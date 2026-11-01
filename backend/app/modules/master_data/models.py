import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    ARRAY,
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

from app.core.models import (
    Base,
    GeoPointMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)


class VehicleType(StrEnum):
    CAR = "CAR"
    MOTORBIKE = "MOTORBIKE"


class VehicleRequirement(StrEnum):
    """Yêu cầu loại xe của khách hàng."""

    CAR = "CAR"
    MOTORBIKE = "MOTORBIKE"
    ANY = "ANY"


class CargoClass(StrEnum):
    """Loại hàng ưu tiên của xe."""

    DRY_ONLY = "DRY_ONLY"
    COLD_ONLY = "COLD_ONLY"  # chỉ hàng đông/lạnh
    ANY = "ANY"


class CostAllocationMethod(StrEnum):
    """Cách phân bổ chi phí chuyến về từng đơn."""

    ORDER_VALUE = "ORDER_VALUE"
    DISTANCE = "DISTANCE"
    WEIGHT = "WEIGHT"
    PER_TRIP = "PER_TRIP"


class TempClass(StrEnum):
    DRY = "DRY"
    CHILLED = "CHILLED"
    FROZEN = "FROZEN"


class Warehouse(UUIDPrimaryKeyMixin, TenantMixin, GeoPointMixin, TimestampMixin, Base):
    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_warehouses_location", "location", postgresql_using="gist"),
    )

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


class Vehicle(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        UniqueConstraint("company_id", "plate_no"),
        CheckConstraint("capacity_kg > 0", name="capacity_positive"),
        CheckConstraint("cost_per_km >= 0", name="cost_non_negative"),
    )

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    plate_no: Mapped[str] = mapped_column(String(20))
    vehicle_type: Mapped[VehicleType] = mapped_column(enum_type(VehicleType))
    capacity_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    cost_per_km: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    requires_assistant: Mapped[bool] = mapped_column(default=False)
    cargo_class: Mapped[CargoClass] = mapped_column(enum_type(CargoClass))
    cost_allocation_method: Mapped[CostAllocationMethod] = mapped_column(
        enum_type(CostAllocationMethod)
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    warehouse_links: Mapped[list["VehicleWarehouse"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def warehouse_ids(self) -> list[uuid.UUID]:
        return sorted(link.warehouse_id for link in self.warehouse_links)


class VehicleWarehouse(TenantMixin, Base):
    """Kho xe được phép lấy hàng."""

    __tablename__ = "vehicle_warehouses"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), primary_key=True
    )


class Customer(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        CheckConstraint(
            "deliveries_per_week IS NULL OR deliveries_per_week BETWEEN 1 AND 7",
            name="deliveries_per_week_range",
        ),
    )

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    required_vehicle_type: Mapped[VehicleRequirement] = mapped_column(
        enum_type(VehicleRequirement), default=VehicleRequirement.ANY
    )
    sales_rep: Mapped[str | None] = mapped_column(String(255))
    # ISO weekday 1 = Thứ 2 ... 7 = Chủ nhật; rỗng = không cố định.
    delivery_weekdays: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=list)
    deliveries_per_week: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    delivery_points: Mapped[list["DeliveryPoint"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DeliveryPoint.code",
    )


class DeliveryPoint(UUIDPrimaryKeyMixin, TenantMixin, GeoPointMixin, TimestampMixin, Base):
    __tablename__ = "delivery_points"
    __table_args__ = (
        UniqueConstraint("customer_id", "code"),
        Index("ix_delivery_points_location", "location", postgresql_using="gist"),
        # Mỗi khách hàng tối đa 1 điểm giao mặc định.
        Index(
            "uq_delivery_points_default",
            "customer_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    customer: Mapped[Customer] = relationship(back_populates="delivery_points", lazy="joined")


class CustomerContact(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Người liên hệ của khách hàng (chủ) hoặc của 1 điểm giao - đối tượng dùng Zalo Mini App.

    `delivery_point_id` trống = liên hệ chủ: xem mọi đơn của khách hàng kèm giá trị;
    có giá trị = chỉ xem đơn đến điểm giao đó, không thấy giá trị (D35).
    """

    __tablename__ = "customer_contacts"
    __table_args__ = (
        Index(
            "uq_customer_contacts_phone",
            "customer_id",
            "delivery_point_id",
            "phone",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    delivery_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("delivery_points.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    # Chuẩn hóa dạng 0xxxxxxxxx (xem `normalize_phone`).
    phone: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    delivery_point: Mapped["DeliveryPoint | None"] = relationship(lazy="joined")

    @property
    def delivery_point_code(self) -> str | None:
        return self.delivery_point.code if self.delivery_point else None


class Product(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        CheckConstraint("weight_kg >= 0", name="weight_non_negative"),
    )

    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    temp_class: Mapped[TempClass] = mapped_column(enum_type(TempClass))
    uom: Mapped[str] = mapped_column(String(32))
    # Trọng lượng 1 đơn vị tính (kg).
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
