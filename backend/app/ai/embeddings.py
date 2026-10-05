"""文本向量化。

策略：
1. 配置了 EMBEDDING_API_KEY / LLM_API_KEY 时，优先调用 OpenAI 兼容的 embeddings 接口；
2. 否则使用内置的确定性哈希向量（字符 n-gram + 词频），完全离线可用。

哈希向量对中文短文本检索效果足够（实验室知识库问答场景），
且不依赖外网下载模型，保证系统在任何环境下都能演示 RAG。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter

from app.config import settings

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")

_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "有", "我", "你", "他", "它", "们",
    "吗", "呢", "吧", "啊", "怎么", "什么", "如何", "可以", "能否", "请问", "一下",
    "the", "a", "an", "is", "are", "of", "to", "and", "or", "in", "on", "for",
}


# --------------------------------------------------------------------- 本地向量
def _tokens(text: str) -> list[str]:
    """中文按字 + 二元组切分，英文数字按词切分。"""
    raw = _TOKEN_RE.findall(text.lower())
    out: list[str] = []
    for tok in raw:
        if tok in _STOPWORDS:
            continue
        out.append(tok)
        if len(tok) > 1 and not tok.isascii():
            for i in range(len(tok) - 1):
                out.append(tok[i : i + 2])
    # 相邻中文字符的二元组，提升短语匹配能力
    han = [t for t in raw if not t.isascii() and len(t) == 1]
    for a, b in zip(han, han[1:]):
        out.append(a + b)
    return out


def _bucket(token: str, dim: int) -> int:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dim


def local_embed(text: str, dim: int | None = None) -> list[float]:
    """确定性哈希向量（L2 归一化），带 sublinear TF 权重。"""
    dim = dim or settings.LOCAL_EMBED_DIM
    vec = [0.0] * dim
    counts = Counter(_tokens(text))
    if not counts:
        return vec
    for token, cnt in counts.items():
        idx = _bucket(token, dim)
        # 符号哈希，减少不同词落入同一桶时的冲突影响
        sign = 1.0 if hashlib.md5((token + "#s").encode()).digest()[0] % 2 == 0 else -1.0
        vec[idx] += sign * (1.0 + math.log(cnt))
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


# --------------------------------------------------------------------- 远端向量
def _remote_embed(texts: list[str]) -> list[list[float]] | None:
    key = (settings.EMBEDDING_API_KEY or settings.LLM_API_KEY).strip()
    if not key:
        return None
    base = (settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL).rstrip("/")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=base, timeout=settings.LLM_TIMEOUT)
        resp = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in resp.data]
    except Exception:  # noqa: BLE001  远端不可用时静默退回本地向量
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    remote = _remote_embed(texts)
    if remote and len(remote) == len(texts):
        return remote
    return [local_embed(t) for t in texts]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def embedding_backend() -> str:
    return "remote" if settings.embedding_enabled and _remote_embed(["ping"]) else "local"


# --------------------------------------------------------------------- 工具
def to_json(vec: list[float]) -> str:
    return json.dumps([round(v, 6) for v in vec], separators=(",", ":"))


def from_json(raw: str) -> list[float]:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# --------------------------------------------------------------------- 切片
def split_text(text: str, chunk_size: int = 260, overlap: int = 40) -> list[str]:
    """按段落/句子边界切片，保留少量重叠以维持上下文。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    sentences: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？!?；;\n":
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())

    chunks: list[str] = []
    cur = ""
    for sent in sentences:
        if len(sent) > chunk_size:
            # 超长句硬切
            for i in range(0, len(sent), chunk_size - overlap):
                piece = sent[i : i + chunk_size]
                if piece.strip():
                    chunks.append(piece.strip())
            continue
        if len(cur) + len(sent) <= chunk_size:
            cur += sent
        else:
            if cur:
                chunks.append(cur)
            cur = (cur[-overlap:] if overlap and cur else "") + sent
    if cur.strip():
        chunks.append(cur.strip())
    return chunks
