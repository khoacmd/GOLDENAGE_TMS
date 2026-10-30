"""Lập lệnh giao thủ công, phê duyệt, xuất kho, cập nhật giao hàng, kết thúc chuyến."""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.modules.audit import service as audit
from app.modules.dispatch.models import (
    ItemStatus,
    Trip,
    TripDeliveryStatus,
    TripItem,
    TripOrderStatus,
    TripStop,
)
from app.modules.dispatch.schemas import TripIn
from app.modules.identity.models import CompanyRole, UserRole
from app.modules.inventory.models import InventoryBalance
from app.modules.master_data.models import (
    CargoClass,
    DeliveryPoint,
    Vehicle,
    VehicleRequirement,
    VehicleType,
)
from app.modules.orders.models import (
    OrderPart,
    OrderPartStatus,
    OrderStatus,
    SalesOrder,
    SalesOrderLine,
    TempGroup,
)
from app.modules.tenancy.models import CompanySettings

# Phần đơn có thể xếp lệnh: chưa lập kế hoạch hoặc lần giao trước thất bại.
ELIGIBLE_PART_STATUSES = (OrderPartStatus.PENDING, OrderPartStatus.FAILED)
EDITABLE = (TripOrderStatus.DRAFT, TripOrderStatus.APPROVED)
# Lệnh còn "giữ" tồn kho tại kho xuất (chưa xuất hàng thực tế).
RESERVING = (TripOrderStatus.DRAFT, TripOrderStatus.APPROVED)

TEMP_LABEL = {TempGroup.DRY: "hàng khô", TempGroup.COLD: "hàng lạnh/đông"}
ENTITY = "trip"


def now() -> datetime:
    return datetime.now(UTC)


# --- Truy vấn --------------------------------------------------------------------------


async def available_parts(session: AsyncSession, plan_date: date) -> list[OrderPart]:
    stmt = (
        select(OrderPart)
        .join(SalesOrder, SalesOrder.id == OrderPart.order_id)
        .where(
            OrderPart.status.in_(ELIGIBLE_PART_STATUSES),
            SalesOrder.status == OrderStatus.OPEN,
            SalesOrder.requested_date <= plan_date,
        )
        .order_by(SalesOrder.requested_date, SalesOrder.external_ref, OrderPart.temp_group)
    )
    return list(await session.scalars(stmt))


async def list_trips(
    session: AsyncSession,
    *,
    plan_date: date | None = None,
    statuses: list[TripOrderStatus] | None = None,
    driver_id: uuid.UUID | None = None,
) -> list[Trip]:
    stmt = select(Trip).order_by(Trip.plan_date.desc(), Trip.code)
    if plan_date:
        stmt = stmt.where(Trip.plan_date == plan_date)
    if statuses:
        stmt = stmt.where(Trip.order_status.in_(statuses))
    if driver_id:
        stmt = stmt.where((Trip.driver_id == driver_id) | (Trip.assistant_id == driver_id))
    return list(await session.scalars(stmt))


async def get_trip(session: AsyncSession, trip_id: uuid.UUID) -> Trip:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("Không tìm thấy lệnh giao")
    return trip


def items_of(trip: Trip) -> list[TripItem]:
    return [item for stop in trip.stops for item in stop.items]


def item_counts(trip: Trip) -> dict[ItemStatus, int]:
    counts: dict[ItemStatus, int] = defaultdict(int)
    for item in items_of(trip):
        counts[ItemStatus(item.status)] += 1
    return dict(counts)


# --- Kiểm tra ràng buộc ------------------------------------------------------------------


def cargo_compatible(cargo_class: CargoClass, group: TempGroup) -> bool:
    if cargo_class == CargoClass.DRY_ONLY:
        return group == TempGroup.DRY
    if cargo_class == CargoClass.COLD_ONLY:
        return group == TempGroup.COLD
    return True


def vehicle_matches(requirement: VehicleRequirement, vehicle_type: VehicleType) -> bool:
    return requirement == VehicleRequirement.ANY or requirement.value == vehicle_type.value


@dataclass
class Validation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def _is_driver(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(UserRole.id).where(
            UserRole.company_id == company_id,
            UserRole.user_id == user_id,
            UserRole.role == CompanyRole.DRIVER,
        )
    )
    return found is not None


