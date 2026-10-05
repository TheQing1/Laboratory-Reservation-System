"""应用配置：全部通过 .env / 环境变量覆盖。

这里没有使用 pydantic-settings —— 当前环境中的 pydantic-settings 与 pydantic 2.5.2
不兼容（缺少 pydantic._internal._signature），因此用一个零依赖的轻量实现，
行为与 pydantic-settings 基本一致：环境变量优先于 .env 文件。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# 默认密钥只在本地开发可用；上线（DEBUG=false）会被强制要求替换
DEFAULT_SECRET_KEY = "smart-lab-booking-dev-secret-change-me"
PLACEHOLDER_SECRET_KEYS = {
    DEFAULT_SECRET_KEY,
    "please-change-this-to-a-random-secret-string",
}


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 支持行内注释（仅当 # 前有空格时）
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        if key:
            values[key] = value
    return values


_ENV_FILE_VALUES = _load_env_file(ENV_FILE)


def _raw(name: str, default: str = "") -> str:
    return os.environ.get(name, _ENV_FILE_VALUES.get(name, default))


def _str(name: str, default: str = "") -> str:
    value = _raw(name, default)
    return value if value != "" else default


def _int(name: str, default: int) -> int:
    try:
        return int(float(_raw(name, str(default))))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_raw(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    value = _raw(name, str(default)).strip().lower()
    return value in ("1", "true", "yes", "on", "y")


def _path(name: str, default: Path) -> Path:
    value = _str(name, "")
    return Path(value).expanduser().resolve() if value else default


class Settings:
    """全部配置项。"""

    def __init__(self) -> None:
        # ---- 基础 ----
        self.APP_NAME: str = _str("APP_NAME", "智能实验室预约系统")
        self.API_PREFIX: str = _str("API_PREFIX", "/api")
        self.DEBUG: bool = _bool("DEBUG", True)

        # ---- 数据库 ----
        self.DATABASE_URL: str = _str(
            "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'data' / 'lab_booking.db').as_posix()}"
        )

        # ---- JWT ----
        self.SECRET_KEY: str = _str("SECRET_KEY", DEFAULT_SECRET_KEY)
        self.ALGORITHM: str = _str("ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = _int("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24)

        # ---- 跨域 ----
        self.CORS_ORIGINS: str = _str("CORS_ORIGINS", "*")

        # ---- 上传 ----
        self.UPLOAD_DIR: Path = _path("UPLOAD_DIR", BASE_DIR / "uploads")
        self.MAX_UPLOAD_MB: int = _int("MAX_UPLOAD_MB", 5)

        # ---- 大模型（OpenAI 兼容）----
        self.LLM_API_KEY: str = _str("LLM_API_KEY", "")
        self.LLM_BASE_URL: str = _str("LLM_BASE_URL", "https://api.deepseek.com/v1")
        self.LLM_MODEL: str = _str("LLM_MODEL", "deepseek-chat")
        self.LLM_TEMPERATURE: float = _float("LLM_TEMPERATURE", 0.3)
        self.LLM_TIMEOUT: int = _int("LLM_TIMEOUT", 60)

        # ---- 向量 ----
        self.EMBEDDING_API_KEY: str = _str("EMBEDDING_API_KEY", "")
        self.EMBEDDING_BASE_URL: str = _str("EMBEDDING_BASE_URL", "")
        self.EMBEDDING_MODEL: str = _str("EMBEDDING_MODEL", "text-embedding-3-small")
        self.RAG_TOP_K: int = _int("RAG_TOP_K", 3)
        self.LOCAL_EMBED_DIM: int = _int("LOCAL_EMBED_DIM", 512)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.LLM_API_KEY.strip())

    @property
    def using_placeholder_secret(self) -> bool:
        return (not self.SECRET_KEY.strip()) or self.SECRET_KEY.strip() in PLACEHOLDER_SECRET_KEYS

    @property
    def embedding_enabled(self) -> bool:
        return bool((self.EMBEDDING_API_KEY or self.LLM_API_KEY).strip())

    def describe(self) -> dict:
        return {
            "app": self.APP_NAME,
            "database": self.DATABASE_URL.split("///")[-1] if "///" in self.DATABASE_URL else self.DATABASE_URL,
            "llm_enabled": self.llm_enabled,
            "llm_model": self.LLM_MODEL,
            "llm_base_url": self.LLM_BASE_URL,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if settings.using_placeholder_secret:
    import logging as _logging

    _logging.getLogger("lab-booking.config").warning(
        "SECRET_KEY 仍为默认/占位值，仅可用于本地开发；上线前请在 .env 中替换为随机字符串。"
    )
    if not settings.DEBUG:
        raise RuntimeError("DEBUG=false 时必须配置随机 SECRET_KEY，拒绝使用默认密钥启动")

# 确保运行期目录存在
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
