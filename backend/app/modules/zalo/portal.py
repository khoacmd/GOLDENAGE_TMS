"""Đơn hàng cho khách hàng trên Zalo Mini App (chỉ đọc).

Như `reporting`, module này đọc trực tiếp bảng đơn hàng / chuyến / xác nhận giao để dựng góc nhìn
của khách. Phạm vi: liên hệ chủ thấy mọi đơn của khách hàng kèm giá trị; liên hệ điểm giao chỉ thấy
đơn đến điểm đó, không có giá trị. Lệnh nháp/đã hủy và mục bị hủy là thông tin nội bộ, không hiện.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.storage import get_storage
from app.modules.delivery.models import DeliveryConfirmation
from app.modules.dispatch import service as dispatch
from app.modules.dispatch.models import (
    ItemStatus,
    Trip,
    TripDeliveryStatus,
    TripItem,
    TripOrderStatus,
)
from app.modules.orders.models import OrderPart, OrderPartStatus, OrderStatus, SalesOrder
from app.modules.tenancy.models import CompanySettings
from app.modules.zalo import eta as eta_service
from app.modules.zalo import route as route_service
from app.modules.zalo.auth import CurrentCustomer
from app.modules.zalo.schemas import (
    CustomerDeliveryAttempt,
    CustomerEta,
    CustomerOrderDetail,
    CustomerOrderLine,
    CustomerOrderList,
    CustomerOrderStatus,
    CustomerOrderSummary,
    CustomerRoute,
    DeliveryAttemptStatus,
    DriverContact,
)

_IN_TRANSIT = DeliveryAttemptStatus.IN_TRANSIT
VISIBLE_TRIPS = (
    TripOrderStatus.APPROVED,
    TripOrderStatus.PREPARED,
    TripOrderStatus.PICKED,
    TripOrderStatus.DISPATCHED,
    TripOrderStatus.CLOSED,
)


@dataclass
class _Scope:
    owner_customers: set[uuid.UUID] = field(default_factory=set)
    points: set[uuid.UUID] = field(default_factory=set)

    def condition(self) -> ColumnElement[bool]:
        clauses = []
        if self.owner_customers:
            clauses.append(SalesOrder.customer_id.in_(self.owner_customers))
        if self.points:
            clauses.append(SalesOrder.delivery_point_id.in_(self.points))
        return or_(*clauses) if clauses else false()

    def sees_value(self, order: SalesOrder) -> bool:
        return order.customer_id in self.owner_customers


def _scope(customer: CurrentCustomer) -> _Scope:
    scope = _Scope()
    for s in customer.scopes:
        if s.delivery_point_id is None:
            scope.owner_customers.add(s.customer_id)
        else:
            scope.points.add(s.delivery_point_id)
    return scope


@dataclass(frozen=True)
class _Attempt:
    item: TripItem
    trip: Trip
    part: OrderPart


async def _attempts(
    session: AsyncSession, order_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[_Attempt]]:
    if not order_ids:
        return {}
    rows = await session.execute(
        select(TripItem, Trip, OrderPart)
        .join(Trip, Trip.id == TripItem.trip_id)
        .join(OrderPart, OrderPart.id == TripItem.order_part_id)
        .where(
            OrderPart.order_id.in_(order_ids),
            Trip.order_status.in_(VISIBLE_TRIPS),
            TripItem.status != ItemStatus.CANCELLED,
        )
        .order_by(Trip.plan_date, Trip.dispatched_at.nulls_last(), TripItem.created_at)
    )
    out: dict[uuid.UUID, list[_Attempt]] = defaultdict(list)
    for item, trip, part in rows:
        out[part.order_id].append(_Attempt(item, trip, part))
    return out


async def _etas(
    session: AsyncSession, company_id: uuid.UUID, attempts: list[_Attempt]
) -> dict[uuid.UUID, CustomerEta]:
    """Giờ đến dự kiến theo điểm dừng của các chuyến đang giao."""
    trips = {a.trip.id: a.trip for a in attempts if _attempt_status(a) == _IN_TRANSIT}
    if not trips:
        return {}
    settings = await session.get_one(CompanySettings, company_id)
    etas: dict[uuid.UUID, CustomerEta] = {}
    for trip in trips.values():
        windows = await dispatch.stop_windows(session, trip, settings)
        etas |= await eta_service.stop_etas(trip, settings, windows)
    return etas


def _attempt_eta(a: _Attempt, etas: dict[uuid.UUID, CustomerEta]) -> CustomerEta | None:
    return etas.get(a.item.stop_id) if _attempt_status(a) == _IN_TRANSIT else None


def _attempt_status(a: _Attempt) -> DeliveryAttemptStatus:
    if a.item.status == ItemStatus.SUCCESS:
        return DeliveryAttemptStatus.DELIVERED
    if a.item.status == ItemStatus.FAILED:
        return DeliveryAttemptStatus.FAILED
    if a.trip.order_status == TripOrderStatus.DISPATCHED:
        return DeliveryAttemptStatus.IN_TRANSIT
    return DeliveryAttemptStatus.SCHEDULED


def _order_status(order: SalesOrder, attempts: list[_Attempt]) -> CustomerOrderStatus:
    if order.status == OrderStatus.CANCELLED:
        return CustomerOrderStatus.CANCELLED
    if order.status == OrderStatus.COMPLETED:
        return CustomerOrderStatus.DELIVERED
    statuses = {_attempt_status(a) for a in attempts}
    parts = [p for p in order.parts if p.status != OrderPartStatus.CANCELLED]
    if DeliveryAttemptStatus.IN_TRANSIT in statuses:
        return CustomerOrderStatus.IN_TRANSIT
    if any(p.status == OrderPartStatus.DELIVERED for p in parts):
        return CustomerOrderStatus.PARTIAL
    if DeliveryAttemptStatus.SCHEDULED in statuses:
        return CustomerOrderStatus.SCHEDULED
    if any(p.status == OrderPartStatus.FAILED for p in parts):
        return CustomerOrderStatus.FAILED
    return CustomerOrderStatus.WAITING


def _summary(
    order: SalesOrder,
    attempts: list[_Attempt],
    scope: _Scope,
    etas: dict[uuid.UUID, CustomerEta],
) -> CustomerOrderSummary:
    sees_value = scope.sees_value(order)
    delivered = [
        a.item.delivered_at
        for a in attempts
        if a.item.status == ItemStatus.SUCCESS and a.item.delivered_at
    ]
    return CustomerOrderSummary(
        id=order.id,
        external_ref=order.external_ref,
        customer_code=order.customer.code,
        customer_name=order.customer.name,
        delivery_point_code=order.delivery_point.code,
        delivery_point_name=order.delivery_point.name,
        delivery_address=order.delivery_point.address,
        requested_date=order.requested_date,
        status=_order_status(order, attempts),
        can_see_value=sees_value,
        order_value=order.order_value if sees_value else None,
        line_count=len(order.lines),
        delivered_at=max(delivered, default=None),
        eta=min(
            (e for a in attempts if (e := _attempt_eta(a, etas))),
            key=lambda e: e.earliest,
            default=None,
        ),
    )


async def _today(session: AsyncSession, company_id: uuid.UUID) -> date:
    settings = await session.get(CompanySettings, company_id)
    return datetime.now(ZoneInfo(settings.timezone if settings else "UTC")).date()


async def list_orders(
    session: AsyncSession, customer: CurrentCustomer, day: date | None
) -> CustomerOrderList:
    """Đơn có ngày giao yêu cầu là `day` hoặc nằm trên chuyến (đã duyệt) của ngày `day`."""
    day = day or await _today(session, customer.company.id)
    scope = _scope(customer)
    on_trip = (
        select(OrderPart.order_id)
        .join(TripItem, TripItem.order_part_id == OrderPart.id)
        .join(Trip, Trip.id == TripItem.trip_id)
        .where(
            Trip.plan_date == day,
            Trip.order_status.in_(VISIBLE_TRIPS),
            TripItem.status != ItemStatus.CANCELLED,
        )
    )
    orders = list(
        await session.scalars(
            select(SalesOrder)
            .where(
                scope.condition(),
                or_(SalesOrder.requested_date == day, SalesOrder.id.in_(on_trip)),
            )
            .order_by(SalesOrder.external_ref)
        )
    )
    attempts = await _attempts(session, [o.id for o in orders])
    etas = await _etas(
        session, customer.company.id, [a for found in attempts.values() for a in found]
    )
    items = [_summary(o, attempts.get(o.id, []), scope, etas) for o in orders]
    items.sort(key=lambda o: (o.customer_code, o.delivery_point_code, o.external_ref))
    return CustomerOrderList(date=day, items=items)


async def _visible_order(session: AsyncSession, scope: _Scope, order_id: uuid.UUID) -> SalesOrder:
    order = await session.scalar(
        select(SalesOrder).where(SalesOrder.id == order_id, scope.condition())
    )
    if order is None:
        raise NotFoundError("Không tìm thấy đơn hàng")
    return order


def _driver_contacts(trip: Trip) -> list[DriverContact]:
    if trip.delivery_status != TripDeliveryStatus.IN_PROGRESS:
        return []
    crew = [(trip.driver, False), (trip.assistant, True)]
    return [
        DriverContact(name=user.full_name, phone=user.phone, is_assistant=is_assistant)
        for user, is_assistant in crew
        if user is not None
    ]


async def get_order(
    session: AsyncSession, customer: CurrentCustomer, order_id: uuid.UUID
) -> CustomerOrderDetail:
    scope = _scope(customer)
    order = await _visible_order(session, scope, order_id)
    attempts = (await _attempts(session, [order.id])).get(order.id, [])
    sees_value = scope.sees_value(order)
    etas = await _etas(session, customer.company.id, attempts)

    # Ảnh chứng từ: của lần xác nhận hợp lệ (lần đã cập nhật trạng thái mục hàng).
    confirmations = await session.scalars(
        select(DeliveryConfirmation).where(
            DeliveryConfirmation.item_id.in_([a.item.id for a in attempts]),
            DeliveryConfirmation.accepted.is_(True),
        )
    )
    storage = get_storage()
    photos: dict[uuid.UUID, list[str]] = defaultdict(list)
    for c in confirmations:
        photos[c.item_id].extend(storage.url(p.object_key) for p in c.photos)

    return CustomerOrderDetail(
        **_summary(order, attempts, scope, etas).model_dump(),
        note=order.note,
        lines=[
            CustomerOrderLine(
                product_code=line.product.code,
                product_name=line.product.name,
                # Khách xem theo đơn vị đã đặt (SKU), không phải đơn vị vận tải.
                uom=line.sku_uom,
                qty=line.sku_qty,
                amount=line.amount if sees_value else None,
            )
            for line in order.lines
        ],
        deliveries=[
            CustomerDeliveryAttempt(
                trip_code=a.trip.code,
                plan_date=a.trip.plan_date,
                temp_group=a.part.temp_group.value,
                status=_attempt_status(a),
                dispatched_at=a.trip.dispatched_at,
                eta=_attempt_eta(a, etas),
                delivered_at=a.item.delivered_at,
                reason=a.item.reason if a.item.status == ItemStatus.FAILED else None,
                driver_name=a.trip.driver.full_name if a.trip.driver else None,
                driver_contacts=_driver_contacts(a.trip),
                photo_urls=photos.get(a.item.id, []),
            )
            for a in attempts
        ],
    )


async def order_routes(
    session: AsyncSession, customer: CurrentCustomer, order_id: uuid.UUID
) -> list[CustomerRoute]:
    """Tuyến đã đi của từng chuyến đã xuất phát chở đơn này."""
    order = await _visible_order(session, _scope(customer), order_id)
    attempts = (await _attempts(session, [order.id])).get(order.id, [])
    stops = {a.trip.id: (a.trip, a.item.stop_id) for a in attempts if a.trip.dispatched_at}
    return [await route_service.customer_route(trip, stop) for trip, stop in stops.values()]
