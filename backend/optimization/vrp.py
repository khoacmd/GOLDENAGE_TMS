"""Giải VRP bằng OR-Tools: đa kho, đa lượt/xe, tải trọng, ca làm việc, tương thích xe."""

import itertools
from collections import defaultdict
from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from optimization.model import Matrix, Problem, Route, Solution, Vehicle


@dataclass(frozen=True)
class _Slot:
    """Xe ảo = 1 lượt của 1 xe vật lý, xuất phát và kết thúc tại 1 kho."""

    vehicle: Vehicle
    depot_id: str
    depot_location: int


def _slots(problem: Problem) -> list[_Slot]:
    depots = {d.id: d for d in problem.depots}
    slots = []
    for vehicle in problem.vehicles:
        # Xếp xen kẽ theo lượt (A1, B1, A2, B2...) - thứ tự này là chuỗi thời gian của xe.
        for _ in range(vehicle.max_trips):
            for depot_id in vehicle.depot_ids:
                if depot_id in depots:
                    slots.append(_Slot(vehicle, depot_id, depots[depot_id].location))
    return slots


def solve(problem: Problem) -> Solution:
    slots = _slots(problem)
    jobs = problem.jobs
    if not jobs:
        return Solution()
    if not slots:
        return Solution(unassigned=[j.id for j in jobs], status="NO_VEHICLE")

    # Node 0..len(jobs)-1 là điểm giao, sau đó mỗi xe ảo có 1 node kho riêng (start = end).
    node_location = [j.location for j in jobs] + [s.depot_location for s in slots]
    depot_node = [len(jobs) + i for i in range(len(slots))]
    manager = pywrapcp.RoutingIndexManager(len(node_location), len(slots), depot_node, depot_node)
    routing = pywrapcp.RoutingModel(manager)
    service = [j.service_s for j in jobs] + [0] * len(slots)
    demand = [j.demand for j in jobs] + [0] * len(slots)

    def location(index: int) -> int:
        return node_location[int(manager.IndexToNode(index))]

    # Chi phí di chuyển theo profile và đơn giá/km của từng xe (đơn vị: đồng).
    cost_callbacks: dict[tuple[str, float], int] = {}
    time_callbacks: dict[str, int] = {}
    for v, slot in enumerate(slots):
        matrix = problem.matrices[slot.vehicle.profile]
        key = (slot.vehicle.profile, slot.vehicle.cost_per_km)
        if key not in cost_callbacks:

            def arc_cost(
                i: int, j: int, m: Matrix = matrix, rate: float = slot.vehicle.cost_per_km
            ) -> int:
                return int(m.distance_m[location(i)][location(j)] * rate / 1000)

            cost_callbacks[key] = routing.RegisterTransitCallback(arc_cost)
        routing.SetArcCostEvaluatorOfVehicle(cost_callbacks[key], v)
        routing.SetFixedCostOfVehicle(slot.vehicle.fixed_cost, v)
        if slot.vehicle.profile not in time_callbacks:

            def travel(i: int, j: int, m: Matrix = matrix) -> int:
                return service[int(manager.IndexToNode(i))] + m.duration_s[location(i)][location(j)]

            time_callbacks[slot.vehicle.profile] = routing.RegisterTransitCallback(travel)

    load_cb = routing.RegisterUnaryTransitCallback(lambda i: demand[manager.IndexToNode(i)])
    routing.AddDimensionWithVehicleCapacity(
        load_cb, 0, [s.vehicle.capacity for s in slots], True, "Load"
    )
    routing.AddDimensionWithVehicleTransits(
        [time_callbacks[s.vehicle.profile] for s in slots],
        problem.shift_end_s,  # cho phép chờ
        problem.shift_end_s,
        False,
        "Time",
    )
    time = routing.GetDimensionOrDie("Time")
    for node in range(len(jobs)):
        time.CumulVar(manager.NodeToIndex(node)).SetRange(
            problem.shift_start_s, problem.shift_end_s
        )
    for v in range(len(slots)):
        time.CumulVar(routing.Start(v)).SetRange(problem.shift_start_s, problem.shift_end_s)
        time.CumulVar(routing.End(v)).SetRange(problem.shift_start_s, problem.shift_end_s)
        routing.AddVariableMinimizedByFinalizer(time.CumulVar(routing.Start(v)))
        routing.AddVariableMinimizedByFinalizer(time.CumulVar(routing.End(v)))

    # Các lượt của cùng 1 xe nối tiếp nhau theo thời gian (+ quay đầu tại kho nếu lượt trước chạy).
    solver = routing.solver()
    by_vehicle: dict[str, list[int]] = defaultdict(list)
    for v, slot in enumerate(slots):
        by_vehicle[slot.vehicle.id].append(v)
    for vehicle in problem.vehicles:
        chain = by_vehicle[vehicle.id]
        for prev, nxt in itertools.pairwise(chain):
            solver.Add(
                time.CumulVar(routing.Start(nxt))
                >= time.CumulVar(routing.End(prev))
                + problem.turnaround_s * routing.ActiveVehicleVar(prev)
            )
        actives = [routing.ActiveVehicleVar(v) for v in chain]
        if actives:
            solver.Add(solver.Sum(actives) <= vehicle.max_trips)
        # Phá đối xứng: lượt k+1 tại 1 kho chỉ dùng khi lượt k tại kho đó đã dùng.
        per_depot: dict[str, list[int]] = defaultdict(list)
        for v in chain:
            per_depot[slots[v].depot_id].append(v)
        for same in per_depot.values():
            for prev, nxt in itertools.pairwise(same):
                solver.Add(routing.ActiveVehicleVar(nxt) <= routing.ActiveVehicleVar(prev))

    for node, job in enumerate(jobs):
        index = manager.NodeToIndex(node)
        allowed = [
            v
            for v, s in enumerate(slots)
            if s.depot_id == job.depot_id and s.vehicle.id in job.vehicle_ids
        ]
        if not allowed:
            solver.Add(routing.ActiveVar(index) == 0)
        else:
            # -1 = không được phục vụ (bị bỏ). SetAllowedVehiclesForIndex lỗi binding ở 9.15.
            routing.VehicleVar(index).SetValues([-1, *allowed])
        routing.AddDisjunction([index], problem.drop_penalty)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(problem.time_limit_s)
    assignment = routing.SolveWithParameters(params)
    if assignment is None:
        return Solution(unassigned=[j.id for j in jobs], status="NO_SOLUTION")

    routes: list[Route] = []
    served: set[str] = set()
    for v, slot in enumerate(slots):
        index = routing.Start(v)
        index = assignment.Value(routing.NextVar(index))
        if routing.IsEnd(index):
            continue
        matrix = problem.matrices[slot.vehicle.profile]
        job_ids, load, distance = [], 0, 0
        prev_loc = slot.depot_location
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            job_ids.append(jobs[node].id)
            load += demand[node]
            distance += matrix.distance_m[prev_loc][node_location[node]]
            prev_loc = node_location[node]
            index = assignment.Value(routing.NextVar(index))
        distance += matrix.distance_m[prev_loc][slot.depot_location]
        served.update(job_ids)
        routes.append(
            Route(
                vehicle_id=slot.vehicle.id,
                depot_id=slot.depot_id,
                trip_seq=0,
                job_ids=job_ids,
                distance_m=distance,
                start_s=assignment.Value(time.CumulVar(routing.Start(v))),
                end_s=assignment.Value(time.CumulVar(routing.End(v))),
                load=load,
                cost=distance * slot.vehicle.cost_per_km / 1000,
            )
        )
    # Đánh số lượt theo giờ xuất phát của từng xe.
    routes.sort(key=lambda r: (r.vehicle_id, r.start_s))
    seq: dict[str, int] = defaultdict(int)
    for route in routes:
        seq[route.vehicle_id] += 1
        route.trip_seq = seq[route.vehicle_id]
    unassigned = [j.id for j in jobs if j.id not in served]
    return Solution(routes=routes, unassigned=unassigned)
