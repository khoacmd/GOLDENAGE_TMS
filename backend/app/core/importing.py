"""Khung import dữ liệu theo dòng: dùng chung cho upload file và API tích hợp.

Mỗi loại dữ liệu khai báo một `ImportSpec`: danh sách cột (template), model Pydantic cho
một dòng, và hàm `apply` ghi vào DB. Pipeline (app.modules.integration.service):
  1. Đọc dòng thô (dict key → giá trị), map header → key theo `normalize_token`.
  2. Validate từng dòng bằng `row_model` → lỗi theo dòng/cột.
  3. Không có lỗi → gọi `apply` trong savepoint; `apply` có thể trả thêm lỗi nghiệp vụ
     (mã không tồn tại, trùng...). Có lỗi → rollback toàn bộ (all-or-nothing).
"""

import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.parsing import blank_to_none, normalize_token
from app.modules.identity.models import CompanyRole


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    required: bool = False
    example: Any = None
    description: str = ""


class RowModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


@dataclass
class RowError:
    row: int
    column: str | None
    message: str


@dataclass
class ApplyResult:
    created: int = 0
    updated: int = 0
    errors: list[RowError] = field(default_factory=list)


@dataclass(frozen=True)
class ImportContext:
    company_id: uuid.UUID
    source: str  # "FILE" | "API"


@dataclass(frozen=True)
class ParsedRow[R: RowModel]:
    row_no: int
    data: R


ApplyFn = Callable[[AsyncSession, ImportContext, Sequence[ParsedRow[Any]]], Awaitable[ApplyResult]]


@dataclass(frozen=True)
class ImportSpec:
    kind: str
    title: str
    description: str
    columns: list[Column]
    row_model: type[RowModel]
    apply: ApplyFn
    allowed_roles: frozenset[CompanyRole]

    def header_map(self) -> dict[str, str]:
        """Header đã chuẩn hóa → key. Chấp nhận cả nhãn tiếng Việt và key."""
        mapping: dict[str, str] = {}
        for col in self.columns:
            mapping[normalize_token(col.key)] = col.key
            mapping[normalize_token(col.label)] = col.key
        return mapping

    def label_of(self, key: str) -> str:
        return next((c.label for c in self.columns if c.key == key), key)


_PYDANTIC_MESSAGES = {
    "missing": "Bắt buộc nhập",
    "string_type": "Phải là chuỗi ký tự",
    "string_too_long": "Quá dài (tối đa {max_length} ký tự)",
    "string_too_short": "Bắt buộc nhập",
    "greater_than": "Phải lớn hơn {gt}",
    "greater_than_equal": "Phải lớn hơn hoặc bằng {ge}",
    "less_than_equal": "Phải nhỏ hơn hoặc bằng {le}",
    "int_parsing": "Phải là số nguyên",
    "decimal_parsing": "Phải là số",
    "value_error": "{error}",
}


def validate_row[R: RowModel](
    spec: ImportSpec, row_no: int, raw: dict[str, Any], model: type[R]
) -> tuple[R | None, list[RowError]]:
    # Ô trống được coi như không nhập → cột bắt buộc báo "Bắt buộc nhập".
    cleaned = {k: v for k, v in raw.items() if blank_to_none(v) is not None}
    try:
        return model.model_validate(cleaned), []
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            key = str(err["loc"][0]) if err["loc"] else None
            template = _PYDANTIC_MESSAGES.get(err["type"])
            ctx = {k: str(v) for k, v in (err.get("ctx") or {}).items()}
            message = template.format(**ctx) if template else err["msg"]
            errors.append(RowError(row_no, spec.label_of(key) if key else None, message))
        return None, errors


def duplicate_errors(
    rows: Sequence[ParsedRow[Any]], key_fn: Callable[[Any], Any], column: str
) -> list[RowError]:
    """Báo lỗi khi cùng khóa xuất hiện ở nhiều dòng (với loại dữ liệu 1 dòng = 1 bản ghi)."""
    seen: dict[Any, int] = {}
    errors = []
    for row in rows:
        key = key_fn(row.data)
        if key in seen:
            errors.append(RowError(row.row_no, column, f"Trùng với dòng {seen[key]}"))
        else:
            seen[key] = row.row_no
    return errors


async def load_by_codes[M](
    session: AsyncSession, model: type[M], codes: Iterable[str]
) -> dict[str, M]:
    """Bản ghi (trong công ty hiện tại, nhờ RLS) theo mã, key là mã viết thường."""
    lowered = {c.lower() for c in codes}
    if not lowered:
        return {}
    code_col = model.code  # type: ignore[attr-defined]
    rows = await session.scalars(select(model).where(func.lower(code_col).in_(lowered)))
    return {row.code.lower(): row for row in rows}  # type: ignore[attr-defined]