async def _stock_warnings(
    session: AsyncSession,
    warehouse_id: uuid.UUID,
    parts: list[OrderPart],
    exclude_trip_id: uuid.UUID | None,
) -> list[str]:
    """Cảnh báo khi tồn kho (trừ phần đã giữ bởi lệnh khác chưa xuất) không đủ."""
    needed: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    names: dict[uuid.UUID, str] = {}
    for part in parts:
        for line in part.order.lines:
            if line.temp_group == part.temp_group:
                needed[line.product_id] += line.qty
                names[line.product_id] = f"{line.product.code} ({line.product.uom})"
    if not needed:
        return []
    on_hand_rows = await session.execute(
        select(InventoryBalance.product_id, InventoryBalance.qty_on_hand).where(
            InventoryBalance.warehouse_id == warehouse_id,
            InventoryBalance.product_id.in_(needed),
        )
    )
    on_hand = {product_id: qty for product_id, qty in on_hand_rows}
    reserved_stmt = (
        select(SalesOrderLine.product_id, func.sum(SalesOrderLine.qty))
        .join(
            OrderPart,
            (OrderPart.order_id == SalesOrderLine.order_id)
            & (OrderPart.temp_group == SalesOrderLine.temp_group),
        )
        .join(TripItem, TripItem.order_part_id == OrderPart.id)
        .join(Trip, Trip.id == TripItem.trip_id)
        .where(
            Trip.warehouse_id == warehouse_id,
            Trip.order_status.in_(RESERVING),
            TripItem.status != ItemStatus.CANCELLED,
            SalesOrderLine.product_id.in_(needed),
        )
        .group_by(SalesOrderLine.product_id)
    )
    if exclude_trip_id is not None:
        reserved_stmt = reserved_stmt.where(Trip.id != exclude_trip_id)
    reserved = {pid: qty for pid, qty in await session.execute(reserved_stmt)}
    warnings = []
    for product_id, qty in needed.items():
        available = on_hand.get(product_id, Decimal(0)) - reserved.get(product_id, Decimal(0))
        if qty > available:
            warnings.append(
                f"Tồn kho không đủ {names[product_id]}: cần {qty:g}, còn {max(available, 0):g}"
            )
    return warnings


async def validate(
    session: AsyncSession, company_id: uuid.UUID, data: TripIn, trip: Trip | None
) -> tuple[Validation, Vehicle | None, dict[uuid.UUID, OrderPart]]:
    v = Validation()
    vehicle = await session.get(Vehicle, data.vehicle_id)
    if vehicle is None or not vehicle.is_active:
        v.errors.append("Xe không tồn tại hoặc ngưng hoạt động")
    elif data.warehouse_id not in vehicle.warehouse_ids:
        v.errors.append(f"Xe {vehicle.code} không được lấy hàng tại kho đã chọn")

    if data.driver_id and not await _is_driver(session, company_id, data.driver_id):
        v.errors.append("Lái xe phải là nhân viên giao hàng của công ty")
    if data.assistant_id:
        if data.assistant_id == data.driver_id:
            v.errors.append("Phụ xe phải khác lái xe")
        elif not await _is_driver(session, company_id, data.assistant_id):
            v.errors.append("Phụ xe phải là nhân viên giao hàng của công ty")
    if vehicle is not None and vehicle.requires_assistant and not data.assistant_id:
        v.errors.append(f"Xe {vehicle.code} yêu cầu phụ xe")

    part_ids = [pid for stop in data.stops for pid in stop.order_part_ids]
    if len(part_ids) != len(set(part_ids)):
        v.errors.append("Một phần đơn xuất hiện nhiều lần trong lệnh")
    parts = {
        p.id: p for p in await session.scalars(select(OrderPart).where(OrderPart.id.in_(part_ids)))
    }
    own = {i.order_part_id for i in items_of(trip)} if trip else set()
    point_ids = [s.delivery_point_id for s in data.stops if s.delivery_point_id]
    points = {
        p.id: p
        for p in await session.scalars(select(DeliveryPoint).where(DeliveryPoint.id.in_(point_ids)))
    }

    total_weight = Decimal(0)
    for n, stop in enumerate(data.stops, start=1):
        if stop.delivery_point_id and stop.delivery_point_id not in points:
            v.errors.append(f"Điểm dừng {n}: điểm giao không tồn tại")
        total_weight += sum((i.weight_kg for i in stop.adhoc_items), Decimal(0))
        for pid in stop.order_part_ids:
            part = parts.get(pid)
            if part is None:
                v.errors.append(f"Điểm dừng {n}: phần đơn không tồn tại")
                continue
            ref = f"Đơn {part.order.external_ref} ({TEMP_LABEL[part.temp_group]})"
            if pid not in own and (
                part.status not in ELIGIBLE_PART_STATUSES or part.order.status != OrderStatus.OPEN
            ):
                v.errors.append(f"{ref} đã được xếp lệnh khác hoặc không còn chờ giao")
            if part.order.delivery_point_id != stop.delivery_point_id:
                v.errors.append(f"{ref} không giao tới điểm dừng {n}")
            total_weight += part.weight_kg
            if vehicle is None:
                continue
            if not cargo_compatible(vehicle.cargo_class, part.temp_group):
                v.errors.append(f"{ref}: xe {vehicle.code} không chở {TEMP_LABEL[part.temp_group]}")
            requirement = part.order.customer.required_vehicle_type
            if not vehicle_matches(requirement, vehicle.vehicle_type):
                v.errors.append(
                    f"{ref}: khách {part.order.customer.code} yêu cầu "
                    f"{'ô tô' if requirement == VehicleRequirement.CAR else 'xe máy'}"
                )
            if part.order.requested_date != data.plan_date:
                v.warnings.append(f"{ref}: ngày giao yêu cầu {part.order.requested_date:%d/%m/%Y}")

    if vehicle is not None and total_weight > vehicle.capacity_kg:
        v.errors.append(
            f"Tổng khối lượng {total_weight:g} kg vượt trọng tải xe {vehicle.code} "
            f"({vehicle.capacity_kg:g} kg)"
        )

    settings = await session.get(CompanySettings, company_id)
    if settings and data.plan_date.isoweekday() not in settings.working_weekdays:
        v.warnings.append(f"Ngày {data.plan_date:%d/%m/%Y} không phải ngày giao hàng")
    if not v.errors:
        v.warnings += await _stock_warnings(
            session, data.warehouse_id, list(parts.values()), trip.id if trip else None
        )
    return v, vehicle, parts


