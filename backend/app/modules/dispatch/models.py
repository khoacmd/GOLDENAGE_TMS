import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.modules.identity.models import User
from app.modules.master_data.models import DeliveryPoint, Vehicle, Warehouse
from app.modules.orders.models import OrderPart


class TripOrderStatus(StrEnum):
    """Trạng thái lệnh giao."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PREPARED = "PREPARED"  # thủ kho đã soạn xong hàng (hàng vẫn ở kho)
    PICKED = "PICKED"  # thủ kho đã xác nhận xuất hàng
    DISPATCHED = "DISPATCHED"  # xe đã xuất phát
    CLOSED = "CLOSED"  # quản lý xác nhận kết thúc
    CANCELLED = "CANCELLED"


class TripDeliveryStatus(StrEnum):
    """Trạng thái giao của chuyến."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"  # không còn item PENDING


class TripSource(StrEnum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"


class ItemStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Trip(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Lệnh giao hàng = 1 chuyến (1 xe, 1 kho xuất, 1 lượt trong ngày)."""

    __tablename__ = "trips"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_trips_plan_date", "company_id", "plan_date"),
    )

    code: Mapped[str] = mapped_column(String(32))
    plan_date: Mapped[date]
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assistant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    trip_seq: Mapped[int] = mapped_column(SmallInteger, default=1)  # lượt thứ mấy của xe trong ngày
    source: Mapped[TripSource] = mapped_column(enum_type(TripSource), default=TripSource.MANUAL)
    note: Mapped[str | None] = mapped_column(String(1000))

    order_status: Mapped[TripOrderStatus] = mapped_column(
        enum_type(TripOrderStatus), default=TripOrderStatus.DRAFT
    )
    delivery_status: Mapped[TripDeliveryStatus] = mapped_column(
        enum_type(TripDeliveryStatus), default=TripDeliveryStatus.NOT_STARTED
    )
    total_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(0))
    total_value: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal(0))

    approved_at: Mapped[datetime | None]
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    prepared_at: Mapped[datetime | None]
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    picked_at: Mapped[datetime | None]
    picked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    dispatched_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))

    # Kết quả lập kế hoạch tự động (ước tính lúc lập; lệnh thủ công để trống).
    planning_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("planning_runs.id", ondelete="SET NULL"), index=True
    )
    planned_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    planned_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))
    planned_start: Mapped[datetime | None]
    planned_end: Mapped[datetime | None]

    vehicle: Mapped[Vehicle] = relationship(lazy="selectin")
    warehouse: Mapped[Warehouse] = relationship(lazy="selectin")
    driver: Mapped[User | None] = relationship(foreign_keys=[driver_id], lazy="selectin")
    assistant: Mapped[User | None] = relationship(foreign_keys=[assistant_id], lazy="selectin")
    stops: Mapped[list["TripStop"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TripStop.seq",
    )


class TripStop(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Điểm dừng; gắn điểm giao của khách hoặc điểm tự do (lệnh thủ công không theo đơn)."""

    __tablename__ = "trip_stops"
    __table_args__ = (
        UniqueConstraint("trip_id", "seq"),
        CheckConstraint(
            "delivery_point_id IS NOT NULL OR (address IS NOT NULL AND latitude IS NOT NULL "
            "AND longitude IS NOT NULL)",
            name="point_or_adhoc",
        ),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(SmallInteger)
    delivery_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("delivery_points.id", ondelete="RESTRICT")
    )
    # Điểm tự do: tên/địa chỉ/tọa độ nhập tay.
    name: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    note: Mapped[str | None] = mapped_column(String(500))

    trip: Mapped[Trip] = relationship(back_populates="stops")
    delivery_point: Mapped[DeliveryPoint | None] = relationship(lazy="selectin")
    items: Mapped[list["TripItem"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TripItem.created_at"
    )


class TripItem(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Hàng giao tại 1 điểm dừng: 1 phần đơn, hoặc mô tả tự do (lệnh thủ công)."""

    __tablename__ = "trip_items"
    __table_args__ = (
        CheckConstraint(
            "order_part_id IS NOT NULL OR description IS NOT NULL", name="part_or_desc"
        ),
        # Một phần đơn chỉ nằm trong 1 item đang hiệu lực (chờ giao hoặc đã giao thành công);
        # item hủy / giao thất bại không tính → phần đơn được xếp lại lệnh khác.
        Index(
            "uq_trip_items_active_part",
            "order_part_id",
            unique=True,
            postgresql_where=text("order_part_id IS NOT NULL AND status IN ('PENDING', 'SUCCESS')"),
        ),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    stop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trip_stops.id", ondelete="CASCADE"))
    order_part_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("order_parts.id", ondelete="RESTRICT")
    )
    description: Mapped[str | None] = mapped_column(String(500))
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(0))
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal(0))

    status: Mapped[ItemStatus] = mapped_column(enum_type(ItemStatus), default=ItemStatus.PENDING)
    reason: Mapped[str | None] = mapped_column(String(500))
    delivered_at: Mapped[datetime | None]
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    is_manual_update: Mapped[bool] = mapped_column(default=False)

    trip: Mapped[Trip] = relationship(lazy="raise")
    order_part: Mapped[OrderPart | None] = relationship(lazy="selectin")
