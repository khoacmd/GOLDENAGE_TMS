"""Chuyển đổi giá trị ô Excel/CSV/JSON sang kiểu Python, thông báo lỗi tiếng Việt.

Dùng làm `BeforeValidator` trong model dòng import (xem `app.core.importing`).
"""

import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Any

from pydantic import BeforeValidator, StringConstraints


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def normalize_token(value: str) -> str:
    """'Mã hàng (*)' → 'ma hang'; 'ma_hang' → 'ma hang'; 'Xe máy' → 'xe may'."""
    text = strip_accents(value).lower()
    text = text.replace("(*)", "").replace("*", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _to_str(value: Any) -> Any:
    value = blank_to_none(value)
    if isinstance(value, float) and value.is_integer():
        # Excel lưu mã số (vd. 1001) dạng float.
        return str(int(value))
    if isinstance(value, int | Decimal):
        return str(value)
    return value


def _to_decimal(value: Any) -> Decimal | None:
    value = blank_to_none(value)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Phải là số")
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = str(value).replace(" ", "")
    # Chấp nhận dấu phẩy thập phân khi không có dấu chấm: "1,5" → 1.5
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"'{value}' không phải là số") from exc


_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y")


def _to_date(value: Any) -> date | None:
    value = blank_to_none(value)
    if isinstance(value, datetime):
        return value.date()
    if value is None or isinstance(value, date):
        return value
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{value}' không đúng định dạng ngày (dd/mm/yyyy)")


_TRUE = {"c", "co", "y", "yes", "x", "1", "true"}
_FALSE = {"k", "khong", "n", "no", "0", "false"}


def _to_bool(value: Any) -> bool | None:
    value = blank_to_none(value)
    if value is None or isinstance(value, bool):
        return value
    token = normalize_token(str(value)).replace(" ", "")
    if token in _TRUE:
        return True
    if token in _FALSE:
        return False
    raise ValueError(f"'{value}' không hợp lệ (dùng C/K)")


_WEEKDAYS = {"t2": 1, "t3": 2, "t4": 3, "t5": 4, "t6": 5, "t7": 6, "cn": 7}
_WEEKDAYS.update({str(n): n - 1 for n in range(2, 8)})  # "2".."7" → Thứ 2..Thứ 7


def _to_weekdays(value: Any) -> list[int]:
    value = blank_to_none(value)
    if value is None:
        return []
    if isinstance(value, list):
        return sorted({int(v) for v in value})
    if isinstance(value, float | int):
        value = str(int(value))
    result = set()
    for raw in re.split(r"[,;\s]+", str(value)):
        token = normalize_token(raw).replace(" ", "").removeprefix("thu")
        if not token:
            continue
        if token not in _WEEKDAYS:
            raise ValueError(f"'{raw}' không phải ngày trong tuần (T2..T7, CN)")
        result.add(_WEEKDAYS[token])
    return sorted(result)


def _to_code_list(value: Any) -> list[str]:
    value = blank_to_none(value)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [c.strip() for c in re.split(r"[,;]+", str(value)) if c.strip()]


def enum_parser[E: Enum](enum_cls: type[E], aliases: dict[str, E]) -> Callable[[Any], E | None]:
    """Nhận giá trị enum gốc (vd. 'CAR') hoặc alias tiếng Việt (vd. 'Ô tô', 'OTO')."""
    lookup = {normalize_token(k).replace(" ", ""): v for k, v in aliases.items()}
    lookup.update({normalize_token(m.value).replace(" ", ""): m for m in enum_cls})
    accepted = ", ".join(aliases)

    def parse(value: Any) -> E | None:
        value = blank_to_none(value)
        if value is None or isinstance(value, enum_cls):
            return value
        token = normalize_token(str(value)).replace(" ", "")
        if token not in lookup:
            raise ValueError(f"'{value}' không hợp lệ (chấp nhận: {accepted})")
        return lookup[token]

    return parse


def normalize_phone(value: Any) -> str:
    """Chuẩn hóa SĐT Việt Nam về dạng 0xxxxxxxxx (bỏ khoảng trắng/dấu, +84/84 → 0).

    Excel lưu SĐT dạng số nên mất số 0 đầu → 9-10 chữ số không bắt đầu bằng 0 được thêm 0.
    """
    raw = _to_str(value)
    if raw is None:
        raise ValueError("Thiếu số điện thoại")
    digits = re.sub(r"[\s.()-]", "", str(raw))
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    elif not digits.startswith("0") and len(digits) in (9, 10):
        digits = "0" + digits
    if not re.fullmatch(r"0\d{9,10}", digits):
        raise ValueError("Số điện thoại không hợp lệ")
    return digits


Code = Annotated[
    str, BeforeValidator(_to_str), StringConstraints(strip_whitespace=True, max_length=64)
]
Text = Annotated[str, BeforeValidator(_to_str), StringConstraints(max_length=500)]
OptionalText = Annotated[str | None, BeforeValidator(_to_str), StringConstraints(max_length=500)]
Num = Annotated[Decimal, BeforeValidator(_to_decimal)]
OptionalNum = Annotated[Decimal | None, BeforeValidator(_to_decimal)]
Day = Annotated[date, BeforeValidator(_to_date)]
OptionalBool = Annotated[bool | None, BeforeValidator(_to_bool)]
Phone = Annotated[str, BeforeValidator(normalize_phone)]
Weekdays = Annotated[list[int], BeforeValidator(_to_weekdays)]
CodeList = Annotated[list[str], BeforeValidator(_to_code_list)]
