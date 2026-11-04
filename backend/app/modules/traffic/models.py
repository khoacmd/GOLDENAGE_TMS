import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type


class VehicleClass(StrEnum):
    """Nhóm xe theo quy định lưu hành."""

    TRUCK = "TRUCK"
    VAN = "VAN"
    PICKUP = "PICKUP"
    MOTORBIKE = "MOTORBIKE"


class WeightBasis(StrEnum):
    """Số dùng để xếp xe vào quy tắc."""

    PAYLOAD = "PAYLOAD"  # trọng tải hàng (`vehicles.capacity_kg`)
    GROSS = "GROSS"  # tổng trọng lượng xe + hàng (`vehicles.gross_weight_kg`)


class TrafficZone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Vùng hạn chế theo quy định nhà nước. Dùng chung mọi công ty, không áp RLS (như `companies`);
    công ty vận hành TMS nạp từ file bằng lệnh `load-traffic-zones`."""

    __tablename__ = "traffic_zones"
    __table_args__ = (Index("ix_traffic_zones_boundary", "boundary", postgresql_using="gist"),)

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    boundary: Mapped[Any] = mapped_column(
        Geography("POLYGON", srid=4326, spatial_index=False), deferred=True
    )
    legal_ref: Mapped[str | None] = mapped_column(String(255))
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]

    rules: Mapped[list["TrafficRule"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class TrafficRule(UUIDPrimaryKeyMixin, Base):
    """Giờ một nhóm xe được hoạt động trong vùng, theo khoảng khối lượng (`min_kg`, `max_kg`].

    `windows`: None = không giới hạn; rỗng = chỉ được vào khi có văn bản chấp thuận. Nhóm xe không
    có quy tắc khớp thì không bị giới hạn (riêng xe Van xem `service._rule_for`).
    """

    __tablename__ = "traffic_rules"

    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("traffic_zones.id", ondelete="CASCADE"), index=True
    )
    vehicle_class: Mapped[VehicleClass] = mapped_column(enum_type(VehicleClass))
    weight_basis: Mapped[WeightBasis] = mapped_column(enum_type(WeightBasis))
    min_kg: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal(0)
    )  # không tính mốc này
    max_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    max_inclusive: Mapped[bool] = mapped_column(default=True)
    windows: Mapped[list[list[str]] | None] = mapped_column(JSONB(none_as_null=True))


class VehiclePermit(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Văn bản chấp thuận cho xe hoạt động ngoài khung giờ. Lưu do công ty nhập, hệ thống không
    kiểm tra được tính hợp lệ hay giới hạn tuyến đường của văn bản."""

    __tablename__ = "vehicle_permits"
    __table_args__ = (UniqueConstraint("company_id", "vehicle_id", "zone_id", "document_no"),)

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("traffic_zones.id", ondelete="RESTRICT"))
    document_no: Mapped[str] = mapped_column(String(64))
    issuer: Mapped[str | None] = mapped_column(String(255))
    valid_from: Mapped[date]
    valid_to: Mapped[date]
    windows: Mapped[list[list[str]]] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(String(500))
