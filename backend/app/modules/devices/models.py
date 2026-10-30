import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type


class DeviceType(StrEnum):
    PC = "PC"
    MOBILE = "MOBILE"
    PRINTER = "PRINTER"


class DeviceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"  # mobile tự đăng ký, chờ admin duyệt (khi công ty bật duyệt thiết bị)
    BLOCKED = "BLOCKED"


class PrinterConnection(StrEnum):
    NETWORK = "NETWORK"
    USB = "USB"
    BLUETOOTH = "BLUETOOTH"


class PaperSize(StrEnum):
    A4 = "A4"
    A5 = "A5"
    K80 = "K80"  # giấy in nhiệt khổ 80 mm


class Device(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Thiết bị của công ty: máy tính, điện thoại lái xe (tự đăng ký từ app), máy in."""

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("company_id", "identifier"),)

    device_type: Mapped[DeviceType] = mapped_column(enum_type(DeviceType))
    name: Mapped[str] = mapped_column(String(255))
    # Mobile: mã cài đặt do app sinh; PC/máy in: mã tài sản, số serial... (tùy chọn).
    identifier: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[DeviceStatus] = mapped_column(
        enum_type(DeviceStatus), default=DeviceStatus.ACTIVE
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="SET NULL")
    )
    # Mobile: người dùng gần nhất; PC: người dùng được giao.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    platform: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    os_version: Mapped[str | None] = mapped_column(String(64))
    app_version: Mapped[str | None] = mapped_column(String(32))
    connection: Mapped[PrinterConnection | None] = mapped_column(enum_type(PrinterConnection))
    address: Mapped[str | None] = mapped_column(String(255))  # IP/hostname, tên cổng...
    paper_size: Mapped[PaperSize | None] = mapped_column(enum_type(PaperSize))
    note: Mapped[str | None] = mapped_column(String(500))
    last_seen_at: Mapped[datetime | None]
