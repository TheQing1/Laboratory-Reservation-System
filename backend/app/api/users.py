"""用户管理接口。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import services
from app.core.exceptions import BizException, NotFoundException, PermissionException
from app.core.response import ok, paginated
from app.core.security import get_current_user, hash_password, require_admin, verify_password
from app.database import get_db
from app.models import User
from app.schemas import PasswordUpdate, ProfileUpdate, UserCreate, UserUpdate

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("", summary="用户列表（分页/搜索）")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str = "",
    role: str = "",
    is_active: bool | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(User)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(User.username.like(like), User.name.like(like), User.student_no.like(like),
                User.email.like(like), User.college.like(like))
        )
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return ok(paginated([services.user_to_dict(u) for u in rows], total, page, page_size))


@router.post("", summary="新增用户")
def create_user(payload: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise BizException("该用户名已存在", code=409, http_status=409)
    if payload.role not in ("admin", "student"):
        raise BizException("角色只能是 admin 或 student")
    user = User(
        username=payload.username,
        password=hash_password(payload.password),
        name=payload.name or payload.username,
        role=payload.role,
        email=payload.email,
        phone=payload.phone,
        student_no=payload.student_no,
        college=payload.college,
        avatar=payload.avatar,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ok(services.user_to_dict(user), "新增成功")


@router.get("/{user_id}", summary="用户详情")
def get_user(user_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.role != "admin" and current.id != user_id:
        raise PermissionException()
    user = db.get(User, user_id)
    if not user:
        raise NotFoundException("用户不存在")
    return ok(services.user_to_dict(user))


@router.put("/{user_id}", summary="修改用户")
def update_user(
    user_id: int, payload: UserUpdate,
    current: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundException("用户不存在")
    if current.role != "admin":
        if current.id != user_id:
            raise PermissionException()
        # 普通用户只能改自己的基础资料
        payload.role = None
        payload.is_active = None

    data = payload.model_dump(exclude_unset=True)
    if data.get("role") and data["role"] not in ("admin", "student"):
        raise BizException("角色只能是 admin 或 student")
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return ok(services.user_to_dict(user), "修改成功")


@router.put("/profile/me", summary="修改个人资料")
def update_profile(
    payload: ProfileUpdate, current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(current, key, value)
    db.commit()
    db.refresh(current)
    return ok(services.user_to_dict(current), "资料已更新")


@router.put("/password/me", summary="修改密码")
def change_password(
    payload: PasswordUpdate, current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not verify_password(payload.old_password, current.password):
        raise BizException("原密码不正确")
    if payload.old_password == payload.new_password:
        raise BizException("新密码不能与原密码相同")
    current.password = hash_password(payload.new_password)
    db.commit()
    return ok(None, "密码修改成功，请重新登录")


@router.delete("/{user_id}", summary="删除用户")
def delete_user(user_id: int, current: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundException("用户不存在")
    if user.id == current.id:
        raise BizException("不能删除当前登录的账号")
    db.delete(user)
    db.commit()
    return ok(None, "删除成功")


@router.put("/{user_id}/status", summary="启用/禁用用户")
def toggle_status(user_id: int, is_active: bool, current: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundException("用户不存在")
    if user.id == current.id:
        raise BizException("不能禁用当前登录的账号")
    user.is_active = is_active
    db.commit()
    return ok(services.user_to_dict(user), "已启用" if is_active else "已禁用")
