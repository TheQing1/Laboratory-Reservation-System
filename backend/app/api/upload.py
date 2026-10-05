"""文件上传接口（头像、实验室封面）。"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from app.config import settings
from app.core.exceptions import BizException
from app.core.response import ok
from app.core.security import get_current_user
from app.models import User

router = APIRouter(prefix="/upload", tags=["文件上传"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}


@router.post("/image", summary="上传图片")
async def upload_image(file: UploadFile = File(...), _: User = Depends(get_current_user)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise BizException(f"仅支持图片格式：{', '.join(sorted(ALLOWED_EXT))}")
    if file.content_type and file.content_type not in ALLOWED_MIME:
        raise BizException("文件类型不是受支持的图片")

    content = await file.read()
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > limit:
        raise BizException(f"文件大小不能超过 {settings.MAX_UPLOAD_MB} MB")
    if not content:
        raise BizException("文件内容为空")

    sub = settings.UPLOAD_DIR / "images"
    sub.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (sub / name).write_bytes(content)

    url = f"/uploads/images/{name}"
    return ok({"url": url, "filename": name, "size": len(content)}, "上传成功")
