import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.devices.models import DeviceStatus, DeviceType, PaperSize, PrinterConnection


class _DeviceFields(BaseModel):
    identifier: str | None = Field(default=None, max_length=128)
    status: DeviceStatus = DeviceStatus.ACTIVE
    warehouse_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    connection: PrinterConnection | None = None
    address: str | None = Field(default=None, max_length=255)
    paper_size: PaperSize | None = None
    note: str | None = Field(default=None, max_length=500)


class DeviceCreate(_DeviceFields):
    device_type: DeviceType
    name: str = Field(min_length=1, max_length=255)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    identifier: str | None = Field(default=None, max_length=128)
    status: DeviceStatus | None = None
    warehouse_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    connection: PrinterConnection | None = None
    address: str | None = Field(default=None, max_length=255)
    paper_size: PaperSize | None = None
    note: str | None = Field(default=None, max_length=500)


class DeviceOut(_DeviceFields):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_type: DeviceType
    name: str
    platform: str | None
    model: str | None
    os_version: str | None
    app_version: str | None
    last_seen_at: datetime | None
    created_at: datetime


class DeviceRegister(BaseModel):
    """App mobile tự đăng ký khi đăng nhập / mở app."""

    identifier: str = Field(min_length=8, max_length=128)
    platform: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=128)
    os_version: str | None = Field(default=None, max_length=64)
    app_version: str | None = Field(default=None, max_length=32)


class RegisteredDevice(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: DeviceStatus
