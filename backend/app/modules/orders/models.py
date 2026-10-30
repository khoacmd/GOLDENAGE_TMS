import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.modules.master_data.models import TempClass


class TempGroup(StrEnum):
    """Nhóm nhiệt độ để tách đơn: hàng khô / hàng lạnh + đông."""

    DRY = "DRY"
    COLD = "COLD"

    @classmethod
    def of(cls, temp_class: TempClass) -> "TempGroup":
        return cls.DRY if temp_class == TempClass.DRY else cls.COLD


class OrderStatus(StrEnum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class OrderPartStatus(StrEnum):
    PENDING = "PENDING"
    PLANNED = "PLANNED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OrderSource(StrEnum):
    FILE = "FILE"
    API = "API"
    MANUAL = "MANUAL"


class SalesOrder(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "external_ref"),
        CheckConstraint("order_value >= 0", name="value_non_negative"),
    )

    external_ref: Mapped[str] = mapped_column(String(64))
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    delivery_point_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("delivery_points.id", ondelete="RESTRICT")
    )
    order_date: Mapped[date]
    requested_date: Mapped[date] = mapped_column(index=True)
    order_value: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    note: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[OrderStatus] = mapped_column(enum_type(OrderStatus), default=OrderStatus.OPEN)
    source: Mapped[OrderSource] = mapped_column(enum_type(OrderSource))

    lines: Mapped[list["SalesOrderLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="SalesOrderLine.line_no"
    )
    parts: Mapped[list["OrderPart"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="OrderPart.temp_group"
    )


class SalesOrderLine(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "sales_order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "line_no"),
        CheckConstraint("qty > 0", name="qty_positive"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_orders.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(SmallInteger)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    # Snapshot tại thời điểm nhận đơn: qty * trọng lượng đơn vị.
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    temp_group: Mapped[TempGroup] = mapped_column(enum_type(TempGroup))


class OrderPart(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Đơn vị lập kế hoạch: phần đơn theo nhóm nhiệt độ, luôn đi nguyên trên 1 chuyến."""

    __tablename__ = "order_parts"
    __table_args__ = (UniqueConstraint("order_id", "temp_group"),)

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_orders.id", ondelete="CASCADE"), index=True
    )
    temp_group: Mapped[TempGroup] = mapped_column(enum_type(TempGroup))
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    status: Mapped[OrderPartStatus] = mapped_column(
        enum_type(OrderPartStatus), default=OrderPartStatus.PENDING, index=True
    )
    attempt_count: Mapped[int] = mapped_column(SmallInteger, default=0)