# --- Lập / sửa lệnh ----------------------------------------------------------------------


def _release_part(part: OrderPart) -> None:
    """Trả phần đơn về hàng chờ (giữ dấu vết đã từng giao thất bại)."""
    part.status = OrderPartStatus.FAILED if part.attempt_count > 0 else OrderPartStatus.PENDING


async def _next_code(session: AsyncSession, plan_date: date) -> str:
    count = await session.scalar(select(func.count()).where(Trip.plan_date == plan_date))
    return f"L{plan_date:%y%m%d}-{(count or 0) + 1:02d}"


async def _next_seq(
    session: AsyncSession, vehicle_id: uuid.UUID, plan_date: date, exclude: uuid.UUID | None
) -> int:
    stmt = select(func.count()).where(
        Trip.vehicle_id == vehicle_id,
        Trip.plan_date == plan_date,
        Trip.order_status != TripOrderStatus.CANCELLED,
    )
    if exclude is not None:
        stmt = stmt.where(Trip.id != exclude)
    return (await session.scalar(stmt) or 0) + 1


async def save_trip(
    session: AsyncSession,
    company_id: uuid.UUID,
    data: TripIn,
    actor_id: uuid.UUID,
    trip: Trip | None = None,
) -> tuple[Trip, list[str]]:
    if trip is not None and trip.order_status not in EDITABLE:
        raise AppError("Chỉ sửa được lệnh nháp hoặc đã duyệt (chưa xuất kho)", code="trip_locked")
    check, vehicle, parts = await validate(session, company_id, data, trip)
    if check.errors:
        raise AppError("Lệnh giao không hợp lệ", code="invalid_trip", details=check.errors)
    assert vehicle is not None

    if trip is None:
        # Tính mã/lượt trước, chỉ add() khi đủ trường để autoflush không ghi lệnh dở dang.
        trip = Trip(
            company_id=company_id,
            code=await _next_code(session, data.plan_date),
            trip_seq=await _next_seq(session, data.vehicle_id, data.plan_date, None),
            plan_date=data.plan_date,
            vehicle_id=data.vehicle_id,
            stops=[],
        )
        action = "created"
    else:
        for item in items_of(trip):
            if item.order_part is not None and item.order_part_id not in parts:
                _release_part(item.order_part)
        trip.stops.clear()
        await session.flush()  # xóa item cũ trước (unique phần đơn đang hiệu lực)
        action = "updated"
        if trip.order_status == TripOrderStatus.APPROVED:
            trip.order_status = TripOrderStatus.DRAFT  # sửa sau duyệt → duyệt lại
            trip.approved_at = trip.approved_by = None
            action = "updated_reopened"
        if trip.vehicle_id != data.vehicle_id or trip.plan_date != data.plan_date:
            trip.trip_seq = await _next_seq(session, data.vehicle_id, data.plan_date, trip.id)

    trip.plan_date = data.plan_date
    trip.vehicle_id = data.vehicle_id
    trip.warehouse_id = data.warehouse_id
    trip.driver_id = data.driver_id
    trip.assistant_id = data.assistant_id
    trip.note = data.note

    total_weight, total_value = Decimal(0), Decimal(0)
    for seq, stop_in in enumerate(data.stops, start=1):
        stop = TripStop(
            company_id=company_id,
            seq=seq,
            delivery_point_id=stop_in.delivery_point_id,
            name=stop_in.name,
            address=None if stop_in.delivery_point_id else stop_in.address,
            latitude=None if stop_in.delivery_point_id else stop_in.latitude,
            longitude=None if stop_in.delivery_point_id else stop_in.longitude,
            note=stop_in.note,
            items=[],
        )
        for pid in stop_in.order_part_ids:
            part = parts[pid]
            part.status = OrderPartStatus.PLANNED
            stop.items.append(
                TripItem(
                    company_id=company_id,
                    trip=trip,
                    order_part=part,
                    weight_kg=part.weight_kg,
                    value=part.value,
                )
            )
            total_weight += part.weight_kg
            total_value += part.value
        for adhoc in stop_in.adhoc_items:
            stop.items.append(
                TripItem(
                    company_id=company_id,
                    trip=trip,
                    description=adhoc.description,
                    weight_kg=adhoc.weight_kg,
                )
            )
            total_weight += adhoc.weight_kg
        trip.stops.append(stop)
    trip.total_weight_kg = total_weight
    trip.total_value = total_value
    session.add(trip)
    await session.flush()
    audit.record(
        session,
        company_id,
        ENTITY,
        trip.id,
        action,
        actor_id,
        stops=len(data.stops),
        weight_kg=total_weight,
    )
    return trip, check.warnings


