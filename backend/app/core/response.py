"""统一响应格式：{code, message, data}。"""
from typing import Any, Generic, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel

T = TypeVar("T")


class Resp(BaseModel, Generic[T]):
    code: int = 200
    message: str = "操作成功"
    data: T | None = None


class BizCode:
    """业务状态码。HTTP 状态统一 200，业务结果由 code 区分。"""

    SUCCESS = 200
    PARAM_ERROR = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    SERVER_ERROR = 500
    LLM_ERROR = 600


def ok(data: Any = None, message: str = "操作成功") -> dict:
    return {"code": BizCode.SUCCESS, "message": message, "data": data}


def fail(code: int = BizCode.SERVER_ERROR, message: str = "操作失败", data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data}


def json_response(code: int = BizCode.SUCCESS, message: str = "操作成功", data: Any = None,
                  http_status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=http_status, content=fail(code, message, data))


def paginated(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "list": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }
