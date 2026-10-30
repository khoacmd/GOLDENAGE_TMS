import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.dispatch.models import ItemStatus


class ConfirmIn(BaseModel):
    """Nhân viên giao hàng xác nhận kết quả 1 mục hàng (gửi từ app, có thể gửi lại khi offline)."""

    client_id: uuid.UUID
    status: ItemStatus = Field(description="SUCCESS hoặc FAILED")
    reason: str | None = Field(default=None, max_length=500)
    device_time: datetime = Field(description="Thời điểm thao tác trên thiết bị (có múi giờ)")
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    accuracy_m: Decimal | None = Field(default=None, ge=0)
    is_mock_location: bool = False
    photo_keys: list[str] = Field(default=[], max_length=5)
    device_id: str | None = Field(
        default=None, max_length=128, description="Mã cài đặt của app (đã đăng ký thiết bị)"
    )


class PhotoOut(BaseModel):
    key: str
    url: str


class ConfirmationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    item_id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID | None
    status: ItemStatus
    reason: str | None
    device_time: datetime
    created_at: datetime
    latitude: Decimal | None
    longitude: Decimal | None
    accuracy_m: Decimal | None
    is_mock_location: bool
    distance_m: Decimal | None
    accepted: bool
    violations: list[str]
    photos: list[PhotoOut] = []


class UploadedPhoto(BaseModel):
    key: str