# --- Chuyển trạng thái ------------------------------------------------------------------


def _require(trip: Trip, *allowed: TripOrderStatus, action: str) -> None:
    if trip.order_status not in allowed:
        raise AppError(f"Không thể {action} lệnh ở trạng thái hiện tại", code="invalid_status")


async def approve(session: AsyncSession, trip: Trip, actor_id: uuid.UUID) -> Trip:
    _require(trip, TripOrderStatus.DRAFT, action="duyệt")
    if trip.driver_id is None:
        raise AppError("Cần phân công lái xe trước khi duyệt", code="driver_required")
    trip.order_status = TripOrderStatus.APPROVED
    trip.approved_at, trip.approved_by = now(), actor_id
    audit.record(session, trip.company_id, ENTITY, trip.id, "approved", actor_id)
    await session.flush()
    return trip


async def cancel(session: AsyncSession, trip: Trip, reason: str, actor_id: uuid.UUID) -> Trip:
    _require(trip, *EDITABLE, action="hủy")
    for item in items_of(trip):
        item.status = ItemStatus.CANCELLED
        if item.order_part is not None:
            _release_part(item.order_part)
    trip.order_status = TripOrderStatus.CANCELLED
    trip.cancel_reason = reason
    audit.record(session, trip.company_id, ENTITY, trip.id, "cancelled", actor_id, reason=reason)
    await session.flush()
    return trip


async def pick(session: AsyncSession, trip: Trip, actor_id: uuid.UUID) -> Trip:
    """Thủ kho xác nhận soạn/xuất hàng - chỉ cho lệnh đã duyệt."""
    _require(trip, TripOrderStatus.APPROVED, action="xác nhận xuất kho cho")
    trip.order_status = TripOrderStatus.PICKED
    trip.picked_at, trip.picked_by = now(), actor_id
    audit.record(session, trip.company_id, ENTITY, trip.id, "picked", actor_id)
    await session.flush()
    return trip


async def dispatch(session: AsyncSession, trip: Trip, actor_id: uuid.UUID) -> Trip:
    _require(trip, TripOrderStatus.PICKED, action="xuất phát")
    trip.order_status = TripOrderStatus.DISPATCHED
    trip.delivery_status = TripDeliveryStatus.IN_PROGRESS
    trip.dispatched_at = now()
    audit.record(session, trip.company_id, ENTITY, trip.id, "dispatched", actor_id)
    await session.flush()
    return trip


async def _sync_order_status(session: AsyncSession, order: SalesOrder) -> None:
    # Truy vấn tường minh: eager-load vòng OrderPart → order → parts không được nạp sẵn.
    parts = await session.scalars(select(OrderPart).where(OrderPart.order_id == order.id))
    active = [p for p in parts if p.status != OrderPartStatus.CANCELLED]
    if active and all(p.status == OrderPartStatus.DELIVERED for p in active):
        order.status = OrderStatus.COMPLETED
    elif order.status == OrderStatus.COMPLETED:
        order.status = OrderStatus.OPEN


