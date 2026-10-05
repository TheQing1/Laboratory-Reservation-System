"""AI 助手对话接口：会话管理 + SSE 流式输出。"""
import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import agent, rag
from app.core.exceptions import NotFoundException, PermissionException
from app.core.response import ok
from app.core.security import get_current_user
from app.database import SessionLocal, get_db
from app.models import ChatMessage, ChatSession, User
from app.schemas import ChatIn

logger = logging.getLogger("lab-booking.chat")
router = APIRouter(prefix="/chat", tags=["AI 助手"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # 关闭 Nginx 缓冲，保证逐字输出
}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("", summary="AI 对话（一次性返回）")
def chat(payload: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = agent.run(
        db, user, payload.message, payload.session_id,
        use_rag=payload.use_rag, use_tools=payload.use_tools,
    )
    return ok(result)


@router.post("/stream", summary="AI 对话（SSE 流式，过程可见）")
def chat_stream(payload: ChatIn, user: User = Depends(get_current_user)):
    """独立打开 Session：生成器在响应结束后才关闭，不能用依赖注入的会话。"""
    user_id = user.id

    def event_source():
        db = SessionLocal()
        try:
            current = db.get(User, user_id)
            if current is None:
                yield _sse({"type": "error", "content": "用户不存在"})
                return
            for event in agent.stream(
                db, current, payload.message, payload.session_id,
                use_rag=payload.use_rag, use_tools=payload.use_tools,
            ):
                yield _sse(event)
        except GeneratorExit:  # 客户端主动断开
            logger.info("SSE 客户端断开连接")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("SSE 流式输出失败")
            yield _sse({"type": "error", "content": f"服务异常：{exc}"})
        finally:
            db.close()
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/sessions", summary="我的会话列表")
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.id.desc())
    ).all()
    return ok(
        [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "message_count": len(s.messages),
            }
            for s in rows
        ]
    )


@router.get("/sessions/{session_id}", summary="会话消息记录")
def session_messages(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.get(ChatSession, session_id)
    if not session:
        raise NotFoundException("会话不存在")
    if session.user_id != user.id and user.role != "admin":
        raise PermissionException()
    return ok(
        {
            "session": {"id": session.id, "title": session.title},
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "tool_name": m.tool_name,
                    "tool_args": json.loads(m.tool_args) if m.tool_args else None,
                    "tool_result": json.loads(m.tool_result) if m.tool_result else None,
                    "created_at": m.created_at,
                }
                for m in session.messages
            ],
        }
    )


@router.delete("/sessions/{session_id}", summary="删除会话")
def delete_session(
    session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    session = db.get(ChatSession, session_id)
    if not session:
        raise NotFoundException("会话不存在")
    if session.user_id != user.id:
        raise PermissionException()
    db.delete(session)
    db.commit()
    return ok(None, "会话已删除")


@router.post("/preview-rag", summary="预览知识库检索结果（调试用）")
def preview_rag(
    query: str = Query(..., min_length=1),
    top_k: int = Query(3, ge=1, le=10),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(rag.search(db, query, top_k=top_k))
