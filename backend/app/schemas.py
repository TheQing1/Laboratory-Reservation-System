"""Pydantic 请求/响应模型。"""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _check_email(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    if not EMAIL_RE.match(v):
        raise ValueError("邮箱格式不正确")
    return v


def _check_time(v: str) -> str:
    if not TIME_RE.match(v):
        raise ValueError("时间格式应为 HH:MM")
    return v


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------- 认证
class LoginIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=64)


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=64)
    name: str = Field("", max_length=50)
    email: str | None = None
    phone: str | None = Field(None, max_length=20)
    student_no: str | None = Field(None, max_length=40)
    college: str | None = Field(None, max_length=80)

    _v_email = field_validator("email")(_check_email)


class TokenOut(BaseModel):
    token: str
    user: "UserOut"


# --------------------------------------------------------------------- 用户
class UserBase(BaseModel):
    name: str = Field("", max_length=50)
    email: str | None = None
    phone: str | None = Field(None, max_length=20)
    student_no: str | None = Field(None, max_length=40)
    college: str | None = Field(None, max_length=80)

    _v_email = field_validator("email")(_check_email)


class UserCreate(UserBase):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=64)
    role: str = "student"
    is_active: bool = True
    avatar: str | None = None


class UserUpdate(UserBase):
    role: str | None = None
    is_active: bool | None = None
    avatar: str | None = None


class ProfileUpdate(UserBase):
    avatar: str | None = None


class PasswordUpdate(BaseModel):
    old_password: str = Field(..., min_length=4, max_length=64)
    new_password: str = Field(..., min_length=6, max_length=64)


class UserOut(ORMModel):
    id: int
    username: str
    name: str
    role: str
    role_text: str
    email: str | None = None
    phone: str | None = None
    student_no: str | None = None
    college: str | None = None
    avatar: str | None = None
    is_active: bool
    created_at: object | None = None


# --------------------------------------------------------------------- 实验室
class LabBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str | None = Field(None, max_length=50)
    building: str | None = Field(None, max_length=80)
    room: str | None = Field(None, max_length=40)
    capacity: int = Field(0, ge=0, le=1000)
    open_time: str = "08:00"
    close_time: str = "22:00"
    description: str | None = None
    cover: str | None = None
    status: str = "available"
    tags: str | None = Field(None, max_length=255)

    _v_open = field_validator("open_time")(_check_time)
    _v_close = field_validator("close_time")(_check_time)

    @field_validator("status")
    @classmethod
    def _v_status(cls, v: str) -> str:
        if v not in ("available", "maintenance", "disabled"):
            raise ValueError("状态只能是 available/maintenance/disabled")
        return v


class LabCreate(LabBase):
    pass


class LabUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    code: str | None = None
    building: str | None = None
    room: str | None = None
    capacity: int | None = Field(None, ge=0, le=1000)
    open_time: str | None = None
    close_time: str | None = None
    description: str | None = None
    cover: str | None = None
    status: str | None = None
    tags: str | None = None

    _v_open = field_validator("open_time")(lambda v: _check_time(v) if v else v)
    _v_close = field_validator("close_time")(lambda v: _check_time(v) if v else v)


class LabOut(ORMModel):
    id: int
    name: str
    code: str | None = None
    building: str | None = None
    room: str | None = None
    location: str = ""
    capacity: int
    open_time: str
    close_time: str
    description: str | None = None
    cover: str | None = None
    status: str
    status_text: str
    tags: str | None = None
    equipments: list["EquipmentOut"] = []


# --------------------------------------------------------------------- 设备
class EquipmentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    model: str | None = Field(None, max_length=100)
    quantity: int = Field(1, ge=0, le=10000)
    status: str = "normal"
    spec: str | None = Field(None, max_length=255)
    description: str | None = None

    @field_validator("status")
    @classmethod
    def _v_status(cls, v: str) -> str:
        if v not in ("normal", "repair", "scrapped"):
            raise ValueError("状态只能是 normal/repair/scrapped")
        return v


class EquipmentCreate(EquipmentBase):
    lab_id: int


class EquipmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    model: str | None = None
    quantity: int | None = Field(None, ge=0, le=10000)
    status: str | None = None
    spec: str | None = None
    description: str | None = None
    lab_id: int | None = None


class EquipmentOut(ORMModel):
    id: int
    lab_id: int
    name: str
    model: str | None = None
    quantity: int
    status: str
    status_text: str
    spec: str | None = None
    description: str | None = None
    lab_name: str | None = None


# --------------------------------------------------------------------- 预约
class ReservationCreate(BaseModel):
    lab_id: int
    booking_date: str = Field(..., description="YYYY-MM-DD")
    start_time: str
    end_time: str
    purpose: str = Field("", max_length=255)
    people_count: int = Field(1, ge=1, le=1000)

    _v_start = field_validator("start_time")(_check_time)
    _v_end = field_validator("end_time")(_check_time)

    @field_validator("booking_date")
    @classmethod
    def _v_date(cls, v: str) -> str:
        import datetime as _dt

        try:
            _dt.date.fromisoformat(v)
        except ValueError:
            raise ValueError("日期格式应为 YYYY-MM-DD") from None
        return v


class ReservationReview(BaseModel):
    status: str = Field(..., description="approved / rejected")
    review_remark: str | None = Field(None, max_length=255)

    @field_validator("status")
    @classmethod
    def _v_status(cls, v: str) -> str:
        if v not in ("approved", "rejected"):
            raise ValueError("审核结果只能是 approved 或 rejected")
        return v


class ReservationOut(ORMModel):
    id: int
    user_id: int
    lab_id: int
    lab_name: str | None = None
    username: str | None = None
    user_name: str | None = None
    booking_date: object
    start_time: str
    end_time: str
    time_range: str = ""
    purpose: str
    people_count: int
    status: str
    status_text: str
    review_remark: str | None = None
    reviewed_at: object | None = None
    created_at: object | None = None


# --------------------------------------------------------------------- 知识库 / AI
class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: str = Field("规章制度", max_length=40)
    content: str = Field(..., min_length=1)
    source: str | None = None
    lab_id: int | None = None


class DocumentUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    content: str | None = None
    source: str | None = None
    lab_id: int | None = None


class DocumentOut(ORMModel):
    id: int
    lab_id: int | None = None
    title: str
    category: str
    content: str
    source: str | None = None
    created_at: object | None = None


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: int | None = None
    use_rag: bool = True
    use_tools: bool = True


class ChatMessageOut(ORMModel):
    id: int
    role: str
    content: str
    tool_name: str | None = None
    tool_args: str | None = None
    tool_result: str | None = None
    created_at: object | None = None


class ChatSessionOut(ORMModel):
    id: int
    title: str
    created_at: object | None = None
    updated_at: object | None = None


TokenOut.model_rebuild()
LabOut.model_rebuild()
