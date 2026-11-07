"""Lập kế hoạch giao hàng tự động.

1. Lấy phần đơn chờ xếp (PENDING/FAILED, ngày yêu cầu <= ngày lập).
2. Kiểm tra khả thi từng phần đơn (xe tương thích loại hàng, loại xe khách yêu cầu, tải trọng).
3. Chọn kho xuất theo tồn kho khả dụng (ưu tiên 1 kho đáp ứng mọi phần của cùng điểm giao, rồi
   kho gần nhất); không có dữ liệu tồn kho thì chọn kho gần nhất.
4. Ma trận khoảng cách (OSRM/ước lượng) → bộ giải OR-Tools (`optimization`).
5. Sinh lệnh nháp (source=AUTO); phần đơn không xếp được kèm lý do.
"""

import asyncio
import itertools
import logging
import time as clock
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import SessionFactory, set_tenant_context
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.schemas import PageParams
from app.modules.audit import service as audit
from app.modules.dispatch import service as dispatch
from app.modules.dispatch.models import Trip, TripOrderStatus, TripSource
from app.modules.dispatch.schemas import StopIn, TripIn
from app.modules.master_data import service as master_data
from app.modules.master_data.models import Vehicle, VehicleRequirement, Warehouse
from app.modules.orders.models import OrderPart, TempGroup
from app.modules.planning.models import PlanningRun, RunStatus, RunTrigger
from app.modules.rivers import geometry as river_geometry
from app.modules.rivers import service as rivers
from app.modules.routing import service as routing
from app.modules.routing.service import Point, Profile
from app.modules.tenancy.models import CompanySettings
from app.modules.traffic import rules as traffic_rules
from app.modules.traffic import service as traffic
from optimization import Depot, Job, Matrix, Problem, Solution, Window, solve
from optimization import Vehicle as SolverVehicle

log = logging.getLogger(__name__)

ALL = PageParams(limit=500)
GRAMS = 1000
TEMP_LABEL = {TempGroup.DRY: "hàng khô", TempGroup.COLD: "hàng lạnh/đông"}
RESTRICTED_CAR = "car_restricted"  # ma trận cho ô tô bị giới hạn giờ vào vùng (`Vehicle.profile`)
REASON_CAPACITY = "Không đủ năng lực xe trong ca làm việc (tải trọng / thời gian / số lượt)"


def now() -> datetime:
    return datetime.now(UTC)


# --- Tạo / truy vấn lần chạy ------------------------------------------------------------


async def create_run(
    session: AsyncSession,
    company_id: uuid.UUID,
    plan_date: date,
    trigger: RunTrigger,
    actor_id: uuid.UUID | None,
    replace_drafts: bool = True,
    vehicle_ids: list[uuid.UUID] | None = None,
) -> PlanningRun:
    if vehicle_ids:
        # Nạp qua session có RLS: id xe của công ty khác coi như không tồn tại.
        selected = set(vehicle_ids)
        found = set(
            await session.scalars(
                select(Vehicle.id).where(Vehicle.id.in_(selected), Vehicle.is_active.is_(True))
            )
        )
        if found != selected:
            raise AppError(
                "Xe được chọn không tồn tại hoặc đã ngưng hoạt động", code="invalid_vehicle"
            )
    busy = await session.scalar(
        select(PlanningRun.id).where(
            PlanningRun.plan_date == plan_date,
            PlanningRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
        )
    )
    if busy is not None:
        raise ConflictError(f"Đang lập kế hoạch cho ngày {plan_date:%d/%m/%Y}, vui lòng chờ")
    run = PlanningRun(
        company_id=company_id,
        plan_date=plan_date,
        trigger=trigger,
        requested_by=actor_id,
        replace_drafts=replace_drafts,
        vehicle_ids=sorted(str(v) for v in set(vehicle_ids)) if vehicle_ids else None,
    )
    session.add(run)
    await session.flush()
    return run


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> PlanningRun:
    run = await session.get(PlanningRun, run_id)
    if run is None:
        raise NotFoundError("Không tìm thấy lần lập kế hoạch")
    return run


async def list_runs(session: AsyncSession, plan_date: date | None) -> list[PlanningRun]:
    stmt = select(PlanningRun).order_by(PlanningRun.created_at.desc()).limit(50)
    if plan_date is not None:
        stmt = stmt.where(PlanningRun.plan_date == plan_date)
    return list(await session.scalars(stmt))


# --- Chuẩn bị dữ liệu --------------------------------------------------------------------


def _point(obj: Any) -> Point:
    return (float(obj.latitude), float(obj.longitude))


