"""业务服务层：序列化与预约校验（供 API 路由与 AI 工具共同复用）。"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.exceptions import BizException
from app.models import Equipment, Lab, LabDocument, Reservation, ReservationSlot, User

ACTIVE_STATUS = ("pending", "approved")

# 预约槽位粒度：与前端时间轴、free_slots 保持一致
SLOT_MINUTES = 30
MAX_RESERVATION_MINUTES = 8 * 60


# --------------------------------------------------------------------- 序列化
def equipment_to_dict(eq: Equipment, lab_name: str | None = None) -> dict:
    return {
        "id": eq.id,
        "lab_id": eq.lab_id,
        "lab_name": lab_name,
        "name": eq.name,
        "model": eq.model,
        "quantity": eq.quantity,
        "status": eq.status,
        "status_text": eq.status_text,
        "spec": eq.spec,
        "description": eq.description,
    }


def lab_to_dict(lab: Lab, with_equipments: bool = False) -> dict:
    data = {
        "id": lab.id,
        "name": lab.name,
        "code": lab.code,
        "building": lab.building,
        "room": lab.room,
        "location": lab.location,
        "capacity": lab.capacity,
        "open_time": lab.open_time,
        "close_time": lab.close_time,
        "description": lab.description,
        "cover": lab.cover,
        "status": lab.status,
        "status_text": lab.status_text,
        "tags": lab.tags,
        "created_at": lab.created_at,
    }
    if with_equipments:
        data["equipments"] = [equipment_to_dict(e, lab.name) for e in lab.equipments]
    return data


def user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "name": u.name,
        "role": u.role,
        "role_text": u.role_text,
        "email": u.email,
        "phone": u.phone,
        "student_no": u.student_no,
        "college": u.college,
        "avatar": u.avatar,
        "is_active": u.is_active,
        "created_at": u.created_at,
    }


def reservation_to_dict(r: Reservation) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "lab_id": r.lab_id,
        "lab_name": r.lab.name if r.lab else None,
        "username": r.user.username if r.user else None,
        "user_name": (r.user.name or r.user.username) if r.user else None,
        "booking_date": r.booking_date.isoformat() if r.booking_date else None,
        "start_time": r.start_time,
        "end_time": r.end_time,
        "time_range": r.time_range,
        "purpose": r.purpose,
        "people_count": r.people_count,
        "status": r.status,
        "status_text": r.status_text,
        "review_remark": r.review_remark,
        "reviewed_at": r.reviewed_at,
        "created_at": r.created_at,
    }


def document_to_dict(d: LabDocument) -> dict:
    return {
        "id": d.id,
        "lab_id": d.lab_id,
        "lab_name": d.lab.name if d.lab else None,
        "title": d.title,
        "category": d.category,
        "content": d.content,
        "source": d.source,
        "created_at": d.created_at,
    }


# --------------------------------------------------------------------- 时间
def to_minutes(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        raise BizException(f"时间格式不正确：{hhmm}，应为 HH:MM") from None


def minutes_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise BizException(f"日期格式不正确：{value}，应为 YYYY-MM-DD") from None


# --------------------------------------------------------------------- 预约校验
def find_conflicts(
    db: Session, lab_id: int, booking_date: dt.date, start: str, end: str,
    exclude_id: int | None = None,
) -> list[Reservation]:
    """同一实验室、同一天、状态有效且时间重叠的预约。"""
    stmt = select(Reservation).where(
        Reservation.lab_id == lab_id,
        Reservation.booking_date == booking_date,
        Reservation.status.in_(ACTIVE_STATUS),
    )
    if exclude_id:
        stmt = stmt.where(Reservation.id != exclude_id)
    s, e = to_minutes(start), to_minutes(end)
    return [r for r in db.scalars(stmt).all() if to_minutes(r.start_time) < e and s < to_minutes(r.end_time)]


def validate_reservation(
    db: Session, lab: Lab, booking_date: dt.date, start: str, end: str,
    people_count: int, exclude_id: int | None = None,
) -> None:
    """预约合法性校验，非法时抛 BizException。"""
    if lab.status != "available":
        raise BizException(f"实验室「{lab.name}」当前{lab.status_text}，暂不可预约")
    if booking_date < dt.date.today():
        raise BizException("不能预约过去的日期")
    if booking_date > dt.date.today() + dt.timedelta(days=90):
        raise BizException("最多只能提前 90 天预约")

    s, e = to_minutes(start), to_minutes(end)
    if e <= s:
        raise BizException("结束时间必须晚于开始时间")
    if e - s < 30:
        raise BizException("单次预约时长不能少于 30 分钟")
    if e - s > 8 * 60:
        raise BizException("单次预约时长不能超过 8 小时")
    if s < to_minutes(lab.open_time) or e > to_minutes(lab.close_time):
        raise BizException(f"预约时间需在实验室开放时间 {lab.open_time}-{lab.close_time} 内")
    if people_count > lab.capacity:
        raise BizException(f"使用人数 {people_count} 超过实验室容量 {lab.capacity}")

    conflicts = find_conflicts(db, lab.id, booking_date, start, end, exclude_id)
    if conflicts:
        c = conflicts[0]
        raise BizException(
            f"该时段与已有预约冲突（{c.start_time}-{c.end_time}，{c.status_text}），请另选时间"
        )


# --------------------------------------------------------------------- 预约槽位（并发互斥）
def slot_minutes(start: str, end: str) -> list[int]:
    """把 [start, end) 映射为 30 分钟槽位（起点向下取整，覆盖到结束前）。

    例：14:00-14:30 -> [840]；14:10-14:40 -> [840, 870]。
    向下取整只会更保守，不会漏判重叠。
    """
    s, e = to_minutes(start), to_minutes(end)
    first = (s // SLOT_MINUTES) * SLOT_MINUTES
    return list(range(first, e, SLOT_MINUTES))


def occupy_slots(db: Session, lab_id: int, booking_date: dt.date,
                 start: str, end: str, reservation_id: int) -> None:
    """原子占用时间段槽位。

    唯一约束 (lab_id, booking_date, slot_minute) 是并发安全的最终防线：
    两个请求同时校验“无冲突”后写入，也只有一个能成功提交。
    """
    for minute in slot_minutes(start, end):
        db.add(
            ReservationSlot(
                lab_id=lab_id,
                booking_date=booking_date,
                slot_minute=minute,
                reservation_id=reservation_id,
            )
        )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise BizException("该时段刚被其他申请占用，请刷新后重新选择空闲时段") from None
    except OperationalError:
        # SQLite 在极端竞争下可能先报锁冲突；同样回滚，避免出现半条预约
        db.rollback()
        raise BizException("系统繁忙，请稍后重试") from None


def release_slots(db: Session, reservation_id: int) -> None:
    """释放某条预约占用的全部槽位（取消 / 驳回 / 删除 / 完成时调用）。"""
    db.execute(delete(ReservationSlot).where(ReservationSlot.reservation_id == reservation_id))


def sync_slot_index(db: Session) -> dict:
    """启动时把槽位表与现有预约对齐，兼容没有槽位记录的旧数据。"""
    active = db.scalars(select(Reservation).where(Reservation.status.in_(ACTIVE_STATUS))).all()
    active_ids = {r.id for r in active}

    removed = 0
    for row in db.scalars(select(ReservationSlot)).all():
        if row.reservation_id not in active_ids:
            db.delete(row)
            removed += 1
    db.flush()

    occupied = {
        (row.lab_id, row.booking_date, row.slot_minute)
        for row in db.scalars(select(ReservationSlot)).all()
    }
    created = 0
    for r in active:
        for minute in slot_minutes(r.start_time, r.end_time):
            key = (r.lab_id, r.booking_date, minute)
            if key in occupied:
                continue
            occupied.add(key)
            db.add(
                ReservationSlot(
                    lab_id=r.lab_id,
                    booking_date=r.booking_date,
                    slot_minute=minute,
                    reservation_id=r.id,
                )
            )
            created += 1
    db.commit()
    return {"active": len(active), "created": created, "removed": removed}


def free_slots(db: Session, lab: Lab, booking_date: dt.date, step: int = 30) -> list[dict]:
    """返回指定日期实验室的空闲时段，供前端时间轴与 AI 推荐使用。"""
    open_m, close_m = to_minutes(lab.open_time), to_minutes(lab.close_time)
    busy = [(to_minutes(r.start_time), to_minutes(r.end_time))
            for r in db.scalars(
                select(Reservation).where(
                    Reservation.lab_id == lab.id,
                    Reservation.booking_date == booking_date,
                    Reservation.status.in_(ACTIVE_STATUS),
                )
            ).all()]
    slots: list[dict] = []
    cur = open_m
    while cur + step <= close_m:
        nxt = cur + step
        occupied = any(bs < nxt and cur < be for bs, be in busy)
        if not occupied:
            slots.append({"start": minutes_to_hhmm(cur), "end": minutes_to_hhmm(nxt)})
        cur = nxt
    return slots


# --------------------------------------------------------------------- 统计
def dashboard_stats(db: Session) -> dict:
    today = dt.date.today()
    total_labs = db.scalar(select(func.count(Lab.id))) or 0
    available_labs = db.scalar(select(func.count(Lab.id)).where(Lab.status == "available")) or 0
    total_users = db.scalar(select(func.count(User.id))) or 0
    total_reservations = db.scalar(select(func.count(Reservation.id))) or 0
    pending = db.scalar(
        select(func.count(Reservation.id)).where(Reservation.status == "pending")
    ) or 0
    today_count = db.scalar(
        select(func.count(Reservation.id)).where(Reservation.booking_date == today)
    ) or 0
    approved = db.scalar(
        select(func.count(Reservation.id)).where(Reservation.status == "approved")
    ) or 0
    total_equipments = db.scalar(select(func.coalesce(func.sum(Equipment.quantity), 0))) or 0

    by_status = [
        {"status": s, "status_text": Reservation.STATUS_TEXT[s], "count": c}
        for s, c in db.execute(
            select(Reservation.status, func.count(Reservation.id))
            .group_by(Reservation.status)
        ).all()
    ]

    # 近 7 天预约趋势
    trend = []
    for i in range(6, -1, -1):
        day = today - dt.timedelta(days=i)
        cnt = db.scalar(
            select(func.count(Reservation.id)).where(Reservation.booking_date == day)
        ) or 0
        trend.append({"date": day.isoformat(), "label": f"{day.month}/{day.day}", "count": cnt})

    # 实验室热度 Top5
    hot_rows = db.execute(
        select(Lab.name, func.count(Reservation.id).label("cnt"))
        .join(Reservation, Reservation.lab_id == Lab.id, isouter=True)
        .group_by(Lab.id)
        .order_by(func.count(Reservation.id).desc())
        .limit(5)
    ).all()
    hot_labs = [{"name": name, "count": cnt} for name, cnt in hot_rows]

    return {
        "total_labs": total_labs,
        "available_labs": available_labs,
        "total_users": total_users,
        "total_reservations": total_reservations,
        "pending_reservations": pending,
        "today_reservations": today_count,
        "approved_reservations": approved,
        "total_equipments": int(total_equipments),
        "status_distribution": by_status,
        "trend": trend,
        "hot_labs": hot_labs,
    }
