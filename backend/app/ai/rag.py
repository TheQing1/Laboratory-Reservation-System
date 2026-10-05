"""RAG 知识库：文档切片、向量化、相似度检索。

向量存放在 doc_chunks 表（JSON 数组），检索时做余弦相似度排序。
文档量大时可无缝切换到 Chroma，接口保持一致。
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai import embeddings as emb
from app.config import settings
from app.models import DocChunk, LabDocument

logger = logging.getLogger("lab-booking.rag")


def index_document(db: Session, doc: LabDocument) -> int:
    """把文档切片并写入向量表，返回切片数。"""
    db.execute(delete(DocChunk).where(DocChunk.document_id == doc.id))
    chunks = emb.split_text(doc.content)
    if not chunks:
        db.commit()
        return 0
    vectors = emb.embed_texts(chunks)
    for seq, (text, vec) in enumerate(zip(chunks, vectors)):
        db.add(
            DocChunk(
                document_id=doc.id,
                lab_id=doc.lab_id,
                seq=seq,
                content=text,
                embedding=emb.to_json(vec),
                dim=len(vec),
            )
        )
    db.commit()
    logger.info("文档 #%s 已索引 %s 个切片", doc.id, len(chunks))
    return len(chunks)


def reindex_all(db: Session) -> int:
    docs = db.scalars(select(LabDocument)).all()
    total = 0
    for doc in docs:
        total += index_document(db, doc)
    return total


def remove_document(db: Session, doc_id: int) -> None:
    db.execute(delete(DocChunk).where(DocChunk.document_id == doc_id))


def _keyword_overlap(query: str, text: str) -> float:
    """查询词在文本中的字面命中率（中文按二元组）。

    纯向量检索对「短查询 vs 长中文段落」容易失准，这里加入字面重叠度作为修正：
    类似 BM25 的关键词召回，与向量分数加权融合后排序更稳。
    """
    tokens = [t for t in emb._tokens(query) if len(t) >= 2]
    if not tokens:
        return 0.0
    unique = set(tokens)
    hit = sum(1 for t in unique if t in text)
    return hit / len(unique)


def search(db: Session, query: str, top_k: int | None = None, lab_id: int | None = None) -> list[dict]:
    """检索最相关的知识片段（向量相似度 + 关键词重叠加权）。"""
    top_k = top_k or settings.RAG_TOP_K
    if not query or not query.strip():
        return []

    stmt = select(DocChunk)
    if lab_id:
        # 命中指定实验室的知识 + 通用知识
        stmt = stmt.where((DocChunk.lab_id == lab_id) | (DocChunk.lab_id.is_(None)))
    rows = db.scalars(stmt).all()
    if not rows:
        return []

    qvec = emb.embed_text(query)
    scored: list[tuple[float, float, DocChunk]] = []
    for row in rows:
        vector_score = emb.cosine(qvec, emb.from_json(row.embedding))
        overlap = _keyword_overlap(query, row.content)
        # 向量 0.45 + 关键词 0.55：制度类问答更依赖字面命中
        final = 0.45 * vector_score + 0.55 * overlap
        scored.append((final, overlap, row))
    scored.sort(key=lambda x: x[0], reverse=True)

    best = scored[0][0] if scored else 0.0
    threshold = max(0.10, best * 0.5)
    hits = [item for item in scored[: max(top_k * 3, top_k)]
            if item[0] >= threshold or item[1] > 0][:top_k]

    if not hits:
        return []

    doc_ids = {r.document_id for _, _, r in hits}
    docs = {
        d.id: d
        for d in db.scalars(select(LabDocument).where(LabDocument.id.in_(doc_ids))).all()
    }
    results = []
    for final, overlap, row in hits:
        doc = docs.get(row.document_id)
        results.append(
            {
                "document_id": row.document_id,
                "title": doc.title if doc else "知识片段",
                "category": doc.category if doc else "",
                "lab_id": row.lab_id,
                "content": row.content,
                "score": round(float(final), 4),
                "overlap": round(float(overlap), 4),
            }
        )
    return results


def knowledge_stats(db: Session) -> dict:
    from sqlalchemy import func

    doc_count = db.scalar(select(func.count(LabDocument.id))) or 0
    chunk_count = db.scalar(select(func.count(DocChunk.id))) or 0
    return {
        "documents": doc_count,
        "chunks": chunk_count,
        "backend": emb.embedding_backend(),
        "dim": settings.LOCAL_EMBED_DIM,
    }
