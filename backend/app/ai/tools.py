"""Tool Calling：把实验室业务数据封装成模型可调用的工具。

每个工具包含 OpenAI function-calling 规范（TOOL_SPECS）与本地执行函数（execute_tool）。
无论模型是否可用，工具层本身都能被独立调用，因此系统在离线时依然"能查数据"。
"""
from __future__ import annotations

import datetime as dt
import logging
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import services
from app.core.exceptions import BizException
from app.models import Equipment, Lab, Reservation, User

logger = logging.getLogger("lab-booking.tools")

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# --------------------------------------------------------------------- 参数规范
TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_labs",
            "description": "查询实验室列表，可按名称/楼栋/用途关键词搜索，并可按状态过滤。返回实验室名称、位置、容量、开放时间、状态与设备数量。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "关键词，如 人工智能、化学、3楼，可为空"},
                    "status": {
                        "type": "string",
                        "enum": ["available", "maintenance", "disabled"],
                        "description": "实验室状态，默认全部",
                    },
                    "min_capacity": {"type": "integer", "description": "最小容纳人数"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lab_detail",
            "description": "查询某个实验室的详细信息，包含位置、容量、开放时间、设备清单和注意事项。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab_name": {"type": "string", "description": "实验室名称，支持模糊匹配"},
                },
                "required": ["lab_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_equipment",
            "description": "按设备名称或型号查询设备分布在哪些实验室、数量与状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "设备名称或型号关键词"},
                    "lab_name": {"type": "string", "description": "限定某个实验室，可为空"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "查询某实验室在某天的空闲时段。日期支持 2026-10-08、今天、明天、后天。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab_name": {"type": "string", "description": "实验室名称"},
                    "date": {"type": "string", "description": "日期，如 2026-10-08 / 今天 / 明天"},
                },
                "required": ["lab_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reservation",
            "description": "为当前用户提交一条实验室预约申请（提交后状态为待审核）。仅在用户明确提供了实验室、日期、开始时间和结束时间时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab_name": {"type": "string", "description": "实验室名称"},
                    "date": {"type": "string", "description": "预约日期，如 2026-10-08 / 明天"},
                    "start_time": {"type": "string", "description": "开始时间 HH:MM"},
                    "end_time": {"type": "string", "description": "结束时间 HH:MM"},
                    "purpose": {"type": "string", "description": "用途说明"},
                    "people_count": {"type": "integer", "description": "使用人数"},
                },
                "required": ["lab_name", "date", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "my_reservations",
            "description": "查询当前用户的预约记录，可按状态过滤（pending 待审核 / approved 已通过 / rejected 已驳回 / cancelled 已取消 / finished 已完成）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "预约状态，可为空表示全部"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "检索实验室规章制度、安全须知、设备操作规范等知识库内容。涉及规定、流程、注意事项时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索问题，如 实验室安全规定 违约处理"},
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_NAMES = [t["function"]["name"] for t in TOOL_SPECS]


# --------------------------------------------------------------------- 辅助
def normalize_date(value: str | None) -> dt.date:
    """解析日期。

    无法识别时抛 BizException 而不是静默返回今天 —— 否则用户说错日期会被
    直接下成一笔“今天”的预约。
    """
    today = dt.date.today()
    if not value or not str(value).strip():
        return today
    v = str(value).strip().lower()
    mapping = {
        "今天": 0, "today": 0, "now": 0,
        "明天": 1, "tomorrow": 1,
        "后天": 2, "大后天": 3,
        "昨天": -1, "yesterday": -1,
    }
    for key, delta in mapping.items():
        if key in v:
            return today + dt.timedelta(days=delta)
    v = v.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%m-%d", "%Y-%m"):
        try:
            parsed = dt.datetime.strptime(v, fmt).date()
            if fmt == "%m-%d":
                parsed = parsed.replace(year=today.year)
            elif fmt == "%Y-%m":
                parsed = parsed.replace(day=1)
            return parsed
        except ValueError:
            continue
    raise BizException(f"无法识别日期「{value}」，请使用 2026-10-08、明天、后天 这样的格式")


def _lab_candidates(db: Session, name: str) -> tuple[Lab | None, list[Lab]]:
    """返回 (精确/编码匹配, 模糊候选列表)。"""
    if not name:
        return None, []
    name = name.strip()
    lab = db.scalar(select(Lab).where(Lab.name == name))
    if lab:
        return lab, [lab]
    lab = db.scalar(select(Lab).where(Lab.code == name))
    if lab:
        return lab, [lab]
    fuzzy = list(db.scalars(select(Lab).where(Lab.name.like(f"%{name}%")).order_by(Lab.id)).all())
    if fuzzy:
        return None, fuzzy
    # 用关键词拆词再试一次
    for token in [t for t in name.replace("实验室", " ").split() if t]:
        found = list(
            db.scalars(select(Lab).where(Lab.name.like(f"%{token}%")).order_by(Lab.id)).all()
        )
        if found:
            return None, found
    return None, []


def _find_lab(db: Session, name: str) -> Lab | None:
    """用于只读查询：模糊匹配到多个时取第一个，保证“能查”优先。"""
    exact, candidates = _lab_candidates(db, name)
    if exact:
        return exact
    return candidates[0] if candidates else None


def _lab_brief(lab: Lab) -> dict:
    return {
        "id": lab.id,
        "name": lab.name,
        "location": lab.location,
        "capacity": lab.capacity,
        "open_time": lab.open_time,
        "close_time": lab.close_time,
        "status": lab.status_text,
        "equipment_count": len(lab.equipments),
        "description": (lab.description or "")[:120],
    }


# --------------------------------------------------------------------- 工具实现
def tool_list_labs(db: Session, keyword: str = "", status: str = "", min_capacity: int = 0) -> dict:
    stmt = select(Lab)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                Lab.name.like(like),
                Lab.building.like(like),
                Lab.room.like(like),
                Lab.description.like(like),
                Lab.tags.like(like),
                Lab.code.like(like),
            )
        )
    if status:
        stmt = stmt.where(Lab.status == status)
    if min_capacity:
        stmt = stmt.where(Lab.capacity >= int(min_capacity))
    labs = db.scalars(stmt.order_by(Lab.id)).all()
    return {
        "total": len(labs),
        "labs": [_lab_brief(lab) for lab in labs],
        "hint": "如需查看设备或空闲时段，可继续询问。" if labs else "没有符合条件的实验室。",
    }


