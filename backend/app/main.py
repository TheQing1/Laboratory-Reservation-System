"""FastAPI 应用入口。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, chat, dashboard, documents, equipments, labs, reservations, upload, users
from app.config import BASE_DIR, settings
from app.core.exceptions import register_exception_handlers
from app.core.response import ok
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("lab-booking")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("正在初始化数据库…")
    init_db()
    from app.seed import ensure_seed

    ensure_seed()
    # 把 30 分钟预约槽位表与现有预约对齐（兼容旧数据 + 并发互斥的最终防线）
    from app import services
    from app.database import SessionLocal

    with SessionLocal() as db:
        slot_stats = services.sync_slot_index(db)
    logger.info(
        "预约槽位索引就绪：有效预约 %s 条，新建槽位 %s 个，清理 %s 个",
        slot_stats["active"], slot_stats["created"], slot_stats["removed"],
    )
    logger.info("数据库就绪 · 模型模式：%s", "大模型" if settings.llm_enabled else "本地助手")
    yield
    logger.info("应用已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "**FastAPI + Vue3 智能实验室预约系统（自研 ReAct Agent）**\n\n"
        "包含用户认证、实验室与设备管理、预约审核，以及带 RAG 知识库、"
        "Tool Calling 与 SSE 流式输出的 AI 智能预约助手；"
        "预约时段通过 30 分钟粒度槽位唯一约束保证并发下不会重复预约。"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# 静态文件（上传的图片）
app.mount("/uploads", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="uploads")

for router in (
    auth.router,
    users.router,
    labs.router,
    equipments.router,
    reservations.router,
    documents.router,
    chat.router,
    dashboard.router,
    upload.router,
):
    app.include_router(router, prefix=settings.API_PREFIX)


@app.get(f"{settings.API_PREFIX}/health", tags=["系统"], summary="健康检查")
def health():
    return ok({"status": "ok", "llm_enabled": settings.llm_enabled})


@app.get(f"{settings.API_PREFIX}", tags=["系统"], summary="服务信息")
def api_info():
    return ok(
        {
            "app": settings.APP_NAME,
            "version": "1.0.0",
            "docs": "/docs",
            "ai_mode": "llm" if settings.llm_enabled else "local",
        }
    )


# ---------------------------------------------------------------------------
# 生产部署：若前端已构建（frontend/dist 存在），由后端一并托管静态页面，
# 这样只需启动一个进程即可访问完整系统。
# 注意：必须放在所有 API 路由之后注册，否则通配路由会抢先匹配。
# ---------------------------------------------------------------------------
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="frontend-assets",
    )

    @app.get("/", include_in_schema=False)
    async def spa_root():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """前端使用 hash 路由，未匹配的路径统一回落到 index.html。"""
        if full_path.startswith(("api/", "uploads/", "docs", "redoc", "openapi.json")):
            return JSONResponse(
                status_code=404,
                content={"code": 404, "message": "接口不存在", "data": None},
            )
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

    logger.info("已挂载前端静态资源：%s", FRONTEND_DIST)
else:
    @app.get("/", tags=["系统"], summary="服务信息")
    def root():
        return ok(
            {
                "app": settings.APP_NAME,
                "version": "1.0.0",
                "docs": "/docs",
                "ai_mode": "llm" if settings.llm_enabled else "local",
            }
        )

    logger.info("未检测到前端构建产物（frontend/dist），仅提供 API 服务")
