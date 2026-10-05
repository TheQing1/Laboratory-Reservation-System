"""SQLAlchemy ORM 模型。"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    """统一使用服务器本地时间（与 date.today() 口径一致）。"""
    return datetime.now()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# --------------------------------------------------------------------------- 用户
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(50), default="")
    role: Mapped[str] = mapped_column(String(20), default="student")  # admin / student
    email: Mapped[str | None] = mapped_column(String(120), default=None)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    student_no: Mapped[str | None] = mapped_column(String(40), default=None)
    college: Mapped[str | None] = mapped_column(String(80), default=None)
    avatar: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="user", foreign_keys="Reservation.user_id"
    )

    @property
    def role_text(self) -> str:
        return {"admin": "管理员", "student": "学生"}.get(self.role, self.role)


# --------------------------------------------------------------------------- 实验室
class Lab(Base, TimestampMixin):
    __tablename__ = "labs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(50), default=None)
    building: Mapped[str | None] = mapped_column(String(80), default=None)
    room: Mapped[str | None] = mapped_column(String(40), default=None)
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    open_time: Mapped[str] = mapped_column(String(5), default="08:00")
    close_time: Mapped[str] = mapped_column(String(5), default="22:00")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    cover: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[str] = mapped_column(String(20), default="available")  # available / maintenance / disabled
    tags: Mapped[str | None] = mapped_column(String(255), default=None)

    equipments: Mapped[list["Equipment"]] = relationship(
        back_populates="lab", cascade="all, delete-orphan"
    )
    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="lab", cascade="all, delete-orphan"
    )
    documents: Mapped[list["LabDocument"]] = relationship(
        back_populates="lab", cascade="all, delete-orphan"
    )

    @property
    def status_text(self) -> str:
        return {"available": "可预约", "maintenance": "维护中", "disabled": "已停用"}.get(
            self.status, self.status
        )

    @property
    def location(self) -> str:
        parts = [p for p in (self.building, self.room) if p]
        return " ".join(parts)


# --------------------------------------------------------------------------- 设备
class Equipment(Base, TimestampMixin):
    __tablename__ = "equipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="normal")  # normal / repair / scrapped
    spec: Mapped[str | None] = mapped_column(String(255), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    lab: Mapped["Lab"] = relationship(back_populates="equipments")

    @property
    def status_text(self) -> str:
        return {"normal": "正常", "repair": "维修中", "scrapped": "已报废"}.get(self.status, self.status)


# --------------------------------------------------------------------------- 预约
class Reservation(Base, TimestampMixin):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id", ondelete="CASCADE"), index=True)
    booking_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[str] = mapped_column(String(5))  # HH:MM
    end_time: Mapped[str] = mapped_column(String(5))
    purpose: Mapped[str] = mapped_column(String(255), default="")
    people_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending 待审核 / approved 已通过 / rejected 已驳回 / cancelled 已取消 / finished 已完成
    review_remark: Mapped[str | None] = mapped_column(String(255), default=None)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    user: Mapped["User"] = relationship(back_populates="reservations", foreign_keys=[user_id])
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewer_id])
    lab: Mapped["Lab"] = relationship(back_populates="reservations")

    STATUS_TEXT = {
        "pending": "待审核",
        "approved": "已通过",
        "rejected": "已驳回",
        "cancelled": "已取消",
        "finished": "已完成",
    }

    @property
    def status_text(self) -> str:
        return self.STATUS_TEXT.get(self.status, self.status)

    @property
    def time_range(self) -> str:
        return f"{self.start_time}-{self.end_time}"


class ReservationSlot(Base):
    """预约槽位：把「时间重叠」下沉成数据库唯一约束，保证并发下不会重复预约。

    每条有效预约（pending / approved）按 30 分钟粒度占用若干槽位，
    (lab_id, booking_date, slot_minute) 唯一。取消 / 驳回 / 删除时释放，
    因此两个请求同时抢同一时段时，只有一个能写入成功。
    """

    __tablename__ = "reservation_slots"
    __table_args__ = (
        UniqueConstraint("lab_id", "booking_date", "slot_minute", name="uq_slot_lab_date_minute"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id", ondelete="CASCADE"), index=True)
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"), index=True
    )
    booking_date: Mapped[date] = mapped_column(Date, index=True)
    slot_minute: Mapped[int] = mapped_column(Integer)  # 当天 00:00 起的分钟数
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# --------------------------------------------------------------------------- 知识库
class LabDocument(Base, TimestampMixin):
    """实验室知识库文档（RAG 检索来源）。"""

    __tablename__ = "lab_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lab_id: Mapped[int | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), default=None, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), default="规章制度")
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200), default=None)

    lab: Mapped["Lab | None"] = relationship(back_populates="documents")


class DocChunk(Base):
    """文档切片 + 向量（本地向量库）。"""

    __tablename__ = "doc_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("lab_documents.id", ondelete="CASCADE"), index=True
    )
    lab_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str] = mapped_column(Text)  # JSON 数组
    dim: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------------- AI 会话
class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="新的对话")

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user / assistant / tool
    content: Mapped[str] = mapped_column(Text, default="")
    # 记录工具调用过程，便于前端"过程可见"
    tool_name: Mapped[str | None] = mapped_column(String(60), default=None)
    tool_args: Mapped[str | None] = mapped_column(Text, default=None)
    tool_result: Mapped[str | None] = mapped_column(Text, default=None)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
