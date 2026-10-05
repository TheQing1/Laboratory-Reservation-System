"""数据库会话与声明基类。

说明：环境未提供 aiosqlite，因此采用同步 SQLAlchemy 2.0 + SQLite。
FastAPI 会把 def 路由放到线程池执行，不会阻塞事件循环。
"""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_connect_args = (
    {"check_same_thread": False, "timeout": 15}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    echo=False,
)

if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite 默认关闭外键约束，这里显式打开，保证级联删除生效；
    # 同时开启 WAL 与忙等待，降低并发写入时的 "database is locked" 概率。
    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（首次启动或新增模型时自动补建）。"""
    from app import models  # noqa: F401  触发模型注册

    Base.metadata.create_all(bind=engine)
