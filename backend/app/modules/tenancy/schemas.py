import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CompanyAdminInput(BaseModel):
    """Admin công ty: dùng tài khoản có sẵn theo username, hoặc tạo mới.

    Tạo mới cần `password` và `full_name`.
    """

    username: str = Field(min_length=3, max_length=64)
    password: str | None = Field(default=None, min_length=8)
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None


class CompanyCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    admin: CompanyAdminInput


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    is_active: bool
    created_at: datetime


class CompanySettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    working_weekdays: list[int]
    shift_start: time
    shift_end: time
    cutover_time: time
    timezone: str
