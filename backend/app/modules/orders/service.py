import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.core.schemas import PageParams, paginate
from app.modules.master_data.models import Customer, Product
from app.modules.orders.models import (
    OrderPart,
    OrderPartStatus,
    OrderSource,
    OrderStatus,
    SalesOrder,
    SalesOrderLine,
    TempGroup,
)

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class LineDraft:
    product: Product
    qty: Decimal
    amount: Decimal | None


@dataclass(frozen=True)
class OrderDraft:
    external_ref: str
    customer_id: uuid.UUID
    delivery_point_id: uuid.UUID
    order_date: date
    requested_date: date
    order_value: Decimal
    note: str | None
    lines: list[LineDraft]


def split_parts(
    lines: list[LineDraft], order_value: Decimal
) -> dict[TempGroup, tuple[Decimal, Decimal]]:
    """Tách đơn theo nhóm nhiệt độ → {nhóm: (khối lượng kg, giá trị)}.

    Giá trị phần = tổng thành tiền các dòng nếu mọi dòng có thành tiền; ngược lại phân bổ
    `order_value` theo khối lượng (đơn 0 kg thì theo số dòng), phần cuối nhận phần làm tròn.
    """
    weights: dict[TempGroup, Decimal] = {}
    amounts: dict[TempGroup, Decimal] = {}
    counts: dict[TempGroup, int] = {}
    for line in lines:
        group = TempGroup.of(line.product.temp_class)
        weights[group] = weights.get(group, Decimal(0)) + line.qty * line.product.weight_kg
        amounts[group] = amounts.get(group, Decimal(0)) + (line.amount or Decimal(0))
        counts[group] = counts.get(group, 0) + 1

    groups = sorted(weights)
    if all(line.amount is not None for line in lines):
        values = {g: amounts[g] for g in groups}
    else:
        total_weight = sum(weights.values())
        basis = (
            {g: weights[g] for g in groups}
            if total_weight > 0
            else {g: Decimal(counts[g]) for g in groups}
        )
        total_basis = sum(basis.values())
        values, allocated = {}, Decimal(0)
        for g in groups[:-1]:
            values[g] = (order_value * basis[g] / total_basis).quantize(_CENT, ROUND_HALF_UP)
            allocated += values[g]
        values[groups[-1]] = order_value - allocated
    return {g: (weights[g], values[g]) for g in groups}


def is_locked(order: SalesOrder) -> bool:
    """Đơn đã vào kế hoạch/giao/hủy thì không được ghi đè từ hệ thống ngoài."""
    return order.status != OrderStatus.OPEN or any(
        p.status != OrderPartStatus.PENDING for p in order.parts
    )


async def upsert_order(
    session: AsyncSession,
    company_id: uuid.UUID,
    draft: OrderDraft,
    source: OrderSource,
    existing: SalesOrder | None,
) -> SalesOrder:
    """Tạo mới hoặc thay toàn bộ dòng/phần của đơn chưa khóa (kiểm tra `is_locked` trước)."""
    order = existing or SalesOrder(
        company_id=company_id, external_ref=draft.external_ref, source=source, lines=[], parts=[]
    )
    if existing is not None:
        # Xóa dòng/phần cũ trước khi thêm mới (unique theo line_no, temp_group).
        order.lines.clear()
        order.parts.clear()
        await session.flush()
    order.customer_id = draft.customer_id
    order.delivery_point_id = draft.delivery_point_id
    order.order_date = draft.order_date
    order.requested_date = draft.requested_date
    order.order_value = draft.order_value
    order.note = draft.note
    order.lines = [
        SalesOrderLine(
            company_id=company_id,
            line_no=i,
            product_id=line.product.id,
            qty=line.qty,
            weight_kg=line.qty * line.product.weight_kg,
            amount=line.amount,
            temp_group=TempGroup.of(line.product.temp_class),
        )
        for i, line in enumerate(draft.lines, start=1)
    ]
    order.parts = [
        OrderPart(company_id=company_id, temp_group=group, weight_kg=weight, value=value)
        for group, (weight, value) in split_parts(draft.lines, draft.order_value).items()
    ]
    if existing is None:
        session.add(order)
    return order


async def list_orders(
    session: AsyncSession,
    params: PageParams,
    *,
    requested_from: date | None = None,
    requested_to: date | None = None,
    status: OrderStatus | None = None,
) -> tuple[list[SalesOrder], int]:
    stmt = select(SalesOrder).join(Customer, Customer.id == SalesOrder.customer_id)
    if params.q:
        pattern = f"%{params.q.strip()}%"
        stmt = stmt.where(
            or_(
                SalesOrder.external_ref.ilike(pattern),
                Customer.code.ilike(pattern),
                Customer.name.ilike(pattern),
            )
        )
    if requested_from:
        stmt = stmt.where(SalesOrder.requested_date >= requested_from)
    if requested_to:
        stmt = stmt.where(SalesOrder.requested_date <= requested_to)
    if status:
        stmt = stmt.where(SalesOrder.status == status)
    stmt = stmt.order_by(SalesOrder.requested_date.desc(), SalesOrder.external_ref)
    return await paginate(session, stmt, params)


async def get_order(session: AsyncSession, order_id: uuid.UUID) -> SalesOrder:
    order = await session.get(SalesOrder, order_id)
    if order is None:
        raise NotFoundError("Không tìm thấy đơn hàng")
    return order


async def cancel_order(session: AsyncSession, order_id: uuid.UUID) -> SalesOrder:
    """Quản lý hủy đơn chưa vào kế hoạch (mọi phần còn PENDING)."""
    order = await get_order(session, order_id)
    if is_locked(order):
        raise AppError("Chỉ hủy được đơn chưa lập kế hoạch/giao hàng", code="order_locked")
    order.status = OrderStatus.CANCELLED
    for part in order.parts:
        part.status = OrderPartStatus.CANCELLED
    await session.flush()
    return order
