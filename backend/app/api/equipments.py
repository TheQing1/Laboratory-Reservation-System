"""实验室设备管理接口。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import services
from app.core.exceptions import BizException, NotFoundException
from app.core.response import ok, paginated
from app.core.security import get_current_user, require_admin
from app.database import get_db
from app.models import Equipment, Lab, User
from app.schemas import EquipmentCreate, EquipmentUpdate

router = APIRouter(prefix="/equipments", tags=["设备管理"])


@router.get("", summary="设备列表（分页/搜索）")
def list_equipments(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str = "",
    lab_id: int | None = None,
    status: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Equipment).join(Lab, Equipment.lab_id == Lab.id)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Equipment.name.like(like), Equipment.model.like(like),
                              Equipment.spec.like(like)))
    if lab_id:
        stmt = stmt.where(Equipment.lab_id == lab_id)
    if status:
        stmt = stmt.where(Equipment.status == status)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Equipment.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [services.equipment_to_dict(e, e.lab.name if e.lab else None) for e in rows]
    return ok(paginated(items, total, page, page_size))


@router.get("/{equipment_id}", summary="设备详情")
def get_equipment(equipment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    eq = db.get(Equipment, equipment_id)
    if not eq:
        raise NotFoundException("设备不存在")
    return ok(services.equipment_to_dict(eq, eq.lab.name if eq.lab else None))


@router.post("", summary="新增设备")
def create_equipment(
    payload: EquipmentCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    if not db.get(Lab, payload.lab_id):
        raise BizException("所属实验室不存在")
    eq = Equipment(**payload.model_dump())
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return ok(services.equipment_to_dict(eq, eq.lab.name if eq.lab else None), "新增成功")


@router.put("/{equipment_id}", summary="修改设备")
def update_equipment(
    equipment_id: int, payload: EquipmentUpdate,
    _: User = Depends(require_admin), db: Session = Depends(get_db),
):
    eq = db.get(Equipment, equipment_id)
    if not eq:
        raise NotFoundException("设备不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("lab_id") and not db.get(Lab, data["lab_id"]):
        raise BizException("所属实验室不存在")
    for key, value in data.items():
        setattr(eq, key, value)
    db.commit()
    db.refresh(eq)
    return ok(services.equipment_to_dict(eq, eq.lab.name if eq.lab else None), "修改成功")


@router.delete("/{equipment_id}", summary="删除设备")
def delete_equipment(
    equipment_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    eq = db.get(Equipment, equipment_id)
    if not eq:
        raise NotFoundException("设备不存在")
    db.delete(eq)
    db.commit()
    return ok(None, "删除成功")
