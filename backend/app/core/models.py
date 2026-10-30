import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Any, ClassVar

from geoalchemy2 import Geography
from sqlalchemy import Computed, DateTime, Enum, ForeignKey, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TenantMixin:
    """Bảng nghiệp vụ thuộc một công ty. Migration tạo bảng phải gọi `enable_tenant_rls`."""

    @declared_attr
    def company_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)


def enum_type(enum_cls: type[PyEnum]) -> Enum:
    """Lưu enum dạng VARCHAR + CHECK (dễ thêm giá trị mới hơn enum native của Postgres)."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [m.value for m in cls],
        name=enum_cls.__name__.lower(),
    )


class GeoPointMixin:
    """Tọa độ nhập dạng vĩ độ/kinh độ; cột `location` (geography) sinh tự động cho truy vấn
    khoảng cách (PostGIS). Cần index GiST: `Index(..., "location", postgresql_using="gist")`."""

    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    location: Mapped[Any] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False),
        Computed(
            "ST_SetSRID(ST_MakePoint(longitude::float8, latitude::float8), 4326)::geography",
            persisted=True,
        ),
        deferred=True,
    )
