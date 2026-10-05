"""大模型客户端：统一封装 OpenAI 兼容接口（DeepSeek / 通义 / OpenAI / Ollama 均可）。"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from app.config import settings

logger = logging.getLogger("lab-booking.llm")


class LLMNotConfigured(RuntimeError):
    """未配置 API Key。"""


def is_enabled() -> bool:
    return settings.llm_enabled


def _client():
    if not settings.llm_enabled:
        raise LLMNotConfigured("未配置 LLM_API_KEY")
    from openai import OpenAI

    return OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL.rstrip("/"),
        timeout=settings.LLM_TIMEOUT,
    )


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float | None = None,
) -> dict:
    """一次非流式对话，返回 {"content": str, "tool_calls": [ {id,name,arguments} ]}。"""
    client = _client()
    kwargs: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0].message
    tool_calls = []
    for tc in (choice.tool_calls or []):
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
    return {"content": choice.content or "", "tool_calls": tool_calls, "usage": getattr(resp, "usage", None)}


def chat_stream(messages: list[dict], temperature: float | None = None) -> Iterator[str]:
    """流式输出纯文本增量。"""
    client = _client()
    stream = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


def health() -> dict:
    """探测模型可用性（用于 /ai/status）。"""
    if not settings.llm_enabled:
        return {"enabled": False, "ok": False, "model": settings.LLM_MODEL, "message": "未配置 LLM_API_KEY，使用本地助手引擎"}
    try:
        resp = chat([{"role": "user", "content": "ping"}], temperature=0)
        return {
            "enabled": True,
            "ok": True,
            "model": settings.LLM_MODEL,
            "base_url": settings.LLM_BASE_URL,
            "reply": (resp.get("content") or "")[:40],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("模型连通性探测失败: %s", exc)
        return {"enabled": True, "ok": False, "model": settings.LLM_MODEL, "message": f"模型不可用：{exc}"}