async def update_item(
    session: AsyncSession,
    trip: Trip,
    item_id: uuid.UUID,
    status: ItemStatus,
    *,
    reason: str | None,
    delivered_at: datetime | None,
    actor_id: uuid.UUID,
    manual: bool,
) -> TripItem:
    """Ghi nhận kết quả giao 1 item. Hủy item đang PENDING chỉ dành cho quản lý (manual)."""
    _require(trip, TripOrderStatus.DISPATCHED, action="cập nhật giao hàng cho")
    item = next((i for i in items_of(trip) if i.id == item_id), None)
    if item is None:
        raise NotFoundError("Không tìm thấy mục hàng trong chuyến")
    if status == ItemStatus.PENDING:
        raise AppError("Trạng thái không hợp lệ", code="invalid_status")
    if item.status == ItemStatus.CANCELLED:
        raise AppError("Mục hàng đã hủy", code="invalid_status")
    if status == ItemStatus.CANCELLED and (item.status != ItemStatus.PENDING or not manual):
        raise AppError("Chỉ quản lý được hủy mục hàng chưa giao", code="invalid_status")
    if status == ItemStatus.FAILED and not reason:
        raise AppError("Cần ghi lý do giao không thành công", code="reason_required")

    previous = ItemStatus(item.status)
    item.status = status
    item.reason = reason
    item.delivered_at = (delivered_at or now()) if status != ItemStatus.CANCELLED else None
    item.updated_by = actor_id
    item.is_manual_update = manual

    part = item.order_part
    if part is not None:
        if previous == ItemStatus.FAILED and status != ItemStatus.FAILED:
            part.attempt_count -= 1
        if status == ItemStatus.FAILED and previous != ItemStatus.FAILED:
            part.attempt_count += 1
        if status == ItemStatus.SUCCESS:
            part.status = OrderPartStatus.DELIVERED
        elif status == ItemStatus.FAILED:
            part.status = OrderPartStatus.FAILED
        else:
            _release_part(part)
        await _sync_order_status(session, part.order)

    pending = any(i.status == ItemStatus.PENDING for i in items_of(trip))
    if pending:
        trip.delivery_status = TripDeliveryStatus.IN_PROGRESS
        trip.finished_at = None
    elif trip.delivery_status != TripDeliveryStatus.FINISHED:
        trip.delivery_status = TripDeliveryStatus.FINISHED
        trip.finished_at = now()
    audit.record(
        session,
        trip.company_id,
        ENTITY,
        trip.id,
        "item_updated",
        actor_id,
        item_id=item.id,
        status=status.value,
        previous=previous.value,
        reason=reason,
        manual=manual,
    )
    await session.flush()
    return item


async def close(session: AsyncSession, trip: Trip, actor_id: uuid.UUID) -> Trip:
    _require(trip, TripOrderStatus.DISPATCHED, action="kết thúc")
    if trip.delivery_status != TripDeliveryStatus.FINISHED:
        raise AppError("Chuyến còn đơn chưa có kết quả giao", code="trip_not_finished")
    trip.order_status = TripOrderStatus.CLOSED
    trip.closed_at, trip.closed_by = now(), actor_id
    audit.record(
        session,
        trip.company_id,
        ENTITY,
        trip.id,
        "closed",
        actor_id,
        **{k.value: v for k, v in item_counts(trip).items()},
    )
    await session.flush()
    return trip


# --- Phiếu soạn hàng ---------------------------------------------------------------------


def picking_lines(trip: Trip) -> tuple[list[dict[str, object]], list[str]]:
    lines: dict[uuid.UUID, dict[str, object]] = {}
    adhoc: list[str] = []
    for item in items_of(trip):
        if item.status == ItemStatus.CANCELLED:
            continue
        if item.order_part is None:
            adhoc.append(f"{item.description} ({item.weight_kg:g} kg)")
            continue
        for line in item.order_part.order.lines:
            if line.temp_group != item.order_part.temp_group:
                continue
            row = lines.setdefault(
                line.product_id,
                {
                    "product_code": line.product.code,
                    "product_name": line.product.name,
                    "uom": line.product.uom,
                    "temp_group": line.temp_group,
                    "qty": Decimal(0),
                    "weight_kg": Decimal(0),
                },
            )
            row["qty"] = row["qty"] + line.qty  # type: ignore[operator]
            row["weight_kg"] = row["weight_kg"] + line.weight_kg  # type: ignore[operator]
    ordered = sorted(lines.values(), key=lambda r: (str(r["temp_group"]), str(r["product_code"])))
    return ordered, adhoc