def _infeasible_reason(part: OrderPart, vehicles: list[Vehicle]) -> str | None:
    """Lý do phần đơn không xe nào chở được (None nếu có xe tương thích)."""
    cargo = [v for v in vehicles if dispatch.cargo_compatible(v.cargo_class, part.temp_group)]
    if not cargo:
        return f"Không có xe chở {TEMP_LABEL[part.temp_group]}"
    requirement = part.order.customer.required_vehicle_type
    typed = [v for v in cargo if dispatch.vehicle_matches(requirement, v.vehicle_type)]
    if not typed:
        kind = "ô tô" if requirement == VehicleRequirement.CAR else "xe máy"
        return f"Khách yêu cầu {kind} nhưng không có {kind} chở {TEMP_LABEL[part.temp_group]}"
    biggest = max(v.capacity_kg for v in typed)
    if part.weight_kg > biggest:
        return (
            f"Khối lượng {part.weight_kg:g} kg vượt trọng tải xe phù hợp lớn nhất ({biggest:g} kg)"
        )
    return None


@dataclass
class _TrafficLimits:
    """Giờ từng xe được đến các điểm và rời các kho nằm trong vùng hạn chế (đã cắt theo ca)."""

    arrivals: dict[tuple[uuid.UUID, uuid.UUID], tuple[Window, ...]] = field(default_factory=dict)
    depots: dict[tuple[uuid.UUID, uuid.UUID], tuple[Window, ...]] = field(default_factory=dict)
    zones_of_point: dict[uuid.UUID, list[str]] = field(default_factory=dict)
    restricted_vehicles: set[uuid.UUID] = field(default_factory=set)
    # Điểm/kho trong vùng: tuyến tránh vùng không áp dụng cho các đoạn có đầu ở đây.
    inside: set[uuid.UUID] = field(default_factory=set)

    def can_serve(self, vehicle_id: uuid.UUID, point_id: uuid.UUID) -> bool:
        return self.arrivals.get((vehicle_id, point_id)) != ()

    def can_load_at(self, vehicle_id: uuid.UUID, warehouse_id: uuid.UUID) -> bool:
        return self.depots.get((vehicle_id, warehouse_id)) != ()


def _compatible(
    part: OrderPart, vehicles: list[Vehicle], limits: _TrafficLimits | None = None
) -> list[Vehicle]:
    requirement = part.order.customer.required_vehicle_type
    return [
        v
        for v in vehicles
        if dispatch.cargo_compatible(v.cargo_class, part.temp_group)
        and dispatch.vehicle_matches(requirement, v.vehicle_type)
        and part.weight_kg <= v.capacity_kg
        and (limits is None or limits.can_serve(v.id, part.order.delivery_point_id))
    ]


async def _traffic_limits(
    session: AsyncSession,
    settings: CompanySettings,
    plan_date: date,
    parts: list[OrderPart],
    warehouses: list[Warehouse],
    vehicles: list[Vehicle],
    shift: Window,
    service_s: int,
) -> _TrafficLimits | None:
    context = await traffic.enabled_context(session, settings, plan_date)
    if context is None:
        return None
    limits = _TrafficLimits(restricted_vehicles={v.id for v in vehicles if context.restricted(v)})
    points = {p.order.delivery_point_id: p.order.delivery_point for p in parts}
    point_list = list(points.values())
    found = await traffic.zones_at(
        session, context, [_point(o) for o in (*point_list, *warehouses)]
    )
    buffer_s = settings.traffic_zone_buffer_minutes * 60
    for point, zone_ids in zip(point_list, found, strict=False):
        if point.traffic_zone_exempt or not zone_ids:
            continue
        limits.inside.add(point.id)
        limits.zones_of_point[point.id] = sorted(context.zones[z].name for z in zone_ids)
        for vehicle in vehicles:
            windows = context.windows(vehicle, zone_ids)
            if windows is not None:
                allowed = traffic_rules.arrival_windows(windows, buffer_s, service_s)
                limits.arrivals[(vehicle.id, point.id)] = traffic_rules.intersect(allowed, (shift,))
    for warehouse, zone_ids in zip(warehouses, found[len(point_list) :], strict=True):
        if warehouse.traffic_zone_exempt or not zone_ids:
            continue
        limits.inside.add(warehouse.id)
        for vehicle in vehicles:
            windows = context.windows(vehicle, zone_ids)
            if windows is not None:
                limits.depots[(vehicle.id, warehouse.id)] = traffic_rules.intersect(
                    windows, (shift,)
                )
    return limits


