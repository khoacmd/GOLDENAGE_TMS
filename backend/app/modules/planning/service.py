"""Lập kế hoạch giao hàng tự động.

1. Lấy phần đơn chờ xếp (PENDING/FAILED, ngày yêu cầu <= ngày lập).
2. Kiểm tra khả thi từng phần đơn (xe tương thích loại hàng, loại xe khách yêu cầu, tải trọng).
3. Chọn kho xuất theo tồn kho khả dụng (ưu tiên 1 kho đáp ứng mọi phần của cùng điểm giao, rồi
   kho gần nhất); không có dữ liệu tồn kho thì chọn kho gần nhất.
4. Ma trận khoảng cách (OSRM/ước lượng) → bộ giải OR-Tools (`optimization`).
5. Sinh lệnh nháp (source=AUTO); phần đơn không xếp được kèm lý do.
"""

import asyncio
import logging
import time as clock
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
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
from app.modules.master_data.models import Vehicle, VehicleRequirement, VehicleType, Warehouse
from app.modules.orders.models import OrderPart, TempGroup
from app.modules.planning.models import PlanningRun, RunStatus, RunTrigger
from app.modules.routing import service as routing
from app.modules.routing.service import Point, Profile
from app.modules.tenancy.models import CompanySettings
from optimization import Depot, Job, Problem, Solution, solve
from optimization import Vehicle as SolverVehicle

log = logging.getLogger(__name__)

ALL = PageParams(limit=500)
GRAMS = 1000
TEMP_LABEL = {TempGroup.DRY: "hàng khô", TempGroup.COLD: "hàng lạnh/đông"}
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
) -> PlanningRun:
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


def _profile(vehicle: Vehicle) -> Profile:
    return Profile.MOTORBIKE if vehicle.vehicle_type == VehicleType.MOTORBIKE else Profile.CAR


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


def _compatible(part: OrderPart, vehicles: list[Vehicle]) -> list[Vehicle]:
    requirement = part.order.customer.required_vehicle_type
    return [
        v
        for v in vehicles
        if dispatch.cargo_compatible(v.cargo_class, part.temp_group)
        and dispatch.vehicle_matches(requirement, v.vehicle_type)
        and part.weight_kg <= v.capacity_kg
    ]


def _needs(part: OrderPart) -> dict[uuid.UUID, Decimal]:
    needed: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for line in part.order.lines:
        if line.temp_group == part.temp_group:
            needed[line.product_id] += line.qty
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
) -> _Allocation:
    """Chọn kho xuất cho từng phần đơn (tham lam). `stock=None`: không xét tồn kho."""
    result = _Allocation()
    remaining = dict(stock or {})
    by_point: dict[uuid.UUID, list[OrderPart]] = defaultdict(list)
    for part in parts:
        by_point[part.order.delivery_point_id].append(part)

    def candidates(part: OrderPart) -> list[Warehouse]:
        return [w for w in warehouses if any(w.id in v.warehouse_ids for v in compatible[part.id])]

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
            {v.id for v in compatible[p.id] if warehouse_id in v.warehouse_ids} for p in group
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
                )
            )
            info[job_id] = _JobInfo([p.id for p in chunk], point_id, warehouse_id)
    return jobs, info, unassigned


# --- Chạy ------------------------------------------------------------------------------


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

    # Lượt còn lại của mỗi xe (trừ các lệnh đã có trong ngày).
    used: dict[uuid.UUID, int] = defaultdict(int)
    for trip in await dispatch.list_trips(session, plan_date=plan_date):
        if trip.order_status != TripOrderStatus.CANCELLED:
            used[trip.vehicle_id] += 1
    remaining_trips = {v.id: settings.max_trips_per_vehicle - used[v.id] for v in vehicles}
    if any(n < settings.max_trips_per_vehicle for n in remaining_trips.values()):
        warnings.append("Một số xe đã có lệnh trong ngày: chỉ dùng số lượt còn lại")
    usable = [v for v in vehicles if remaining_trips[v.id] > 0]

    unassigned: dict[uuid.UUID, str] = {}
    compatible: dict[uuid.UUID, list[Vehicle]] = {}
    feasible: list[OrderPart] = []
    for part in parts:
        reason = _infeasible_reason(part, vehicles)
        if reason is None and not _compatible(part, usable):
            reason = "Các xe phù hợp đã dùng hết số lượt trong ngày"
        if reason is not None:
            unassigned[part.id] = reason
            continue
        compatible[part.id] = _compatible(part, usable)
        feasible.append(part)

    stock = await dispatch.stock_available(session)
    if not stock:
        warnings.append("Chưa có dữ liệu tồn kho: chọn kho gần nhất, không kiểm tra tồn")
    allocation = allocate_warehouses(feasible, compatible, warehouses, stock or None)
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
        feasible, allocation, compatible, location_of, settings.service_minutes * 60
    )
    unassigned.update(merge_unassigned)

    sources: set[str] = set()
    matrices = {}
    for profile in {_profile(v) for v in usable} or {Profile.CAR}:
        matrices[str(profile)], source = await routing.matrix(locations, profile)
        sources.add(source)
    run.distance_source = "estimate" if "estimate" in sources else sorted(sources)[0]
    if run.distance_source == "estimate":
        warnings.append("Khoảng cách ước lượng theo đường chim bay (chưa dùng OSRM)")

    shift_start = settings.shift_start.hour * 3600 + settings.shift_start.minute * 60
    shift_end = settings.shift_end.hour * 3600 + settings.shift_end.minute * 60
    local_now = now().astimezone(tz)
    if plan_date == local_now.date():
        # Lập trong ngày: chuyến chỉ xuất phát từ bây giờ (+15 phút chuẩn bị).
        shift_start = max(shift_start, _seconds(local_now + timedelta(minutes=15)))
    problem = Problem(
        depots=[Depot(str(w.id), location_of[w.id]) for w in warehouses],
        vehicles=[
            SolverVehicle(
                id=str(v.id),
                profile=str(_profile(v)),
                capacity=int(v.capacity_kg * GRAMS),
                cost_per_km=float(v.cost_per_km),
                depot_ids=tuple(str(w) for w in v.warehouse_ids if w in active_wh),
                max_trips=remaining_trips[v.id],
                fixed_cost=settings.trip_fixed_cost,
            )
            for v in usable
        ],
        jobs=jobs,
        matrices=matrices,
        shift_start_s=shift_start,
        shift_end_s=max(shift_end, shift_start),
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
        "shift": [shift_start, shift_end],
        "settings": {
            "service_minutes": settings.service_minutes,
            "turnaround_minutes": settings.turnaround_minutes,
            "max_trips_per_vehicle": settings.max_trips_per_vehicle,
            "trip_fixed_cost": settings.trip_fixed_cost,
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
    stops = [
        _point(s.delivery_point)
        if s.delivery_point
        else (float(s.latitude or 0), float(s.longitude or 0))
        for s in trip.stops
    ]
    depot = _point(trip.warehouse)
    meters = await routing.route_distance_m([depot, *stops, depot], _profile(trip.vehicle))
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
