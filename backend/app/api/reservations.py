"""实验室预约接口：提交、查询、取消、审核。"""
import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app import services
from app.core.exceptions import BizException, NotFoundException, PermissionException
from app.core.response import ok, paginated
from app.core.security import get_current_user, require_admin
from app.database import get_db
from app.models import Lab, Reservation, ReservationSlot, User
from app.schemas import ReservationCreate, ReservationReview

router = APIRouter(prefix="/reservations", tags=["实验室预约"])

STATUS_ALL = ("pending", "approved", "rejected", "cancelled", "finished")


def refresh_finished(db: Session) -> int:
    """把已结束的已通过预约标记为「已完成」，并释放其占用的槽位。

    用一条 UPDATE 完成，避免每次列表查询都把所有 approved 记录拉回内存。
    """
    today = dt.date.today()
    now_hm = dt.datetime.now().strftime("%H:%M")
    ids = list(
        db.scalars(
            select(Reservation.id).where(
                Reservation.status == "approved",
                or_(
                    Reservation.booking_date < today,
                    and_(Reservation.booking_date == today, Reservation.end_time <= now_hm),
                ),
            )
        ).all()
    )
    if not ids:
        return 0
    db.execute(update(Reservation).where(Reservation.id.in_(ids)).values(status="finished"))
    db.execute(delete(ReservationSlot).where(ReservationSlot.reservation_id.in_(ids)))
    db.commit()
    return len(ids)


@router.get("", summary="预约列表")
def list_reservations(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: str = "",
    lab_id: int | None = None,
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
    mine: bool = False,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_finished(db)
    stmt = select(Reservation).join(Lab, Reservation.lab_id == Lab.id).join(
        User, Reservation.user_id == User.id
    ).options(joinedload(Reservation.lab), joinedload(Reservation.user))
    # 学生只能看到自己的预约
    if current.role != "admin" or mine:
        stmt = stmt.where(Reservation.user_id == current.id)
    if status:
        stmt = stmt.where(Reservation.status == status)
    if lab_id:
        stmt = stmt.where(Reservation.lab_id == lab_id)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(Lab.name.like(like), User.username.like(like), User.name.like(like),
                Reservation.purpose.like(like))
        )
    if date_from:
        stmt = stmt.where(Reservation.booking_date >= services.parse_date(date_from))
    if date_to:
        stmt = stmt.where(Reservation.booking_date <= services.parse_date(date_to))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Reservation.booking_date.desc(), Reservation.start_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ok(paginated([services.reservation_to_dict(r) for r in rows], total, page, page_size))