async def _restricted_matrix(
    locations: list[Point],
    inside_locations: set[int],
    factor: float,
    plain: Matrix,
) -> Matrix | None:
    """Ma trận cho ô tô bị giới hạn giờ: đoạn có cả 2 đầu ngoài vùng đi tuyến tránh vùng (hợp lệ ở
    mọi giờ), đoạn có đầu trong vùng đi tuyến thường. None nếu không tính được tuyến tránh vùng."""
    avoid, source = await routing.matrix(locations, Profile.CAR, factor, avoid_zones=True)
    if source == "estimate":
        return None
    n = range(len(locations))

    def pick(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
        return [
            [b[i][j] if i in inside_locations or j in inside_locations else a[i][j] for j in n]
            for i in n
        ]

    return Matrix(
        pick(avoid.distance_m, plain.distance_m), pick(avoid.duration_s, plain.duration_s)
    )


def _needs(part: OrderPart) -> dict[uuid.UUID, Decimal]:
    needed: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for line in part.order.lines:
        if line.temp_group == part.temp_group:
            needed[line.product_id] += line.sku_qty
    return needed


@dataclass
class _Allocation:
    warehouse_of: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)  # phần đơn → kho
    unassigned: dict[uuid.UUID, str] = field(default_factory=dict)  # phần đơn → lý do


def allocate_warehouses(
    parts: list[OrderPart],
    compatible: dict[uuid.UUID, list[Vehicle]],
    warehouses: list[Warehouse],
    stock: dict[tuple[uuid.UUID, uuid.UUID], Decimal] | None,
    limits: _TrafficLimits | None = None,
) -> _Allocation:
    """Chọn kho xuất cho từng phần đơn (tham lam). `stock=None`: không xét tồn kho."""
    result = _Allocation()
    remaining = dict(stock or {})
    by_point: dict[uuid.UUID, list[OrderPart]] = defaultdict(list)
    for part in parts:
        by_point[part.order.delivery_point_id].append(part)

    def candidates(part: OrderPart) -> list[Warehouse]:
        return [
            w
            for w in warehouses
            if any(
                w.id in v.warehouse_ids and (limits is None or limits.can_load_at(v.id, w.id))
                for v in compatible[part.id]
            )
        ]

    def enough(w: Warehouse, group: list[OrderPart]) -> bool:
        if stock is None:
            return True
        total: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        for part in group:
            for product_id, qty in _needs(part).items():
                total[product_id] += qty
        return all(remaining.get((w.id, pid), Decimal(0)) >= q for pid, q in total.items())

    def take(w: Warehouse, part: OrderPart) -> None:
        result.warehouse_of[part.id] = w.id
        if stock is not None:
            for product_id, qty in _needs(part).items():
                remaining[(w.id, product_id)] = remaining.get((w.id, product_id), Decimal(0)) - qty

    # Ưu tiên đơn yêu cầu sớm hơn, đơn đã từng giao thất bại (tồn kho có hạn).
    def priority(group: list[OrderPart]) -> tuple[date, int]:
        return (min(p.order.requested_date for p in group), -max(p.attempt_count for p in group))

    for _, group in sorted(by_point.items(), key=lambda kv: priority(kv[1])):
        point = _point(group[0].order.delivery_point)
        common = set.intersection(*({w.id for w in candidates(p)} for p in group))
        nearest = sorted(warehouses, key=lambda w: routing.haversine_m(_point(w), point))
        whole = next((w for w in nearest if w.id in common and enough(w, group)), None)
        if whole is not None:
            for part in group:
                take(whole, part)
            continue
        for part in group:
            allowed = {w.id for w in candidates(part)}
            w = next((w for w in nearest if w.id in allowed and enough(w, [part])), None)
            if w is not None:
                take(w, part)
            elif not allowed:
                result.unassigned[part.id] = "Không có xe phù hợp được lấy hàng tại kho nào"
            else:
                result.unassigned[part.id] = (
                    "Không kho nào đủ tồn kho (trừ phần đã giữ cho lệnh khác)"
                )
    return result


@dataclass
class _JobInfo:
    part_ids: list[uuid.UUID]
    delivery_point_id: uuid.UUID
    warehouse_id: uuid.UUID


