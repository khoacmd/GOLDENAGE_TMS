import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.modules.master_data.models import CostAllocationMethod


class DistanceSource(StrEnum):
    ODOMETER = "ODOMETER"  # số công-tơ-mét lúc xuất phát / kết thúc
    MANUAL = "MANUAL"  # quản lý nhập số km
    PLANNED = "PLANNED"  # km kế hoạch của bộ tối ưu
    ESTIMATE = "ESTIMATE"  # ước lượng theo tuyến điểm dừng


class TripCost(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Chi phí thực tế của 1 chuyến; đơn giá & phương pháp phân bổ chụp lại lúc ghi nhận."""

    __tablename__ = "trip_costs"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), unique=True
    )
    odometer_start: Mapped[Decimal | None] = mapped_column(Numeric(10, 1))
    odometer_end: Mapped[Decimal | None] = mapped_column(Numeric(10, 1))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    distance_source: Mapped[DistanceSource] = mapped_column(enum_type(DistanceSource))
    cost_per_km: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    distance_cost: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    extra_cost: Mapped[Decimal] = mapped_column(Numeric(14, 0), default=Decimal(0))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    allocation_method: Mapped[CostAllocationMethod] = mapped_column(enum_type(CostAllocationMethod))
    note: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    recorded_at: Mapped[datetime]

    allocations: Mapped[list["CostAllocation"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class CostAllocation(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Phần chi phí chuyến phân bổ về 1 mục hàng (phần đơn) của chuyến."""

    __tablename__ = "cost_allocations"

    trip_cost_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trip_costs.id", ondelete="CASCADE"), index=True
    )
    trip_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trip_items.id", ondelete="CASCADE"))
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_orders.id", ondelete="CASCADE"), index=True
    )
    basis: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # giá trị làm căn cứ phân bổ
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 0))
