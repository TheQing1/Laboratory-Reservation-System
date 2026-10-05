"""实验室管理接口。"""
import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import services
from app.core.exceptions import BizException, NotFoundException
from app.core.response import ok, paginated
from app.core.security import get_current_user, require_admin
from app.database import get_db
from app.models import Equipment, Lab, Reservation, User
from app.schemas import LabCreate, LabUpdate

router = APIRouter(prefix="/labs", tags=["实验室管理"])


@router.get("", summary="实验室列表（分页/搜索）")
def list_labs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str = "",
    status: str = "",
    building: str = "",
    min_capacity: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Lab)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(Lab.name.like(like), Lab.code.like(like), Lab.building.like(like),
                Lab.room.like(like), Lab.description.like(like), Lab.tags.like(like))
        )
    if status:
        stmt = stmt.where(Lab.status == status)
    if building:
        stmt = stmt.where(Lab.building.like(f"%{building}%"))
    if min_capacity:
        stmt = stmt.where(Lab.capacity >= min_capacity)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Lab.id).offset((page - 1) * page_size).limit(page_size)
    ).all()

    # 一次性统计设备数量，避免 N+1
    lab_ids = [lab.id for lab in rows]
    eq_counts: dict[int, int] = {}
    if lab_ids:
        eq_counts = dict(
            db.execute(
                select(Equipment.lab_id, func.count(Equipment.id))
                .where(Equipment.lab_id.in_(lab_ids))
                .group_by(Equipment.lab_id)
            ).all()
        )
    items = []
    for lab in rows:
        data = services.lab_to_dict(lab)
        data["equipment_count"] = eq_counts.get(lab.id, 0)
        items.append(data)
    return ok(paginated(items, total, page, page_size))


@router.get("/buildings", summary="楼栋列表（筛选用）")
def list_buildings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(Lab.building).where(Lab.building.is_not(None)).distinct()).all()
    return ok([b for b in rows if b])


@router.get("/{lab_id}", summary="实验室详情")
def get_lab(lab_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lab = db.get(Lab, lab_id)
    if not lab:
        raise NotFoundException("实验室不存在")
    return ok(services.lab_to_dict(lab, with_equipments=True))


@router.get("/{lab_id}/availability", summary="实验室指定日期空闲时段")
def availability(
    lab_id: int,
    date: str = Query(default="", description="YYYY-MM-DD，默认今天"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    lab = db.get(Lab, lab_id)
    if not lab:
        raise NotFoundException("实验室不存在")
    day = services.parse_date(date) if date else dt.date.today()
    slots = services.free_slots(db, lab, day)
    reservations = db.scalars(
        select(Reservation).where(
            Reservation.lab_id == lab_id,
            Reservation.booking_date == day,
            Reservation.status.in_(services.ACTIVE_STATUS),
        ).order_by(Reservation.start_time)
    ).all()
    return ok(
        {
            "lab": services.lab_to_dict(lab),
            "date": day.isoformat(),
            "open_time": lab.open_time,
            "close_time": lab.close_time,
            "free_slots": slots,
            "busy": [
                {"start_time": r.start_time, "end_time": r.end_time, "status": r.status_text}
                for r in reservations
            ],
        }
    )


@router.post("", summary="新增实验室")
def create_lab(payload: LabCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Lab).where(Lab.name == payload.name)):
        raise BizException("同名实验室已存在", code=409, http_status=409)
    if services.to_minutes(payload.open_time) >= services.to_minutes(payload.close_time):
        raise BizException("开放开始时间必须早于结束时间")
    lab = Lab(**payload.model_dump())
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return ok(services.lab_to_dict(lab, with_equipments=True), "新增成功")


@router.put("/{lab_id}", summary="修改实验室")
def update_lab(
    lab_id: int, payload: LabUpdate,
    _: User = Depends(require_admin), db: Session = Depends(get_db),
):
    lab = db.get(Lab, lab_id)
    if not lab:
        raise NotFoundException("实验室不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") and data["name"] != lab.name:
        if db.scalar(select(Lab).where(Lab.name == data["name"])):
            raise BizException("同名实验室已存在", code=409, http_status=409)
    open_t = data.get("open_time", lab.open_time)
    close_t = data.get("close_time", lab.close_time)
    if services.to_minutes(open_t) >= services.to_minutes(close_t):
        raise BizException("开放开始时间必须早于结束时间")
    for key, value in data.items():
        setattr(lab, key, value)
    db.commit()
    db.refresh(lab)
    return ok(services.lab_to_dict(lab, with_equipments=True), "修改成功")


@router.delete("/{lab_id}", summary="删除实验室")
def delete_lab(lab_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    lab = db.get(Lab, lab_id)
    if not lab:
        raise NotFoundException("实验室不存在")
    active = db.scalar(
        select(func.count(Reservation.id)).where(
            Reservation.lab_id == lab_id,
            Reservation.status.in_(services.ACTIVE_STATUS),
            Reservation.booking_date >= dt.date.today(),
        )
    )
    if active:
        raise BizException(f"该实验室还有 {active} 条未完成的预约，无法删除")
    db.delete(lab)
    db.commit()
    return ok(None, "删除成功")