def build_jobs(
    parts: list[OrderPart],
    allocation: _Allocation,
    compatible: dict[uuid.UUID, list[Vehicle]],
    location_of: dict[uuid.UUID, int],
    service_s: int,
    limits: _TrafficLimits | None = None,
) -> tuple[list[Job], dict[str, _JobInfo], dict[uuid.UUID, str]]:
    """Gộp phần đơn cùng điểm giao + nhóm nhiệt độ + kho thành 1 điểm cần ghé (job)."""
    groups: dict[tuple[uuid.UUID, TempGroup, uuid.UUID], list[OrderPart]] = defaultdict(list)
    for part in parts:
        if part.id in allocation.warehouse_of:
            key = (part.order.delivery_point_id, part.temp_group, allocation.warehouse_of[part.id])
            groups[key].append(part)
    jobs: list[Job] = []
    info: dict[str, _JobInfo] = {}
    unassigned: dict[uuid.UUID, str] = {}
    for (point_id, _, warehouse_id), group in groups.items():
        vehicle_sets = [
            {
                v.id
                for v in compatible[p.id]
                if warehouse_id in v.warehouse_ids
                and (limits is None or limits.can_load_at(v.id, warehouse_id))
            }
            for p in group
        ]
        allowed = set.intersection(*vehicle_sets)
        if not allowed:
            for part in group:
                unassigned[part.id] = "Các phần đơn cùng điểm giao không có chung xe phù hợp"
            continue
        max_cap = max(v.capacity_kg for p in group for v in compatible[p.id] if v.id in allowed)
        # Gộp quá trọng tải xe lớn nhất → chia thành nhiều lần ghé (không tách phần đơn).
        bins: list[list[OrderPart]] = []
        for part in sorted(group, key=lambda p: p.weight_kg, reverse=True):
            target = next(
                (b for b in bins if sum(p.weight_kg for p in b) + part.weight_kg <= max_cap), None
            )
            if target is None:
                bins.append([part])
            else:
                target.append(part)
        for chunk in bins:
            job_id = f"j{len(jobs)}"
            weight = sum((p.weight_kg for p in chunk), Decimal(0))
            jobs.append(
                Job(
                    id=job_id,
                    location=location_of[point_id],
                    depot_id=str(warehouse_id),
                    demand=int(weight * GRAMS),
                    vehicle_ids=tuple(str(v) for v in sorted(allowed)),
                    service_s=service_s,
                    vehicle_windows={
                        str(v): limits.arrivals[(v, point_id)]
                        for v in allowed
                        if limits is not None and (v, point_id) in limits.arrivals
                    },
                )
            )
            info[job_id] = _JobInfo([p.id for p in chunk], point_id, warehouse_id)
    return jobs, info, unassigned


def prefer_motorbikes(
    jobs: list[Job],
    locations: list[Point],
    depot_location: dict[str, int],
    motorbike_ids: set[str],
    radius_km: float,
    cost: int,
) -> list[Job]:
    """Điểm trong bán kính quanh kho xuất (đường chim bay) mà xe máy giao được: ô tô giao điểm đó
    bị cộng `cost` vào hàm mục tiêu, để xe máy giao trước; ngoài bán kính giữ nguyên."""
    if radius_km <= 0 or cost <= 0:
        return jobs
    out = []
    for job in jobs:
        allowed = set(job.vehicle_ids)
        depot = locations[depot_location[job.depot_id]]
        near = routing.haversine_m(depot, locations[job.location]) <= radius_km * 1000
        if near and allowed & motorbike_ids:
            job = replace(job, vehicle_costs={v: cost for v in allowed - motorbike_ids})
        out.append(job)
    return out


# --- Chạy ------------------------------------------------------------------------------


def _river_crossings(
    path: list[Point], river_list: list[river_geometry.River], rate_per_km: float
) -> list[river_geometry.Crossing]:
    """Các lần qua sông trên tuyến (kho → điểm giao → kho), cầu dự kiến theo chi phí nhỏ nhất."""
    found = []
    for a, b in itertools.pairwise(path):
        for river in river_list:
            crossing = river_geometry.crossing(a, b, river, rate_per_km)
            if crossing is not None:
                found.append(crossing)
    return found


def _seconds(t: datetime) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


