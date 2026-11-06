import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.integration.models import ImportKind, ImportSource, ImportStatus


class ColumnOut(BaseModel):
    key: str
    label: str
    required: bool
    example: Any
    description: str


class ImportSpecOut(BaseModel):
    kind: ImportKind
    title: str
    description: str
    columns: list[ColumnOut]


class RowErrorOut(BaseModel):
    row: int
    column: str | None
    message: str


class ImportResultOut(BaseModel):
    job_id: uuid.UUID
    kind: ImportKind
    status: ImportStatus
    dry_run: bool
    total_rows: int
    created: int
    updated: int
    errors: list[RowErrorOut]


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ImportKind
    source: ImportSource
    filename: str | None
    dry_run: bool
    status: ImportStatus
    total_rows: int
    created_count: int
    updated_count: int
    error_count: int
    created_at: datetime


class IntegrationRequest(BaseModel):
    """Dữ liệu từ hệ thống ngoài: mỗi phần tử là 1 dòng, key theo cột template (vd. ma_hang)."""

    rows: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    dry_run: bool = False


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    # Chỉ trả về một lần khi tạo.
    api_key: str


class DmsOrdersConversionOut(BaseModel):
    """Kết quả chuyển đổi file đơn hàng DMS; file Excel theo template đơn hàng (base64)."""

    filename: str
    content_base64: str
    lines: int
    orders: int
    customers: int
    products: int
    total_value: int
    skipped_zero_qty: int
    skipped_returns: int
    first_delivery_date: date | None
    last_delivery_date: date | None
    warnings: list[str]


class DmsMasterConversionOut(BaseModel):
    """Lọc khách hàng / mặt hàng từ file DMS: chỉ mã chưa có trong hệ thống được đưa vào file."""

    filename: str
    content_base64: str
    total: int
    new: int
    existing: int
    incomplete: int
    warnings: list[str]
