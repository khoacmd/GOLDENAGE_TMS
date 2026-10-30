import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.modules.dispatch.models import ItemStatus


class DeliveryConfirmation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Mỗi lần nhân viên giao hàng xác nhận kết quả (kể cả bị từ chối do vi phạm quy tắc)."""

    __tablename__ = "delivery_confirmations"
    __table_args__ = (UniqueConstraint("company_id", "client_id"),)

    # Do app sinh, dùng để gửi lại khi mất mạng mà không ghi trùng.
    client_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trip_items.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL")
    )
    status: Mapped[ItemStatus] = mapped_column(enum_type(ItemStatus))
    reason: Mapped[str | None] = mapped_column(String(500))
    device_time: Mapped[datetime]
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    is_mock_location: Mapped[bool] = mapped_column(default=False)
    distance_m: Mapped[Decimal | None] = mapped_column(Numeric(10, 1))
    accepted: Mapped[bool]
    violations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rule_check: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    photos: Mapped[list["DeliveryPhoto"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class DeliveryPhoto(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "delivery_photos"

    confirmation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("delivery_confirmations.id", ondelete="CASCADE"), index=True
    )
    object_key: Mapped[str] = mapped_column(String(255))
