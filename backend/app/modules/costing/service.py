"""Chi phí thực tế của chuyến và phân bổ về từng đơn theo phương pháp của xe (D11)."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.costing.models import CostAllocation, DistanceSource, TripCost
from app.modules.costing.schemas import TripCostIn
from app.modules.dispatch.models import ItemStatus, Trip, TripItem, TripOrderStatus, TripStop
from app.modules.master_data.models import CostAllocationMethod, VehicleType
from app.modules.routing import service as routing
from app.modules.routing.service import Point, Profile

# Chỉ ghi nhận chi phí cho chuyến đã chạy.
COSTABLE = (TripOrderStatus.DISPATCHED, TripOrderStatus.CLOSED)
# Mục hàng chịu chi phí: đã giao (thành công hoặc thất bại); mục bị hủy không tính.
CHARGED = (ItemStatus.SUCCESS, ItemStatus.FAILED)


def split(total: Decimal, bases: list[Decimal]) -> list[Decimal]:
    """Chia `total` (đồng, số nguyên) theo tỷ lệ `bases`; phần dư dồn cho phần lẻ lớn nhất.
    Mọi căn cứ bằng 0 → chia đều."""
    if not bases:
        return []
    weights = bases if sum(bases) > 0 else [Decimal(1)] * len(bases)
    whole = sum(weights)
    raw = [total * w / whole for w in weights]
    amounts = [r.to_integral_value(ROUND_FLOOR) for r in raw]
    remainder = int(total - sum(amounts))
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - amounts[i], reverse=True)[:remainder]:
        amounts[i] += 1
    return amounts


def _stop_point(stop: TripStop) -> Point:
    point = stop.delivery_point
    if point is not None:
        return (float(point.latitude), float(point.longitude))
    return (float(stop.latitude or 0), float(stop.longitude or 0))


def _profile(trip: Trip) -> Profile:
    return Profile.MOTORBIKE if trip.vehicle.vehicle_type == VehicleType.MOTORBIKE else Profile.CAR


def charged_items(trip: Trip) -> list[tuple[TripStop, TripItem]]:
    return [
        (stop, item)
        for stop in trip.stops
        for item in stop.items
        if item.order_part_id is not None and item.status in CHARGED
    ]


def bases(trip: Trip, method: CostAllocationMethod) -> list[Decimal]:
    """Căn cứ phân bổ cho từng mục trong `charged_items(trip)`."""
    rows = charged_items(trip)
    if method == CostAllocationMethod.ORDER_VALUE:
        return [item.value for _, item in rows]
    if method == CostAllocationMethod.WEIGHT:
        return [item.weight_kg for _, item in rows]
    if method == CostAllocationMethod.PER_TRIP:
        # Mỗi đơn của chuyến nhận phần bằng nhau (chia tiếp đều cho các phần đơn của đơn đó).
        per_order: dict[uuid.UUID, int] = defaultdict(int)
        for _, item in rows:
            assert item.order_part is not None
            per_order[item.order_part.order_id] += 1
        return [
            Decimal(1) / per_order[item.order_part.order_id]  # type: ignore[union-attr]
            for _, item in rows
        ]
    # DISTANCE: điểm dừng xa kho chịu nhiều hơn; trong 1 điểm chia theo khối lượng.
    depot = (float(trip.warehouse.latitude), float(trip.warehouse.longitude))
    stop_weight: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    stop_count: dict[uuid.UUID, int] = defaultdict(int)
    for stop, item in rows:
        stop_weight[stop.id] += item.weight_kg
        stop_count[stop.id] += 1
    result = []
    for stop, item in rows:
        distance = Decimal(str(round(routing.haversine_m(depot, _stop_point(stop)))))
        share = (
            item.weight_kg / stop_weight[stop.id]
            if stop_weight[stop.id] > 0
            else Decimal(1) / stop_count[stop.id]
        )
        result.append(distance * share)
    return result


async def estimated_distance_km(trip: Trip) -> Decimal:
    depot = (float(trip.warehouse.latitude), float(trip.warehouse.longitude))
    points = [depot, *(_stop_point(s) for s in trip.stops), depot]
    meters = await routing.route_distance_m(points, _profile(trip))
    return (Decimal(meters) / 1000).quantize(Decimal("0.01"))


async def get_cost(session: AsyncSession, trip_id: uuid.UUID) -> TripCost | None:
    return await session.scalar(select(TripCost).where(TripCost.trip_id == trip_id))


async def record(
    session: AsyncSession,
    trip: Trip,
    data: TripCostIn | None,
    actor_id: uuid.UUID | None,
) -> TripCost:
    """Ghi nhận (hoặc tính lại) chi phí chuyến và phân bổ về đơn."""
    if trip.order_status not in COSTABLE:
        raise AppError("Chỉ ghi nhận chi phí cho chuyến đã xuất phát", code="invalid_status")
    data = data or TripCostIn()
    if data.odometer_start is not None and data.odometer_end is not None:
        if data.odometer_end < data.odometer_start:
            raise AppError("Số công-tơ-mét lúc về nhỏ hơn lúc đi", code="invalid_odometer")
        distance, source = data.odometer_end - data.odometer_start, DistanceSource.ODOMETER
    elif data.distance_km is not None:
        distance, source = data.distance_km, DistanceSource.MANUAL
    elif trip.planned_distance_km is not None:
        distance, source = trip.planned_distance_km, DistanceSource.PLANNED
    else:
        distance, source = await estimated_distance_km(trip), DistanceSource.ESTIMATE

    vehicle = trip.vehicle
    distance_cost = (distance * vehicle.cost_per_km).quantize(Decimal(1))
    cost = await get_cost(session, trip.id)
    if cost is None:
        cost = TripCost(company_id=trip.company_id, trip_id=trip.id, allocations=[])
        session.add(cost)
    cost.odometer_start = data.odometer_start
    cost.odometer_end = data.odometer_end
    cost.distance_km = distance
    cost.distance_source = source
    cost.cost_per_km = vehicle.cost_per_km
    cost.distance_cost = distance_cost
    cost.extra_cost = data.extra_cost
    cost.total_cost = distance_cost + data.extra_cost
    cost.allocation_method = vehicle.cost_allocation_method
    cost.note = data.note
    cost.recorded_by = actor_id
    cost.recorded_at = datetime.now(UTC)

    rows = charged_items(trip)
    basis_values = bases(trip, cost.allocation_method)
    amounts = split(cost.total_cost, basis_values)
    cost.allocations.clear()
    await session.flush()
    for (_, item), basis, amount in zip(rows, basis_values, amounts, strict=True):
        assert item.order_part is not None
        cost.allocations.append(
            CostAllocation(
                company_id=trip.company_id,
                trip_item_id=item.id,
                order_id=item.order_part.order_id,
                basis=basis.quantize(Decimal("0.0001")),
                amount=amount,
            )
        )
    await session.flush()
    audit.record(
        session,
        trip.company_id,
        "trip",
        trip.id,
        "cost_recorded",
        actor_id,
        distance_km=distance,
        source=source.value,
        total_cost=cost.total_cost,
    )
    return cost


async def ensure(session: AsyncSession, trip: Trip, actor_id: uuid.UUID | None) -> TripCost:
    """Khi kết thúc chuyến: chưa ghi nhận thì tính theo km kế hoạch/ước lượng; đã có thì tính lại
    phân bổ (kết quả giao có thể đã đổi)."""
    existing = await get_cost(session, trip.id)
    if existing is None:
        return await record(session, trip, None, actor_id)
    keep = TripCostIn(
        odometer_start=existing.odometer_start,
        odometer_end=existing.odometer_end,
        distance_km=existing.distance_km
        if existing.distance_source == DistanceSource.MANUAL
        else None,
        extra_cost=existing.extra_cost,
        note=existing.note,
    )
    return await record(session, trip, keep, existing.recorded_by)
