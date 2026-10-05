"""认证接口：登录、注册、当前用户。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.core.exceptions import BizException
from app.core.response import ok
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.schemas import LoginIn, RegisterIn

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", summary="用户登录")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password):
        raise BizException("用户名或密码错误")
    if not user.is_active:
        raise BizException("账号已被禁用，请联系管理员", code=403, http_status=403)
    token = create_access_token(user.id, user.username, user.role)
    return ok({"token": token, "token_type": "Bearer", "user": services.user_to_dict(user)}, "登录成功")


@router.post("/register", summary="学生注册")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise BizException("该用户名已被注册", code=409, http_status=409)
    user = User(
        username=payload.username,
        password=hash_password(payload.password),
        name=payload.name or payload.username,
        role="student",
        email=payload.email,
        phone=payload.phone,
        student_no=payload.student_no,
        college=payload.college,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username, user.role)
    return ok({"token": token, "token_type": "Bearer", "user": services.user_to_dict(user)}, "注册成功")


@router.get("/me", summary="获取当前登录用户")
def me(user: User = Depends(get_current_user)):
    return ok(services.user_to_dict(user))


@router.post("/logout", summary="退出登录")
def logout(user: User = Depends(get_current_user)):
    # JWT 无状态，前端清除本地 token 即可；此处保留接口便于扩展黑名单
    return ok(None, "已退出登录")
