"""Bộ giải VRP (thuần Python): dữ liệu tổng hợp trên lưới, 1 đơn vị = 1 km, 30 km/h."""

import math

from optimization import Depot, Job, Matrix, Problem, Vehicle, solve

HOUR = 3600


def grid_matrix(points: list[tuple[float, float]], kmh: float = 30) -> Matrix:
    dist = [[round(math.dist(a, b) * 1000) for b in points] for a in points]
    return Matrix(
        distance_m=dist, duration_s=[[round(d / 1000 / kmh * HOUR) for d in row] for row in dist]
    )


def problem(points: list[tuple[float, float]], **kw: object) -> Problem:
    m = grid_matrix(points)
    defaults: dict[str, object] = {
        "depots": [Depot("K1", 0)],
        "matrices": {"car": m, "motorbike": m},
        "shift_start_s": 7 * HOUR,
        "shift_end_s": 19 * HOUR,
        "time_limit_s": 2,
    }
    return Problem(**{**defaults, **kw})  # type: ignore[arg-type]


def car(id: str = "XE1", capacity: int = 1000, **kw: object) -> Vehicle:
    return Vehicle(
        id=id, profile="car", capacity=capacity, cost_per_km=5000, depot_ids=("K1",), **kw
    )  # type: ignore[arg-type]


def job(
    id: str, loc: int, demand: int = 100, vehicles: tuple[str, ...] = ("XE1",), **kw: object
) -> Job:
    return Job(id=id, location=loc, depot_id="K1", demand=demand, vehicle_ids=vehicles, **kw)  # type: ignore[arg-type]


def test_single_route_visits_all_in_good_order() -> None:
    # Kho ở gốc, 3 điểm trên một đường thẳng: tuyến tối ưu đi ra rồi quay về (20 km).
    pts = [(0, 0), (3, 0), (10, 0), (6, 0)]
    sol = solve(problem(pts, vehicles=[car()], jobs=[job("A", 1), job("B", 2), job("C", 3)]))
    assert sol.unassigned == []
    (route,) = sol.routes
    assert route.job_ids in (["A", "C", "B"], ["B", "C", "A"])
    assert route.distance_m == 20_000
    assert route.cost == 100_000  # 20 km x 5.000 đ
    assert route.load == 300 and route.trip_seq == 1


def test_capacity_forces_second_trip_after_turnaround() -> None:
    pts = [(0, 0), (5, 0), (0, 5)]
    sol = solve(
        problem(
            pts,
            vehicles=[car(capacity=100, max_trips=2)],
            jobs=[job("A", 1), job("B", 2)],
            turnaround_s=1800,
        )
    )
    assert sol.unassigned == []
    first, second = sorted(sol.routes, key=lambda r: r.trip_seq)
    assert (first.trip_seq, second.trip_seq) == (1, 2)
    assert second.start_s >= first.end_s + 1800


def test_vehicle_compatibility_respected() -> None:
    pts = [(0, 0), (2, 0), (0, 2)]
    bike = Vehicle("XM1", "motorbike", 100, 2000, ("K1",))
    sol = solve(
        problem(
            pts,
            vehicles=[car(), bike],
            jobs=[job("A", 1, 50, ("XM1",)), job("B", 2, 500, ("XE1",))],
        )
    )
    served_by = {j: r.vehicle_id for r in sol.routes for j in r.job_ids}
    assert served_by == {"A": "XM1", "B": "XE1"}


def test_not_enough_capacity_leaves_unassigned() -> None:
    pts = [(0, 0), (1, 0), (2, 0), (3, 0)]
    sol = solve(
        problem(
            pts,
            vehicles=[car(capacity=250)],
            jobs=[job("A", 1, 200), job("B", 2, 200), job("C", 3, 200)],
        )
    )
    assert len(sol.unassigned) == 2 and len(sol.routes) == 1