@router.get("/stats", summary="预约统计")
def reservation_stats(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    refresh_finished(db)
    stmt = select(Reservation.status, func.count(Reservation.id)).group_by(Reservation.status)
    if current.role != "admin":
        stmt = stmt.where(Reservation.user_id == current.id)
    counts = {s: c for s, c in db.execute(stmt).all()}
    return ok(
        {
            "total": sum(counts.values()),
            **{s: counts.get(s, 0) for s in STATUS_ALL},
        }
    )


@router.get("/{reservation_id}", summary="预约详情")
def get_reservation(
    reservation_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    r = db.get(Reservation, reservation_id)
    if not r:
        raise NotFoundException("预约记录不存在")
    if current.role != "admin" and r.user_id != current.id:
        raise PermissionException()
    return ok(services.reservation_to_dict(r))


@router.post("", summary="提交预约")
def create_reservation(
    payload: ReservationCreate, current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    lab = db.get(Lab, payload.lab_id)
    if not lab:
        raise NotFoundException("实验室不存在")
    day = services.parse_date(payload.booking_date)
    services.validate_reservation(db, lab, day, payload.start_time, payload.end_time, payload.people_count)

    reservation = Reservation(
        user_id=current.id,
        lab_id=lab.id,
        booking_date=day,
        start_time=payload.start_time,
        end_time=payload.end_time,
        purpose=payload.purpose,
        people_count=payload.people_count,
        status="pending",
    )
    db.add(reservation)
    db.flush()  # 先拿到预约 id，再占用槽位；槽位冲突会连同本次插入一起回滚
    services.occupy_slots(db, lab.id, day, payload.start_time, payload.end_time, reservation.id)
    db.commit()
    db.refresh(reservation)
    return ok(services.reservation_to_dict(reservation), "预约申请已提交，等待管理员审核")


@router.put("/{reservation_id}", summary="修改预约（仅待审核）")
def update_reservation(
    reservation_id: int, payload: ReservationCreate,
    current: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    r = db.get(Reservation, reservation_id)
    if not r:
        raise NotFoundException("预约记录不存在")
    if current.role != "admin" and r.user_id != current.id:
        raise PermissionException()
    if r.status not in ("pending",):
        raise BizException(f"当前状态为「{r.status_text}」，不能修改")

    lab = db.get(Lab, payload.lab_id)
    if not lab:
        raise NotFoundException("实验室不存在")
    day = services.parse_date(payload.booking_date)
    services.validate_reservation(
        db, lab, day, payload.start_time, payload.end_time, payload.people_count, exclude_id=r.id
    )
    r.lab_id = lab.id
    r.booking_date = day
    r.start_time = payload.start_time
    r.end_time = payload.end_time
    r.purpose = payload.purpose
    r.people_count = payload.people_count
    services.release_slots(db, r.id)
    services.occupy_slots(db, lab.id, day, payload.start_time, payload.end_time, r.id)
    db.commit()
    db.refresh(r)
    return ok(services.reservation_to_dict(r), "修改成功，等待重新审核")


@router.put("/{reservation_id}/cancel", summary="取消预约")
def cancel_reservation(
    reservation_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    r = db.get(Reservation, reservation_id)
    if not r:
        raise NotFoundException("预约记录不存在")
    if current.role != "admin" and r.user_id != current.id:
        raise PermissionException()
    if r.status in ("cancelled", "finished"):
        raise BizException(f"当前状态为「{r.status_text}」，无法取消")
    if r.status == "approved" and r.booking_date < dt.date.today():
        raise BizException("已过期的预约无法取消")
    r.status = "cancelled"
    services.release_slots(db, r.id)
    db.commit()
    db.refresh(r)
    return ok(services.reservation_to_dict(r), "已取消预约")


@router.put("/{reservation_id}/review", summary="审核预约（管理员）")
def review_reservation(
    reservation_id: int, payload: ReservationReview,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    r = db.get(Reservation, reservation_id)
    if not r:
        raise NotFoundException("预约记录不存在")
    if r.status != "pending":
        raise BizException(f"该预约当前状态为「{r.status_text}」，无法重复审核")

    if payload.status == "approved":
        # 审核时再次校验冲突，避免同一时段被批准两次
        conflicts = services.find_conflicts(
            db, r.lab_id, r.booking_date, r.start_time, r.end_time, exclude_id=r.id
        )
        approved_conflicts = [c for c in conflicts if c.status == "approved"]
        if approved_conflicts:
            c = approved_conflicts[0]
            raise BizException(
                f"该时段已被其他预约占用（{c.start_time}-{c.end_time}），无法通过"
            )
        # 自动驳回同一时段的其它待审核申请
        for other in [c for c in conflicts if c.status == "pending"]:
            other.status = "rejected"
            other.review_remark = "同一时段已有通过的预约，系统自动驳回"
            other.reviewer_id = admin.id
            other.reviewed_at = dt.datetime.now()
            services.release_slots(db, other.id)
    else:
        # 驳回后释放时段，供其他同学预约
        services.release_slots(db, r.id)

    r.status = payload.status
    r.review_remark = payload.review_remark or ("审核通过" if payload.status == "approved" else "审核驳回")
    r.reviewer_id = admin.id
    r.reviewed_at = dt.datetime.now()
    db.commit()
    db.refresh(r)
    return ok(services.reservation_to_dict(r), "审核完成")


@router.delete("/{reservation_id}", summary="删除预约（管理员）")
def delete_reservation(
    reservation_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    r = db.get(Reservation, reservation_id)
    if not r:
        raise NotFoundException("预约记录不存在")
    services.release_slots(db, r.id)
    db.delete(r)
    db.commit()
    return ok(None, "删除成功")