def tool_get_lab_detail(db: Session, lab_name: str) -> dict:
    lab = _find_lab(db, lab_name)
    if not lab:
        return {"found": False, "message": f"没有找到名称包含「{lab_name}」的实验室。"}
    return {
        "found": True,
        "lab": _lab_brief(lab),
        "equipments": [
            {"name": e.name, "model": e.model, "quantity": e.quantity, "status": e.status_text}
            for e in lab.equipments
        ],
        "notices": [
            {"title": d.title, "content": d.content[:300]}
            for d in lab.documents[:3]
        ],
    }


def tool_find_equipment(db: Session, keyword: str, lab_name: str = "") -> dict:
    """按关键词查设备。

    模型/用户给出的关键词往往比设备登记名更长（例如「GPU服务器」vs
    「GPU 计算服务器」），因此先整体匹配，命中不到再逐步退化为更短的
    关键词（分词结果、单词），提升召回率。
    """
    keyword = (keyword or "").strip()
    lab_name = (lab_name or "").strip()

    candidates: list[str] = []
    if keyword:
        candidates.append(keyword)
        # 去掉中文里的「的」等修饰后再切词
        normalized = re.sub(r"[的地得]", " ", keyword)
        parts = [p for p in re.split(r"[\s,，、/]+", normalized) if len(p) >= 2]
        candidates.extend(sorted(parts, key=len, reverse=True))
        # 长关键词再按「前 1/3 片段」兜底，覆盖「GPU服务器」这类连写情况
        if len(keyword) >= 4:
            candidates.append(keyword[: max(2, len(keyword) // 3)])
    # 去重且保持顺序，过滤掉过短的关键词
    seen: set[str] = set()
    ordered = []
    for cand in candidates:
        cand = cand.strip()
        if len(cand) >= 2 and cand not in seen:
            seen.add(cand)
            ordered.append(cand)

    rows: list[Equipment] = []
    used_keyword = keyword
    for cand in ordered:
        stmt = select(Equipment).join(Lab, Equipment.lab_id == Lab.id)
        like = f"%{cand}%"
        stmt = stmt.where(or_(Equipment.name.like(like), Equipment.model.like(like),
                              Equipment.spec.like(like)))
        if lab_name:
            stmt = stmt.where(Lab.name.like(f"%{lab_name}%"))
        found = db.scalars(stmt).all()
        if found:
            rows = found
            used_keyword = cand
            break

    return {
        "total": len(rows),
        "matched_keyword": used_keyword,
        "items": [
            {
                "equipment": e.name,
                "model": e.model,
                "quantity": e.quantity,
                "status": e.status_text,
                "lab": e.lab.name if e.lab else None,
                "lab_location": e.lab.location if e.lab else None,
            }
            for e in rows
        ],
        "hint": "" if rows else "可尝试更简短的设备名，例如「显微镜」「服务器」「示波器」。",
    }


def tool_check_availability(db: Session, lab_name: str, date: str = "") -> dict:
    lab = _find_lab(db, lab_name)
    if not lab:
        return {"found": False, "message": f"没有找到名称包含「{lab_name}」的实验室。"}
    try:
        day = normalize_date(date)
    except BizException as exc:
        return {"found": False, "message": str(exc)}
    slots = services.free_slots(db, lab, day)
    # 合并连续时段，回答更自然
    merged: list[dict] = []
    for slot in slots:
        if merged and merged[-1]["end"] == slot["start"]:
            merged[-1]["end"] = slot["end"]
        else:
            merged.append({"start": slot["start"], "end": slot["end"]})
    return {
        "found": True,
        "lab": lab.name,
        "date": day.isoformat(),
        "weekday": WEEKDAY_CN[day.weekday()],
        "open_time": lab.open_time,
        "close_time": lab.close_time,
        "free_ranges": merged[:12],
        "free_slot_count": len(slots),
    }


def tool_create_reservation(
    db: Session, user: User, lab_name: str, date: str, start_time: str, end_time: str,
    purpose: str = "", people_count: int = 1,
) -> dict:
    # 涉及写操作时不允许“猜”实验室：名称有歧义必须先让用户确认
    lab, candidates = _lab_candidates(db, lab_name)
    if lab is None:
        if not candidates:
            return {"success": False, "message": f"没有找到名称包含「{lab_name}」的实验室，请确认实验室名称。"}
        if len(candidates) > 1:
            names = "、".join(c.name for c in candidates)
            return {
                "success": False,
                "message": f"「{lab_name}」匹配到多个实验室：{names}。请说明具体是哪一间，我再帮你提交。",
                "candidates": [c.name for c in candidates],
            }
        lab = candidates[0]

    try:
        day = normalize_date(date)
    except BizException as exc:
        return {"success": False, "message": str(exc)}

    try:
        services.validate_reservation(db, lab, day, start_time, end_time, int(people_count or 1))
    except Exception as exc:  # noqa: BLE001  BizException
        return {"success": False, "message": str(exc), "lab": lab.name, "date": day.isoformat()}

    reservation = Reservation(
        user_id=user.id,
        lab_id=lab.id,
        booking_date=day,
        start_time=start_time,
        end_time=end_time,
        purpose=purpose or "AI 助手代提交",
        people_count=int(people_count or 1),
        status="pending",
    )
    try:
        db.add(reservation)
        db.flush()  # 拿到 id 后占用槽位，唯一约束兜底并发
        services.occupy_slots(db, lab.id, day, start_time, end_time, reservation.id)
        db.commit()
    except BizException as exc:
        return {"success": False, "message": str(exc), "lab": lab.name, "date": day.isoformat()}
    db.refresh(reservation)
    return {
        "success": True,
        "message": "预约申请已提交，等待管理员审核。",
        "reservation": services.reservation_to_dict(reservation),
    }


def tool_my_reservations(db: Session, user: User, status: str = "") -> dict:
    stmt = select(Reservation).where(Reservation.user_id == user.id)
    if status:
        stmt = stmt.where(Reservation.status == status)
    rows = db.scalars(stmt.order_by(Reservation.booking_date.desc(), Reservation.start_time)).all()
    return {
        "total": len(rows),
        "items": [services.reservation_to_dict(r) for r in rows[:20]],
    }


def tool_search_knowledge(db: Session, query: str, top_k: int = 3) -> dict:
    from app.ai import rag

    hits = rag.search(db, query, top_k=top_k)
    return {
        "total": len(hits),
        "hits": [
            {"title": h["title"], "category": h["category"], "content": h["content"], "score": h["score"]}
            for h in hits
        ],
    }


# --------------------------------------------------------------------- 调度
def execute_tool(name: str, args: dict, db: Session, user: User) -> dict:
    """执行工具并返回结构化结果（永不抛出，错误以 success=False 返回给模型）。"""
    args = args or {}
    logger.info("执行工具 %s 参数 %s", name, args)
    try:
        if name == "list_labs":
            return tool_list_labs(
                db,
                keyword=str(args.get("keyword") or ""),
                status=str(args.get("status") or ""),
                min_capacity=int(args.get("min_capacity") or 0),
            )
        if name == "get_lab_detail":
            return tool_get_lab_detail(db, str(args.get("lab_name") or ""))
        if name == "find_equipment":
            return tool_find_equipment(
                db, str(args.get("keyword") or ""), str(args.get("lab_name") or "")
            )
        if name == "check_availability":
            return tool_check_availability(
                db, str(args.get("lab_name") or ""), str(args.get("date") or "")
            )
        if name == "create_reservation":
            return tool_create_reservation(
                db,
                user,
                str(args.get("lab_name") or ""),
                str(args.get("date") or ""),
                str(args.get("start_time") or ""),
                str(args.get("end_time") or ""),
                str(args.get("purpose") or ""),
                int(args.get("people_count") or 1),
            )
        if name == "my_reservations":
            return tool_my_reservations(db, user, str(args.get("status") or ""))
        if name == "search_knowledge":
            return tool_search_knowledge(db, str(args.get("query") or ""))
        return {"success": False, "message": f"未知工具：{name}"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("工具 %s 执行失败", name)
        return {"success": False, "message": f"工具执行失败：{exc}"}


def tools_summary() -> list[dict]:
    return [
        {"name": t["function"]["name"], "description": t["function"]["description"]}
        for t in TOOL_SPECS
    ]