def test_shift_limit_drops_unreachable_and_respects_service_time() -> None:
    # Điểm cách 200 km (6h40 mỗi chiều) không kịp trong ca 7h-19h.
    pts = [(0, 0), (1, 0), (200, 0)]
    sol = solve(problem(pts, vehicles=[car()], jobs=[job("A", 1, service_s=600), job("FAR", 2)]))
    assert sol.unassigned == ["FAR"]
    (route,) = sol.routes
    assert route.end_s - route.start_s >= 600 + 2 * 120


def test_multi_depot_jobs_start_from_their_warehouse() -> None:
    pts = [(0, 0), (20, 0), (1, 0), (21, 0)]
    vehicle = Vehicle("XE1", "car", 1000, 5000, ("K1", "K2"), max_trips=2)
    jobs = [job("A", 2), Job("B", 3, "K2", 100, ("XE1",))]
    sol = solve(
        problem(pts, depots=[Depot("K1", 0), Depot("K2", 1)], vehicles=[vehicle], jobs=jobs)
    )
    assert sol.unassigned == []
    assert {r.depot_id: r.job_ids for r in sol.routes} == {"K1": ["A"], "K2": ["B"]}
    a, b = sorted(sol.routes, key=lambda r: r.trip_seq)
    assert b.start_s >= a.end_s


def test_fixed_cost_prefers_fewer_trips() -> None:
    pts = [(0, 0), (1, 0), (0, 1)]
    vehicles = [car("XE1", fixed_cost=1_000_000), car("XE2", fixed_cost=1_000_000)]
    jobs = [job("A", 1, vehicles=("XE1", "XE2")), job("B", 2, vehicles=("XE1", "XE2"))]
    sol = solve(problem(pts, vehicles=vehicles, jobs=jobs))
    assert len(sol.routes) == 1


def test_benchmark_100_points_two_depots() -> None:
    """~100 điểm, 2 kho, 4 xe (như công ty đầu tiên): phải giải xong và hợp lệ."""
    import random

    rnd = random.Random(42)
    pts: list[tuple[float, float]] = [(0, 0), (8, 6)]
    pts += [(rnd.uniform(-10, 18), rnd.uniform(-8, 14)) for _ in range(100)]
    vehicles = [
        Vehicle("TAI", "car", 2_000_000, 8000, ("K1", "K2"), max_trips=3, fixed_cost=200_000),
        Vehicle("VAN", "car", 945_000, 6000, ("K1", "K2"), max_trips=3, fixed_cost=150_000),
        Vehicle("XM1", "motorbike", 250_000, 2000, ("K1",), max_trips=4, fixed_cost=50_000),
        Vehicle("XM2", "motorbike", 250_000, 2000, ("K2",), max_trips=4, fixed_cost=50_000),
    ]
    all_ids = tuple(v.id for v in vehicles)
    jobs = []
    for i in range(100):
        weight = rnd.choice([20_000, 40_000, 80_000, 150_000])
        depot = "K1" if i % 2 else "K2"
        ok = (
            tuple(v.id for v in vehicles if depot in v.depot_ids and v.capacity >= weight)
            or all_ids
        )
        jobs.append(Job(f"J{i}", i + 2, depot, weight, ok, service_s=600))
    sol = solve(
        Problem(
            depots=[Depot("K1", 0), Depot("K2", 1)],
            vehicles=vehicles,
            jobs=jobs,
            matrices={"car": grid_matrix(pts, 25), "motorbike": grid_matrix(pts, 22)},
            shift_start_s=7 * HOUR,
            shift_end_s=19 * HOUR,
            turnaround_s=1800,
            time_limit_s=5,
        )
    )
    capacity = {v.id: v.capacity for v in vehicles}
    by_job = {j.id: j for j in jobs}
    seen = [j for r in sol.routes for j in r.job_ids]
    assert len(seen) == len(set(seen))
    assert len(seen) + len(sol.unassigned) == 100
    for r in sol.routes:
        assert r.load <= capacity[r.vehicle_id]
        assert all(by_job[j].depot_id == r.depot_id for j in r.job_ids)
        assert 7 * HOUR <= r.start_s <= r.end_s <= 19 * HOUR
    print(
        f"\n{len(sol.routes)} chuyến, {sol.distance_m / 1000:.1f} km, bỏ {len(sol.unassigned)} điểm"
    )
