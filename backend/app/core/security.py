"""JWT 认证与密码加密。"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import AuthException, PermissionException
from app.database import get_db

ALGORITHM = settings.ALGORITHM


def hash_password(plain: str) -> str:
    """bcrypt 加密。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, username: str, role: str,
                        expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "username": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthException("登录已过期，请重新登录") from None
    except jwt.PyJWTError:
        raise AuthException("无效的身份凭证，请重新登录") from None


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # SSE / 下载场景无法自定义 header，允许 query 传 token
    token = request.query_params.get("token")
    if token:
        return token
    raise AuthException("未提供身份凭证，请先登录")


def get_current_user(request: Request, db: Session = Depends(get_db)):
    """解析当前登录用户。"""
    from app.models import User

    payload = decode_token(_extract_token(request))
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None:
        raise AuthException("用户不存在，请重新登录")
    if not user.is_active:
        raise PermissionException("账号已被禁用，请联系管理员")
    return user


def require_roles(*roles: str):
    """角色守卫：require_roles("admin")。"""

    def _dep(user=Depends(get_current_user)):
        if roles and user.role not in roles:
            raise PermissionException()
        return user

    return _dep


require_admin = require_roles("admin")