async def execute(session: AsyncSession, run: PlanningRun) -> None:
    """Lập kế hoạch cho `run` (session đã đặt context công ty). Ghi kết quả vào `run`."""
    started = clock.monotonic()
    company_id, plan_date = run.company_id, run.plan_date
    settings = await session.get(CompanySettings, company_id)
    assert settings is not None
    tz = ZoneInfo(settings.timezone)
    warnings: list[str] = []

    if run.replace_drafts:
        drafts = await session.scalars(
            select(Trip).where(
                Trip.plan_date == plan_date,
                Trip.source == TripSource.AUTO,
                Trip.order_status == TripOrderStatus.DRAFT,
            )
        )
        for trip in drafts:
            await dispatch.cancel(session, trip, "Lập lại kế hoạch tự động", run.requested_by)

    parts = await dispatch.available_parts(session, plan_date)
    vehicles, _ = await master_data.list_vehicles(session, ALL, True)
    warehouses, _ = await master_data.list_warehouses(session, ALL, True)
    active_wh = {w.id for w in warehouses}
    vehicles = [v for v in vehicles if active_wh.intersection(v.warehouse_ids)]
    if run.vehicle_ids is not None:
        chosen = set(run.vehicle_ids)
        vehicles = [v for v in vehicles if str(v.id) in chosen]
        codes = ", ".join(sorted(v.code for v in vehicles)) or "không còn xe nào hoạt động"
        warnings.append(f"Chỉ dùng các xe được chọn: {codes}")

    # Lượt còn lại của mỗi xe (trừ các lệnh đã có trong ngày).
    used: dict[uuid.UUID, int] = defaultdict(int)
    for trip in await dispatch.list_trips(session, plan_date=plan_date):
        if trip.order_status != TripOrderStatus.CANCELLED:
            used[trip.vehicle_id] += 1
    remaining_trips = {v.id: settings.max_trips_per_vehicle - used[v.id] for v in vehicles}
    if any(n < settings.max_trips_per_vehicle for n in remaining_trips.values()):
        warnings.append("Một số xe đã có lệnh trong ngày: chỉ dùng số lượt còn lại")
    usable = [v for v in vehicles if remaining_trips[v.id] > 0]

    shift_start = settings.shift_start.hour * 3600 + settings.shift_start.minute * 60
    shift_end = settings.shift_end.hour * 3600 + settings.shift_end.minute * 60
    local_now = now().astimezone(tz)
    if plan_date == local_now.date():
        # Lập trong ngày: chuyến chỉ xuất phát từ bây giờ (+15 phút chuẩn bị).
        shift_start = max(shift_start, _seconds(local_now + timedelta(minutes=15)))
    shift_end = max(shift_end, shift_start)
    limits = await _traffic_limits(
        session,
        settings,
        plan_date,
        parts,
        warehouses,
        usable,
        (shift_start, shift_end),
        settings.service_minutes * 60,
    )

    unassigned: dict[uuid.UUID, str] = {}
    compatible: dict[uuid.UUID, list[Vehicle]] = {}
    feasible: list[OrderPart] = []
    for part in parts:
        reason = _infeasible_reason(part, vehicles)
        if reason is not None and run.vehicle_ids is not None:
            reason += " (trong các xe được chọn)"
        if reason is None and not _compatible(part, usable):
            reason = "Các xe phù hợp đã dùng hết số lượt trong ngày"
        if reason is None and not _compatible(part, usable, limits):
            assert limits is not None
            zones = ", ".join(limits.zones_of_point.get(part.order.delivery_point_id, []))
            reason = (
                f"Điểm giao thuộc vùng hạn chế ({zones}): các xe phù hợp không được vào "
                "trong giờ làm việc"
            )
        if reason is not None:
            unassigned[part.id] = reason
            continue
        compatible[part.id] = _compatible(part, usable, limits)
        feasible.append(part)

    stock = await dispatch.stock_available(session)
    if not stock:
        warnings.append("Chưa có dữ liệu tồn kho: chọn kho gần nhất, không kiểm tra tồn")
    allocation = allocate_warehouses(feasible, compatible, warehouses, stock or None, limits)
    unassigned.update(allocation.unassigned)

    # Địa điểm: kho trước, sau đó các điểm giao.
    locations: list[Point] = [_point(w) for w in warehouses]
    location_of: dict[uuid.UUID, int] = {w.id: i for i, w in enumerate(warehouses)}
    for part in feasible:
        point = part.order.delivery_point
        if point.id not in location_of:
            location_of[point.id] = len(locations)
            locations.append(_point(point))
    jobs, job_info, merge_unassigned = build_jobs(
        feasible, allocation, compatible, location_of, settings.service_minutes * 60, limits
    )
    unassigned.update(merge_unassigned)
    jobs = prefer_motorbikes(
        jobs,
        locations,
        {str(w.id): location_of[w.id] for w in warehouses},
        {str(v.id) for v in usable if dispatch.vehicle_profile(v) == Profile.MOTORBIKE},
        settings.motorbike_priority_radius_km,
        settings.motorbike_priority_cost,
    )

    sources: set[str] = set()
    matrices = {}
    for profile in {dispatch.vehicle_profile(v) for v in usable} or {Profile.CAR}:
        matrices[str(profile)], source = await routing.matrix(
            locations, profile, settings.travel_time_factor
        )
        sources.add(source)
    run.distance_source = "estimate" if "estimate" in sources else sorted(sources)[0]
    if run.distance_source == "estimate":
        warnings.append("Khoảng cách ước lượng theo đường chim bay (chưa dùng OSRM)")

    # Ô tô bị giới hạn giờ dùng ma trận riêng để các đoạn ngoài vùng không xuyên qua vùng.
    restricted_cars = limits is not None and any(
        v.id in limits.restricted_vehicles and dispatch.vehicle_profile(v) == Profile.CAR
        for v in usable
    )
    avoid_ok = False
    if restricted_cars and limits is not None:
        inside_locations = {location_of[i] for i in limits.inside if i in location_of}
        avoid = (
            await _restricted_matrix(
                locations,
                inside_locations,
                settings.travel_time_factor,
                matrices[str(Profile.CAR)],
            )
            if routing.can_avoid_zones()
            else None
        )
        if avoid is not None:
            matrices[RESTRICTED_CAR] = avoid
            avoid_ok = True
        else:
            warnings.append(
                "Chưa tính được tuyến tránh vùng hạn chế: tuyến của ô tô có thể đi xuyên vùng"
            )

    # Xe máy: phạt khi đi qua sông (theo danh mục cầu) để ưu tiên điểm giao cùng bờ với kho.
    river_list = await rivers.planning_rivers(session)
    penalties: dict[str, list[list[int]]] = {}
    penalty_of: dict[uuid.UUID, str] = {}
    if river_list:
        for v in usable:
            if dispatch.vehicle_profile(v) == Profile.MOTORBIKE:
                key = f"river:{v.cost_per_km}"
                if key not in penalties:
                    penalties[key] = river_geometry.penalty_matrix(
                        locations, river_list, float(v.cost_per_km)
                    )
                penalty_of[v.id] = key

    def solver_profile(vehicle: Vehicle) -> str:
        profile = dispatch.vehicle_profile(vehicle)
        restricted = limits is not None and vehicle.id in limits.restricted_vehicles
        if avoid_ok and restricted and profile == Profile.CAR:
            return RESTRICTED_CAR
        return str(profile)

    problem = Problem(
        depots=[Depot(str(w.id), location_of[w.id]) for w in warehouses],
        vehicles=[
            SolverVehicle(
                id=str(v.id),
                profile=solver_profile(v),
                capacity=int(v.capacity_kg * GRAMS),
                cost_per_km=float(v.cost_per_km),
                depot_ids=tuple(str(w) for w in v.warehouse_ids if w in active_wh),
                max_trips=remaining_trips[v.id],
                fixed_cost=settings.trip_fixed_cost,
                depot_windows={
                    str(w): limits.depots[(v.id, w)]
                    for w in v.warehouse_ids
                    if limits is not None and (v.id, w) in limits.depots
                },
                penalty=penalty_of.get(v.id),
            )
            for v in usable
        ],
        jobs=jobs,
        matrices=matrices,
        penalties=penalties,
        shift_start_s=shift_start,
        shift_end_s=shift_end,
        turnaround_s=settings.turnaround_minutes * 60,
        time_limit_s=min(
            settings.planning_time_limit_s,
            get_settings().planning_time_cap_s or settings.planning_time_limit_s,
        ),
    )
    solve_started = clock.monotonic()
    solution: Solution = await asyncio.to_thread(solve, problem) if jobs else Solution()
    solve_seconds = clock.monotonic() - solve_started
    for job_id in solution.unassigned:
        for part_id in job_info[job_id].part_ids:
            unassigned[part_id] = REASON_CAPACITY

    trips: list[Trip] = []
    job_location = {j.id: j.location for j in jobs}
    rate_of = {v.id: v.cost_per_km for v in usable}
    midnight = datetime.combine(plan_date, datetime.min.time(), tz)
    for route in sorted(solution.routes, key=lambda r: (r.vehicle_id, r.trip_seq)):
        stops: list[StopIn] = []
        for job_id in route.job_ids:
            item = job_info[job_id]
            if stops and stops[-1].delivery_point_id == item.delivery_point_id:
                stops[-1].order_part_ids.extend(item.part_ids)
            else:
                stops.append(
                    StopIn(delivery_point_id=item.delivery_point_id, order_part_ids=item.part_ids)
                )
        data = TripIn(
            plan_date=plan_date,
            vehicle_id=uuid.UUID(route.vehicle_id),
            warehouse_id=uuid.UUID(route.depot_id),
            stops=stops,
        )
        try:
            async with session.begin_nested():
                trip, trip_warnings = await dispatch.save_trip(
                    session, company_id, data, run.requested_by, source=TripSource.AUTO
                )
        except AppError as e:
            details = "; ".join(e.details) or e.message
            for stop in stops:
                for part_id in stop.order_part_ids:
                    unassigned[part_id] = f"Không lưu được lệnh: {details}"
            continue
        trip.planning_run_id = run.id
        trip.planned_distance_km = Decimal(route.distance_m) / 1000
        trip.planned_cost = Decimal(round(route.cost))
        trip.planned_start = midnight + timedelta(seconds=route.start_s)
        trip.planned_end = midnight + timedelta(seconds=route.end_s)
        warnings += [f"{trip.code}: {w}" for w in trip_warnings]
        if trip.vehicle_id in penalty_of:
            path = [location_of[trip.warehouse_id]]
            path += [job_location[j] for j in route.job_ids] + path[:1]
            warnings += [
                f"{trip.code}: xe máy qua {c.river} (dự kiến {c.bridge})"
                for c in _river_crossings(
                    [locations[i] for i in path], river_list, float(rate_of[trip.vehicle_id])
                )
            ]
        trips.append(trip)
    await session.flush()

    by_id = {p.id: p for p in parts}
    run.unassigned = [
        {
            "order_part_id": str(pid),
            "order_id": str(by_id[pid].order_id),
            "external_ref": by_id[pid].order.external_ref,
            "customer_code": by_id[pid].order.customer.code,
            "customer_name": by_id[pid].order.customer.name,
            "temp_group": by_id[pid].temp_group.value,
            "weight_kg": float(by_id[pid].weight_kg),
            "requested_date": by_id[pid].order.requested_date.isoformat(),
            "reason": reason,
        }
        for pid, reason in unassigned.items()
    ]
    assigned_weight = sum((t.total_weight_kg for t in trips), Decimal(0))
    capacity_of = {v.id: v.capacity_kg for v in vehicles}
    capacity = sum((capacity_of[t.vehicle_id] for t in trips), Decimal(0))
    run.summary = {
        "parts_total": len(parts),
        "parts_assigned": len(parts) - len(unassigned),
        "trips": len(trips),
        "stops": sum(len(t.stops) for t in trips),
        "weight_kg": float(assigned_weight),
        "utilization": float(assigned_weight / capacity) if capacity else 0,
        "distance_km": round(sum(float(t.planned_distance_km or 0) for t in trips), 2),
        "cost": round(sum(float(t.planned_cost or 0) for t in trips)),
        "solve_seconds": round(solve_seconds, 2),
        "total_seconds": round(clock.monotonic() - started, 2),
    }
    run.input_snapshot = {
        "parts": [
            {
                "id": str(p.id),
                "order": p.order.external_ref,
                "temp_group": p.temp_group.value,
                "weight_kg": float(p.weight_kg),
                "delivery_point_id": str(p.order.delivery_point_id),
                "warehouse_id": str(allocation.warehouse_of.get(p.id) or "") or None,
            }
            for p in parts
        ],
        "vehicles": [
            {"id": str(v.id), "code": v.code, "remaining_trips": remaining_trips[v.id]}
            for v in vehicles
        ],
        "selected_vehicle_ids": run.vehicle_ids,
        "river_bridges": [
            {"river": r.name, "bridge": b.name, "motorbike_penalty": b.penalty}
            for r in river_list
            for b in r.bridges
        ],
        "shift": [shift_start, shift_end],
        "settings": {
            "service_minutes": settings.service_minutes,
            "turnaround_minutes": settings.turnaround_minutes,
            "max_trips_per_vehicle": settings.max_trips_per_vehicle,
            "trip_fixed_cost": settings.trip_fixed_cost,
            "travel_time_factor": settings.travel_time_factor,
            "motorbike_priority_radius_km": settings.motorbike_priority_radius_km,
            "motorbike_priority_cost": settings.motorbike_priority_cost,
            "traffic_rules_enabled": settings.traffic_rules_enabled,
            "traffic_zone_buffer_minutes": settings.traffic_zone_buffer_minutes,
        },
    }
    if unassigned:
        warnings.insert(0, f"{len(unassigned)} phần đơn không xếp được, cần xử lý thủ công")
    run.warnings = warnings
    audit.record(
        session,
        company_id,
        "planning_run",
        run.id,
        "completed",
        run.requested_by,
        trips=len(trips),
        unassigned=len(unassigned),
    )


