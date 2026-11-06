"""Chuyển file đơn hàng tải từ DMS (báo cáo ReportSOSalesRealtime) sang template import đơn hàng.

Chỉ đổi định dạng, không ghi dữ liệu: người dùng tải file kết quả về rồi import như bình thường.
"""

import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import load_workbook

from app.core.errors import AppError
from app.core.importing import validate_row
from app.modules.integration.service import RawRow, build_template, read_file
from app.modules.orders.importers import ORDERS

# Cột của DMS dùng để chuyển đổi; các cột khác bị bỏ qua.
REQUIRED = ("OrderNbr", "OrderDate", "CustomerCD", "InventoryCD", "OrderSalesQty", "SalesPrice")
DEFAULT_PRODUCT_CODE_LENGTH = 18
MAX_REPORTED_ERRORS = 20


@dataclass
class DmsSummary:
    lines: int = 0
    orders: int = 0
    customers: int = 0
    products: int = 0
    total_value: int = 0
    skipped_zero_qty: int = 0
    skipped_returns: int = 0
    first_delivery_date: date | None = None
    last_delivery_date: date | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Line:
    order: str
    order_date: date
    ship_date: date
    customer: str
    product: str
    qty: Decimal
    amount: Decimal


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _decimal(value: Any) -> Decimal:
    if value is None or _text(value) == "":
        return Decimal(0)
    try:
        return Decimal(_text(value).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"không phải số: {value}") from exc


def _day(value: Any) -> date | None:
    if value is None or _text(value) == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"ngày không hợp lệ: {value}")


def _is_true(value: Any) -> bool:
    return _text(value).lower() in {"true", "1", "yes", "có"}


def product_code(value: Any, length: int) -> str:
    """Mã hàng toàn số được thêm số 0 bên trái cho đủ `length` ký tự (DMS bỏ mất các số 0)."""
    code = _text(value)
    if length and code.isdigit() and len(code) < length:
        return code.zfill(length)
    return code


def _parse(rows: list[RawRow], length: int, summary: DmsSummary) -> list[_Line]:
    if not rows:
        raise AppError("File không có dữ liệu", code="empty_file")
    missing = [c for c in REQUIRED if c not in rows[0][1]]
    if missing:
        raise AppError(
            "File không đúng định dạng đơn hàng DMS",
            code="invalid_dms_file",
            details=[f"Thiếu cột: {', '.join(missing)}"],
        )
    lines: list[_Line] = []
    errors: list[str] = []
    for row_no, raw in rows:
        try:
            order_type = _text(raw.get("OrderType")).upper()
            if (order_type and order_type != "SO") or _is_true(raw.get("IsReturned")):
                summary.skipped_returns += 1
                continue
            # Hàng tặng cũng phải giao: cộng vào số lượng, không tính tiền.
            sales_qty = _decimal(raw.get("OrderSalesQty"))
            qty = sales_qty + _decimal(raw.get("OrderFreeQty"))
            if qty <= 0:
                summary.skipped_zero_qty += 1
                continue
            order_date = _day(raw.get("OrderDate"))
            if order_date is None:
                raise ValueError("thiếu OrderDate")
            for key in ("OrderNbr", "CustomerCD", "InventoryCD"):
                if not _text(raw.get(key)):
                    raise ValueError(f"thiếu {key}")
            lines.append(
                _Line(
                    order=_text(raw.get("OrderNbr")),
                    order_date=order_date,
                    ship_date=_day(raw.get("CreateShipDate")) or order_date,
                    customer=_text(raw.get("CustomerCD")),
                    product=product_code(raw.get("InventoryCD"), length),
                    qty=qty,
                    amount=(sales_qty * _decimal(raw.get("SalesPrice"))).quantize(Decimal(1)),
                )
            )
        except ValueError as exc:
            errors.append(f"Dòng {row_no}: {exc}")
    if errors:
        raise AppError(
            "File DMS có dòng không đọc được",
            code="invalid_dms_file",
            details=errors[:MAX_REPORTED_ERRORS],
        )
    return lines


