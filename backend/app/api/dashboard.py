"""首页仪表盘与统计接口。"""
import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import services
from app.ai import embeddings, llm, rag
from app.ai import tools as T
from app.core.response import ok
from app.core.security import get_current_user
from app.database import get_db
from app.models import Lab, Reservation, User

router = APIRouter(prefix="/dashboard", tags=["首页统计"])


@router.get("/stats", summary="系统概览统计")
def stats(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.api.reservations import refresh_finished

    refresh_finished(db)
    data = services.dashboard_stats(db)

    # 学生端的个人数据
    if current.role != "admin":
        mine = db.scalars(select(Reservation).where(Reservation.user_id == current.id)).all()
        data["my_total"] = len(mine)
        data["my_pending"] = sum(1 for r in mine if r.status == "pending")
        data["my_approved"] = sum(1 for r in mine if r.status == "approved")
        data["my_finished"] = sum(1 for r in mine if r.status == "finished")

    # 今日推荐：可用实验室中较空闲的 3 间
    today = dt.date.today()
    busy_ids = set(
        db.scalars(
            select(Reservation.lab_id).where(
                Reservation.booking_date == today,
                Reservation.status.in_(services.ACTIVE_STATUS),
            )
        ).all()
    )
    candidates = db.scalars(
        select(Lab).where(Lab.status == "available").order_by(Lab.capacity.desc()).limit(12)
    ).all()
    recommended = [
        {
            "id": lab.id,
            "name": lab.name,
            "location": lab.location,
            "capacity": lab.capacity,
            "open_time": lab.open_time,
            "close_time": lab.close_time,
            "free_slot_count": len(services.free_slots(db, lab, today)),
            "busy_today": lab.id in busy_ids,
        }
        for lab in candidates
    ]
    recommended.sort(key=lambda x: (x["busy_today"], -x["free_slot_count"]))
    data["recommended"] = recommended[:3]
    return ok(data)


@router.get("/ai-status", summary="AI 能力状态")
def ai_status(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    health = llm.health()
    return ok(
        {
            "llm": health,
            "embedding_backend": embeddings.embedding_backend(),
            "knowledge": rag.knowledge_stats(db),
            "tools": T.tools_summary(),
            "mode": "llm" if health.get("ok") else "local",
            "mode_text": "大模型模式" if health.get("ok") else "本地助手模式",
        }
    )
