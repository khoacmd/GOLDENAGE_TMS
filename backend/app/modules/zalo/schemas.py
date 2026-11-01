import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ZaloStatus(StrEnum):
    NOT_INVITED = "NOT_INVITED"  # chưa có mã / mã đã hết hạn
    PENDING = "PENDING"  # đã cấp mã, chờ nhập trên Zalo Mini App
    ACTIVE = "ACTIVE"  # đã liên kết Zalo


class ZaloLinkInfo(BaseModel):
    status: ZaloStatus = ZaloStatus.NOT_INVITED
    display_name: str | None = None  # tên Zalo khi kích hoạt
    activated_at: datetime | None = None
    code_expires_at: datetime | None = None  # hạn của mã đang chờ


class ActivationCodeOut(BaseModel):
    """Mã chỉ hiển thị 1 lần lúc tạo (server chỉ lưu hash)."""

    code: str  # dạng XXXX-XXXX
    expires_at: datetime
    link: str | None  # mở Zalo Mini App kèm mã (dùng làm QR); None nếu chưa cấu hình


class ZaloTarget(BaseModel):
    contact_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