def convert_dms_orders(
    content: bytes,
    filename: str,
    *,
    delivery_date: date | None = None,
    product_code_length: int = DEFAULT_PRODUCT_CODE_LENGTH,
) -> tuple[bytes, DmsSummary]:
    summary = DmsSummary()
    lines = _parse(read_file(content, filename), product_code_length, summary)

    by_order: dict[str, list[_Line]] = defaultdict(list)
    for line in lines:
        by_order[line.order].append(line)

    out: list[dict[str, Any]] = []
    errors: list[str] = []
    for order_no in sorted(by_order):
        group = by_order[order_no]
        customers = {line.customer for line in group}
        if len(customers) > 1:
            errors.append(f"Đơn {order_no}: nhiều mã khách hàng ({', '.join(sorted(customers))})")
            continue
        # Thông tin đầu đơn phải giống nhau trên mọi dòng của đơn.
        order_date = min(line.order_date for line in group)
        ship_date = delivery_date or max(line.ship_date for line in group)
        # Cùng mặt hàng xuất hiện nhiều dòng (vd. dòng hàng bán và dòng hàng tặng): gộp lại.
        merged: dict[str, list[Decimal]] = {}
        for line in group:
            qty_amount = merged.setdefault(line.product, [Decimal(0), Decimal(0)])
            qty_amount[0] += line.qty
            qty_amount[1] += line.amount
        total = sum((amount for _, amount in merged.values()), Decimal(0))
        for product, (qty, amount) in sorted(merged.items()):
            out.append(
                {
                    "so_don": order_no,
                    "ngay_dat": order_date.strftime("%d/%m/%Y"),
                    "ngay_giao_yc": ship_date.strftime("%d/%m/%Y"),
                    "ma_kh": group[0].customer,
                    "gia_tri_don": int(total),
                    "ma_hang": product,
                    "so_luong": int(qty) if qty == qty.to_integral_value() else float(qty),
                    "thanh_tien": int(amount),
                }
            )
        summary.total_value += int(total)
        summary.first_delivery_date = min(filter(None, (summary.first_delivery_date, ship_date)))
        summary.last_delivery_date = max(filter(None, (summary.last_delivery_date, ship_date)))

    # Kiểm tra lại bằng đúng model dòng của import để file kết quả chắc chắn đọc được.
    for i, row in enumerate(out, start=2):
        errors += [
            f"Dòng {i} ({row['so_don']}): {e.column + ' - ' if e.column else ''}{e.message}"
            for e in validate_row(ORDERS, i, row, ORDERS.row_model)[1]
        ]
    if errors:
        raise AppError(
            "Không chuyển đổi được file DMS",
            code="invalid_dms_file",
            details=errors[:MAX_REPORTED_ERRORS],
        )

    summary.lines = len(out)
    summary.orders = len({r["so_don"] for r in out})
    summary.customers = len({r["ma_kh"] for r in out})
    summary.products = len({r["ma_hang"] for r in out})
    if delivery_date is None and summary.first_delivery_date != summary.last_delivery_date:
        summary.warnings.append("Các đơn có ngày giao yêu cầu khác nhau (theo ngày tạo phiếu giao)")
    return _write(out), summary


def _write(rows: list[dict[str, Any]]) -> bytes:
    wb = load_workbook(io.BytesIO(build_template(ORDERS)))
    ws = wb.worksheets[0]
    ws.delete_rows(2)  # dòng ví dụ của template
    keys = [c.key for c in ORDERS.columns]
    for r, row in enumerate(rows, start=2):
        for c, key in enumerate(keys, start=1):
            value = row.get(key)
            if value is None:
                continue
            cell = ws.cell(row=r, column=c, value=value)
            if isinstance(value, str):
                cell.number_format = "@"  # giữ nguyên số 0 đầu mã khi mở bằng Excel
            elif key in ("gia_tri_don", "thanh_tien"):
                cell.number_format = "#,##0"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
