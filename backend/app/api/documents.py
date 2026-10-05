"""知识库管理接口（RAG 数据源）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import services
from app.ai import rag
from app.core.exceptions import BizException, NotFoundException
from app.core.response import ok, paginated
from app.core.security import get_current_user, require_admin
from app.database import get_db
from app.models import Lab, LabDocument, User
from app.schemas import DocumentCreate, DocumentUpdate

router = APIRouter(prefix="/documents", tags=["知识库"])


@router.get("", summary="知识库文档列表")
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str = "",
    category: str = "",
    lab_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(LabDocument)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(LabDocument.title.like(like), LabDocument.content.like(like)))
    if category:
        stmt = stmt.where(LabDocument.category == category)
    if lab_id:
        stmt = stmt.where(LabDocument.lab_id == lab_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(LabDocument.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = []
    for doc in rows:
        data = services.document_to_dict(doc)
        data["content_preview"] = (doc.content or "")[:120]
        items.append(data)
    return ok(paginated(items, total, page, page_size))


@router.get("/categories", summary="知识库分类")
def categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(LabDocument.category).distinct()).all()
    return ok(sorted({c for c in rows if c}))


@router.get("/stats", summary="知识库统计")
def stats(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return ok(rag.knowledge_stats(db))


@router.post("/search", summary="知识库检索（调试/预览用）")
def search(
    query: str = Query(..., min_length=1),
    top_k: int = Query(3, ge=1, le=10),
    lab_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return ok(rag.search(db, query, top_k=top_k, lab_id=lab_id))


@router.get("/{doc_id}", summary="文档详情")
def get_document(doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.get(LabDocument, doc_id)
    if not doc:
        raise NotFoundException("文档不存在")
    return ok(services.document_to_dict(doc))


@router.post("", summary="新增文档（自动向量化）")
def create_document(
    payload: DocumentCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    if payload.lab_id and not db.get(Lab, payload.lab_id):
        raise BizException("关联的实验室不存在")
    doc = LabDocument(**payload.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    chunks = rag.index_document(db, doc)
    data = services.document_to_dict(doc)
    data["chunks"] = chunks
    return ok(data, f"新增成功，已生成 {chunks} 个知识片段")


@router.put("/{doc_id}", summary="修改文档（重新向量化）")
def update_document(
    doc_id: int, payload: DocumentUpdate,
    _: User = Depends(require_admin), db: Session = Depends(get_db),
):
    doc = db.get(LabDocument, doc_id)
    if not doc:
        raise NotFoundException("文档不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("lab_id") and not db.get(Lab, data["lab_id"]):
        raise BizException("关联的实验室不存在")
    for key, value in data.items():
        setattr(doc, key, value)
    db.commit()
    db.refresh(doc)
    chunks = rag.index_document(db, doc)
    out = services.document_to_dict(doc)
    out["chunks"] = chunks
    return ok(out, "修改成功，已重新建立索引")


@router.delete("/{doc_id}", summary="删除文档")
def delete_document(doc_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.get(LabDocument, doc_id)
    if not doc:
        raise NotFoundException("文档不存在")
    rag.remove_document(db, doc_id)
    db.delete(doc)
    db.commit()
    return ok(None, "删除成功")


@router.post("/reindex", summary="全量重建向量索引")
def reindex(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    total = rag.reindex_all(db)
    return ok({"chunks": total}, f"重建完成，共 {total} 个知识片段")