async def process_run(run_id: uuid.UUID, company_id: uuid.UUID) -> None:
    """Chạy 1 lần lập kế hoạch đã xếp hàng (worker hoặc chạy ngay khi `tasks_eager`)."""
    async with SessionFactory() as session:
        await set_tenant_context(session, company_id=company_id, user_id=None)
        run = await get_run(session, run_id)
        if run.status != RunStatus.QUEUED:
            return
        run.status, run.started_at = RunStatus.RUNNING, now()
        await session.commit()
        try:
            await execute(session, run)
            run.status = RunStatus.SUCCEEDED
        except Exception as e:
            log.exception("Lập kế hoạch %s lỗi", run_id)
            await session.rollback()
            run = await get_run(session, run_id)
            run.status = RunStatus.FAILED
            run.error = (e.message if isinstance(e, AppError) else repr(e))[:2000]
        run.finished_at = now()
        await session.commit()


def next_working_day(today: date, weekdays: list[int]) -> date:
    day = today + timedelta(days=1)
    for _ in range(7):
        if day.isoweekday() in weekdays:
            return day
        day += timedelta(days=1)
    return today + timedelta(days=1)


async def create_due_runs() -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Job định kỳ: công ty bật lập tự động, đã qua giờ cut-over → lập cho ngày làm việc kế tiếp
    (mỗi ngày 1 lần). Trả các (run_id, company_id) cần đưa vào hàng đợi."""
    from app.modules.tenancy import service as tenancy

    created = []
    async with SessionFactory() as session:
        companies = [c for c in await tenancy.list_companies(session) if c.is_active]
    for company in companies:
        async with SessionFactory() as session:
            await set_tenant_context(session, company_id=company.id, user_id=None)
            settings = await session.get(CompanySettings, company.id)
            if settings is None or not settings.auto_plan_enabled:
                continue
            local = now().astimezone(ZoneInfo(settings.timezone))
            if local.time() < settings.cutover_time:
                continue
            plan_date = next_working_day(local.date(), settings.working_weekdays)
            exists = await session.scalar(
                select(PlanningRun.id).where(
                    PlanningRun.plan_date == plan_date,
                    PlanningRun.trigger == RunTrigger.SCHEDULED,
                )
            )
            if exists is not None:
                continue
            try:
                run = await create_run(session, company.id, plan_date, RunTrigger.SCHEDULED, None)
            except ConflictError:
                continue  # đang có lần chạy thủ công cho ngày này
            await session.commit()
            created.append((run.id, company.id))
    return created


# --- Điều chỉnh sau khi lập ---------------------------------------------------------------


async def run_trips(session: AsyncSession, run_id: uuid.UUID) -> list[Trip]:
    stmt = (
        select(Trip)
        .where(Trip.planning_run_id == run_id, Trip.order_status != TripOrderStatus.CANCELLED)
        .order_by(Trip.code)
    )
    return list(await session.scalars(stmt))


async def trip_distance_km(trip: Trip) -> float:
    """Quãng đường hiện tại của lệnh: kho → các điểm dừng theo thứ tự → kho."""
    meters = await routing.route_distance_m(
        dispatch.trip_path(trip), dispatch.vehicle_profile(trip.vehicle)
    )
    return meters / 1000


async def current_cost(trips: list[Trip]) -> tuple[float, float]:
    """(km, chi phí) hiện tại của các lệnh - để so với kết quả bộ tối ưu."""
    km = cost = 0.0
    for trip in trips:
        d = await trip_distance_km(trip)
        km += d
        cost += d * float(trip.vehicle.cost_per_km)
    return round(km, 2), round(cost)


async def move_stop(
    session: AsyncSession,
    company_id: uuid.UUID,
    from_trip_id: uuid.UUID,
    stop_id: uuid.UUID,
    to_trip_id: uuid.UUID,
    position: int | None,
    actor_id: uuid.UUID,
) -> tuple[list[Trip], list[str]]:
    """Chuyển điểm dừng giữa 2 lệnh (hoặc đổi thứ tự trong cùng lệnh) - 1 transaction."""
    source = await dispatch.get_trip(session, from_trip_id)
    index = next((i for i, s in enumerate(source.stops) if s.id == stop_id), None)
    if index is None:
        raise NotFoundError("Không tìm thấy điểm dừng trong lệnh")
    source_in = dispatch.trip_input(source)
    moved = source_in.stops.pop(index)
    if from_trip_id == to_trip_id:
        source_in.stops.insert(len(source_in.stops) if position is None else position, moved)
        trip, reorder_warnings = await dispatch.save_trip(
            session, company_id, source_in, actor_id, source
        )
        return [trip], reorder_warnings

    target = await dispatch.get_trip(session, to_trip_id)
    if target.warehouse_id != source.warehouse_id:
        # Giai đoạn này kho xuất cố định theo kho gần nhất (D24) → chỉ chuyển trong cùng kho.
        raise AppError(
            "Chỉ chuyển điểm dừng giữa các chuyến cùng kho xuất", code="different_warehouse"
        )
    target_in = dispatch.trip_input(target)
    # Gộp vào điểm dừng cùng điểm giao nếu lệnh đích đã có.
    same = next(
        (
            s
            for s in target_in.stops
            if moved.delivery_point_id and s.delivery_point_id == moved.delivery_point_id
        ),
        None,
    )
    if same is not None:
        same.order_part_ids += moved.order_part_ids
        same.adhoc_items += moved.adhoc_items
    else:
        target_in.stops.insert(len(target_in.stops) if position is None else position, moved)

    warnings: list[str] = []
    trips = []
    if source_in.stops:
        trip, w = await dispatch.save_trip(session, company_id, source_in, actor_id, source)
        trips.append(trip)
        warnings += w
    else:
        await dispatch.cancel(session, source, "Đã chuyển hết điểm dừng sang lệnh khác", actor_id)
    # Lệnh nguồn lưu trước → phần đơn được giải phóng rồi mới gán sang lệnh đích.
    trip, w = await dispatch.save_trip(session, company_id, target_in, actor_id, target)
    trips.append(trip)
    warnings += w
    return trips, warnings
