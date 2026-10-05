"""自定义业务异常与全局异常处理器。"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.response import BizCode, json_response

logger = logging.getLogger("lab-booking")


class BizException(Exception):
    """业务异常：由业务代码主动抛出。"""

    def __init__(self, message: str, code: int = BizCode.PARAM_ERROR, http_status: int = 200):
        self.message = message
        self.code = code
        self.http_status = http_status
        super().__init__(message)


class AuthException(BizException):
    def __init__(self, message: str = "登录状态已失效，请重新登录"):
        super().__init__(message, code=BizCode.UNAUTHORIZED, http_status=401)


class PermissionException(BizException):
    def __init__(self, message: str = "没有权限执行该操作"):
        super().__init__(message, code=BizCode.FORBIDDEN, http_status=403)


class NotFoundException(BizException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code=BizCode.NOT_FOUND, http_status=404)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizException)
    async def _biz(_: Request, exc: BizException):
        return json_response(exc.code, exc.message, http_status=exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
        msg = first.get("msg", "参数校验失败").replace("Value error, ", "")
        detail = f"{loc}: {msg}" if loc else msg
        return json_response(BizCode.PARAM_ERROR, f"参数校验失败（{detail}）")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        mapping = {401: BizCode.UNAUTHORIZED, 403: BizCode.FORBIDDEN, 404: BizCode.NOT_FOUND}
        code = mapping.get(exc.status_code, BizCode.SERVER_ERROR)
        return json_response(code, str(exc.detail), http_status=200)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("未处理异常: %s", exc)
        return json_response(BizCode.SERVER_ERROR, f"服务器内部错误：{exc}", http_status=200)
