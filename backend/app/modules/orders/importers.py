"""Import đơn hàng: mỗi dòng 1 dòng hàng, gom theo số đơn (xem docs/IMPORT_TEMPLATES.md)."""

from collections.abc import Sequence
from typing import Annotated

from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.importing import (
    ApplyResult,
    Column,
    ImportContext,
    ImportSpec,
    ParsedRow,
    RowError,
    RowModel,
    load_by_codes,
)
from app.core.parsing import Code, Day, Num, OptionalNum, OptionalText
from app.modules.identity.models import CompanyRole
from app.modules.master_data.models import Customer, Product
from app.modules.orders.models import OrderSource, SalesOrder
from app.modules.orders.service import LineDraft, OrderDraft, is_locked, upsert_order


class OrderRow(RowModel):
    so_don: Code
    ngay_dat: Day
    ngay_giao_yc: Day
    ma_kh: Code
    ma_diem_giao: Code | None = None
    gia_tri_don: Annotated[Num, Field(ge=0)]
    ghi_chu: OptionalText = None
    ma_hang: Code
    so_luong: Annotated[Num, Field(gt=0)]
    thanh_tien: Annotated[OptionalNum, Field(ge=0)] = None


# Thông tin đầu đơn phải giống nhau giữa các dòng của cùng một đơn.
_HEADER_FIELDS = {
    "ngay_dat": "Ngày đặt",
    "ngay_giao_yc": "Ngày giao yêu cầu",
    "ma_kh": "Mã KH",
    "ma_diem_giao": "Mã điểm giao",
    "gia_tri_don": "Giá trị đơn",
}


def _header_errors(group: list[ParsedRow[OrderRow]]) -> list[RowError]:
    head = group[0].data
    errors = []
    for row in group[1:]:
        for field, label in _HEADER_FIELDS.items():
            a, b = getattr(head, field), getattr(row.data, field)
            if (a.lower() if isinstance(a, str) else a) != (b.lower() if isinstance(b, str) else b):
                errors.append(
                    RowError(row.row_no, label, f"Khác với dòng {group[0].row_no} của cùng đơn")
                )
    return errors


async def apply_orders(
    session: AsyncSession,
    ctx: ImportContext,
    rows: Sequence[ParsedRow[OrderRow]],
) -> ApplyResult:
    source = OrderSource(ctx.source)
    result = ApplyResult()
    groups: dict[str, list[ParsedRow[OrderRow]]] = {}
    for row in rows:
        groups.setdefault(row.data.so_don.lower(), []).append(row)

    customers = await load_by_codes(session, Customer, (r.data.ma_kh for r in rows))
    products = await load_by_codes(session, Product, (r.data.ma_hang for r in rows))
    existing = {
        o.external_ref.lower(): o
        for o in await session.scalars(
            select(SalesOrder).where(func.lower(SalesOrder.external_ref).in_(groups))
        )
    }

    for ref, group in groups.items():
        head_row = group[0]
        head = head_row.data
        errors = _header_errors(group)

        customer = customers.get(head.ma_kh.lower())
        point = None
        if customer is None or not customer.is_active:
            errors.append(
                RowError(
                    head_row.row_no,
                    "Mã KH",
                    f"Khách hàng '{head.ma_kh}' không tồn tại hoặc ngưng hoạt động",
                )
            )
        else:
            active_points = [p for p in customer.delivery_points if p.is_active]
            if head.ma_diem_giao:
                point = next(
                    (p for p in active_points if p.code.lower() == head.ma_diem_giao.lower()), None
                )
                if point is None:
                    errors.append(
                        RowError(
                            head_row.row_no,
                            "Mã điểm giao",
                            f"Điểm giao '{head.ma_diem_giao}' không tồn tại",
                        )
                    )
            else:
                point = next((p for p in active_points if p.is_default), None)
                if point is None:
                    errors.append(
                        RowError(
                            head_row.row_no, "Mã điểm giao", "Khách hàng chưa có điểm giao mặc định"
                        )
                    )

        if head.ngay_giao_yc < head.ngay_dat:
            errors.append(RowError(head_row.row_no, "Ngày giao yêu cầu", "Trước ngày đặt"))

        lines = []
        for row in group:
            product = products.get(row.data.ma_hang.lower())
            if product is None or not product.is_active:
                errors.append(
                    RowError(
                        row.row_no,
                        "Mã hàng",
                        f"Mặt hàng '{row.data.ma_hang}' không tồn tại hoặc ngưng hoạt động",
                    )
                )
                continue
            lines.append(LineDraft(product, row.data.so_luong, row.data.thanh_tien))

        order = existing.get(ref)
        if order is not None and is_locked(order):
            errors.append(
                RowError(
                    head_row.row_no,
                    "Số đơn",
                    "Đơn đã lập kế hoạch/giao hoặc đã hủy, không thể cập nhật",
                )
            )

        if errors:
            result.errors.extend(errors)
            continue
        assert customer is not None and point is not None
        draft = OrderDraft(
            external_ref=head.so_don,
            customer_id=customer.id,
            delivery_point_id=point.id,
            order_date=head.ngay_dat,
            requested_date=head.ngay_giao_yc,
            order_value=head.gia_tri_don,
            note=head.ghi_chu,
            lines=lines,
        )
        await upsert_order(session, ctx.company_id, draft, source, order)
        if order is None:
            result.created += 1
        else:
            result.updated += 1
    return result


ORDERS = ImportSpec(
    kind="orders",
    title="Đơn hàng",
    description=(
        "Mỗi dòng 1 mặt hàng của đơn; các dòng cùng Số đơn được gom thành 1 đơn và phải giống "
        "nhau ở thông tin đầu đơn. Đơn đã tồn tại và chưa lập kế hoạch sẽ được thay thế toàn bộ. "
        "Đơn tự tách thành phần hàng khô và phần hàng lạnh/đông."
    ),
    columns=[
        Column("so_don", "Số đơn", True, "DH2026-0001"),
        Column("ngay_dat", "Ngày đặt", True, "29/10/2026", "dd/mm/yyyy"),
        Column("ngay_giao_yc", "Ngày giao yêu cầu", True, "31/10/2026", "dd/mm/yyyy"),
        Column("ma_kh", "Mã KH", True, "KH001"),
        Column("ma_diem_giao", "Mã điểm giao", False, "DG1", "Bỏ trống = điểm giao mặc định"),
        Column("gia_tri_don", "Giá trị đơn (đ)", True, 15600000, "Tổng giá trị cả đơn"),
        Column("ghi_chu", "Ghi chú", False, ""),
        Column("ma_hang", "Mã hàng", True, "SUA-TT-180"),
        Column("so_luong", "Số lượng", True, 20, "Theo đơn vị tính của mặt hàng"),
        Column("thanh_tien", "Thành tiền (đ)", False, 7800000, "Giá trị dòng hàng (nếu có)"),
    ],
    row_model=OrderRow,
    apply=apply_orders,
    allowed_roles=frozenset({CompanyRole.COMPANY_ADMIN, CompanyRole.MANAGER}),
)
