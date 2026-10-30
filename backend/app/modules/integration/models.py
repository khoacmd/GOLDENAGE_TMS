import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type


class ImportKind(StrEnum):
    PRODUCTS = "products"
    WAREHOUSES = "warehouses"
    VEHICLES = "vehicles"
    CUSTOMERS = "customers"
    ORDERS = "orders"
    INVENTORY = "inventory"


class ImportSource(StrEnum):
    FILE = "FILE"
    API = "API"


class ImportStatus(StrEnum):
    VALIDATED = "VALIDATED"  # dry-run hợp lệ, chưa ghi
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ImportJob(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Lịch sử mỗi lần import (file hoặc API)."""

    __tablename__ = "import_jobs"

    kind: Mapped[ImportKind] = mapped_column(enum_type(ImportKind))
    source: Mapped[ImportSource] = mapped_column(enum_type(ImportSource))
    filename: Mapped[str | None] = mapped_column(String(255))
    dry_run: Mapped[bool]
    status: Mapped[ImportStatus] = mapped_column(enum_type(ImportStatus))
    total_rows: Mapped[int]
    created_count: Mapped[int]
    updated_count: Mapped[int]
    error_count: Mapped[int]
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL")
    )


class ApiKey(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """API key cho hệ thống ngoài (bán hàng, kho) đẩy dữ liệu vào. Chỉ lưu hash."""

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    last_used_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
