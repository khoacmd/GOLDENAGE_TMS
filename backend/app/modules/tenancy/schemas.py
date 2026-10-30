import uuid
import zoneinfo
from datetime import datetime, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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


class DeliveryRules(BaseModel):
    """Điều kiện cho nhân viên giao hàng xác nhận kết quả giao."""

    confirm_time_rule: bool
    confirm_grace_minutes: int = Field(ge=0, le=720)
    confirm_geofence: bool
    confirm_radius_m: int = Field(ge=20, le=10_000)
    photo_required_success: bool
    photo_required_failed: bool
    offline_max_delay_minutes: int = Field(ge=5, le=24 * 60)
    require_device_approval: bool


class PlanningSettings(BaseModel):
    """Tham số lập kế hoạch tự động."""

    auto_plan_enabled: bool
    service_minutes: int = Field(ge=0, le=240)
    turnaround_minutes: int = Field(ge=0, le=240)
    max_trips_per_vehicle: int = Field(ge=1, le=10)
    trip_fixed_cost: int = Field(ge=0, le=100_000_000)
    planning_time_limit_s: int = Field(ge=1, le=300)


class CompanySettingsOut(DeliveryRules, PlanningSettings):
    model_config = ConfigDict(from_attributes=True)

    working_weekdays: list[int]
    shift_start: time
    shift_end: time
    cutover_time: time
    timezone: str


class CompanySettingsUpdate(BaseModel):
    working_weekdays: list[Annotated[int, Field(ge=1, le=7)]] | None = Field(
        default=None, min_length=1
    )
    shift_start: time | None = None
    shift_end: time | None = None
    cutover_time: time | None = None
    timezone: str | None = None
    confirm_time_rule: bool | None = None
    confirm_grace_minutes: int | None = Field(default=None, ge=0, le=720)
    confirm_geofence: bool | None = None
    confirm_radius_m: int | None = Field(default=None, ge=20, le=10_000)
    photo_required_success: bool | None = None
    photo_required_failed: bool | None = None
    offline_max_delay_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    require_device_approval: bool | None = None
    auto_plan_enabled: bool | None = None
    service_minutes: int | None = Field(default=None, ge=0, le=240)
    turnaround_minutes: int | None = Field(default=None, ge=0, le=240)
    max_trips_per_vehicle: int | None = Field(default=None, ge=1, le=10)
    trip_fixed_cost: int | None = Field(default=None, ge=0, le=100_000_000)
    planning_time_limit_s: int | None = Field(default=None, ge=1, le=300)

    @field_validator("working_weekdays")
    @classmethod
    def _dedupe(cls, value: list[int] | None) -> list[int] | None:
        return sorted(set(value)) if value is not None else None

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, value: str | None) -> str | None:
        if value is not None and value not in zoneinfo.available_timezones():
            raise ValueError("Múi giờ không hợp lệ")
        return value
