"""Giải VRP bằng OR-Tools: đa kho, đa lượt/xe, tải trọng, ca làm việc, tương thích xe."""

import itertools
from collections import defaultdict
from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from optimization.model import Job, Matrix, Problem, Route, Solution, Vehicle, Window


@dataclass(frozen=True)
class _Slot:
    """Xe ảo = 1 lượt của 1 xe vật lý, xuất phát và kết thúc tại 1 kho."""

    vehicle: Vehicle
    depot_id: str
    depot_location: int


def _clip(windows: tuple[Window, ...], start: int, end: int) -> tuple[Window, ...]:
    return tuple(
        sorted((max(a, start), min(b, end)) for a, b in windows if max(a, start) <= min(b, end))
    )


def _slots(problem: Problem) -> list[_Slot]:
    depots = {d.id: d for d in problem.depots}
    shift = ((problem.shift_start_s, problem.shift_end_s),)
    slots = []
    for vehicle in problem.vehicles:
        # Xếp xen kẽ theo lượt (A1, B1, A2, B2...) - thứ tự này là chuỗi thời gian của xe.
        for _ in range(vehicle.max_trips):
            for depot_id in vehicle.depot_ids:
                # Kho không được rời trong ca (kho trong vùng hạn chế) thì không có xe ảo.
                windows = vehicle.depot_windows.get(depot_id, shift)
                usable = _clip(windows, problem.shift_start_s, problem.shift_end_s)
                if depot_id in depots and usable:
                    slots.append(_Slot(vehicle, depot_id, depots[depot_id].location))
    return slots


@dataclass(frozen=True)
class _Node:
    """Một phương án phục vụ 1 điểm: các xe ảo dùng chung khung giờ. Điểm có xe bị giới hạn giờ
    tách thành nhiều node trong 1 disjunction, mỗi node khung giờ riêng (bộ giải xử lý khung giờ
    trên node rất tốt, khác với ràng buộc có điều kiện theo xe)."""

    job: Job
    windows: tuple[Window, ...]
    slots: tuple[int, ...]


def _nodes(problem: Problem, slots: list[_Slot]) -> list[list[_Node]]:
    shift = ((problem.shift_start_s, problem.shift_end_s),)
    out: list[list[_Node]] = []
    for job in problem.jobs:
        groups: dict[tuple[Window, ...], list[int]] = defaultdict(list)
        for v, slot in enumerate(slots):
            if slot.depot_id == job.depot_id and slot.vehicle.id in job.vehicle_ids:
                windows = job.vehicle_windows.get(slot.vehicle.id, shift)
                clipped = _clip(windows, problem.shift_start_s, problem.shift_end_s)
                if clipped:
                    groups[clipped].append(v)
        out.append(
            [_Node(job, windows, tuple(vs)) for windows, vs in groups.items()]
            or [_Node(job, (), ())]
        )
    return out


def _restrict(var: pywrapcp.IntVar, windows: tuple[Window, ...]) -> None:
    """Giới hạn biến thời gian trong các khung giờ (đã sắp xếp)."""
    var.SetRange(windows[0][0], max(b for _, b in windows))
    for (_, end), (next_start, _) in itertools.pairwise(windows):
        if next_start > end + 1:
            var.RemoveInterval(end + 1, next_start - 1)


def _simulate(
    node_seq: list[_Node], first_leg: int, legs: list[int], start: int, back: int
) -> tuple[int, list[int], int]:
    """Lịch thực tế của 1 lượt: đi muộn nhất có thể để không phải chờ ở điểm đầu tiên có khung giờ,
    các điểm sau nối tiếp (chờ khung giờ nếu cần). Trả (giờ đi, giờ đến từng điểm, giờ về).

    `legs[i]` = thời gian đi từ điểm i đến điểm i+1, không gồm phục vụ."""
    arrivals: list[int] = []
    clock = start
    for node, leg in zip(node_seq, [first_leg, *legs], strict=True):
        clock += leg
        arrival = next((max(clock, a) for a, b in node.windows if clock <= b), clock)
        arrivals.append(arrival)
        clock = arrival + node.job.service_s
    delay = 0
    probe = start
    for node, leg, arrival in zip(node_seq, [first_leg, *legs], arrivals, strict=True):
        probe += leg
        if arrival > probe:
            delay = arrival - probe
            break
        probe = arrival + node.job.service_s
    return start + delay, arrivals, clock + back


def solve(problem: Problem) -> Solution:
    slots = _slots(problem)
    jobs = problem.jobs
    if not jobs:
        return Solution()
    if not slots:
        return Solution(unassigned=[j.id for j in jobs], status="NO_VEHICLE")

    # Node 0..len(nodes)-1 là các phương án phục vụ điểm giao, sau đó mỗi xe ảo có 1 node kho riêng.
    alternatives = _nodes(problem, slots)
    nodes = [n for group in alternatives for n in group]
    node_location = [n.job.location for n in nodes] + [s.depot_location for s in slots]
    depot_node = [len(nodes) + i for i in range(len(slots))]
    manager = pywrapcp.RoutingIndexManager(len(node_location), len(slots), depot_node, depot_node)
    routing = pywrapcp.RoutingModel(manager)
    service = [n.job.service_s for n in nodes] + [0] * len(slots)
    demand = [n.job.demand for n in nodes] + [0] * len(slots)

    def location(index: int) -> int:
        return node_location[int(manager.IndexToNode(index))]

    # Chi phí di chuyển theo profile và đơn giá/km của từng xe (đơn vị: đồng).
    cost_callbacks: dict[tuple[str, float, str | None], int] = {}
    time_callbacks: dict[str, int] = {}
    for v, slot in enumerate(slots):
        matrix = problem.matrices[slot.vehicle.profile]
        key = (slot.vehicle.profile, slot.vehicle.cost_per_km, slot.vehicle.penalty)
        if key not in cost_callbacks:
            penalty = problem.penalties.get(slot.vehicle.penalty or "")

            def arc_cost(
                i: int,
                j: int,
                m: Matrix = matrix,
                rate: float = slot.vehicle.cost_per_km,
                extra: list[list[int]] | None = penalty,
            ) -> int:
                a, b = location(i), location(j)
                cost = int(m.distance_m[a][b] * rate / 1000)
                return cost + extra[a][b] if extra is not None else cost

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
    shift = (problem.shift_start_s, problem.shift_end_s)
    for i, node in enumerate(nodes):
        _restrict(time.CumulVar(manager.NodeToIndex(i)), node.windows or (shift,))
    for v, slot in enumerate(slots):
        windows = _clip(slot.vehicle.depot_windows.get(slot.depot_id, (shift,)), *shift)
        for var in (routing.Start(v), routing.End(v)):
            _restrict(time.CumulVar(var), windows)
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

    offset = 0
    for group in alternatives:
        indices = [manager.NodeToIndex(offset + i) for i in range(len(group))]
        for index, node in zip(indices, group, strict=True):
            if not node.slots:
                solver.Add(routing.ActiveVar(index) == 0)
            else:
                # -1 = không được phục vụ (bị bỏ). SetAllowedVehiclesForIndex lỗi binding ở 9.15.
                routing.VehicleVar(index).SetValues([-1, *node.slots])
        routing.AddDisjunction(indices, problem.drop_penalty, 1)
        offset += len(group)

    params = pywrapcp.DefaultRoutingSearchParameters()
    # Bắt đầu từ "chưa xếp điểm nào" rồi để GLS chèn dần. PATH_CHEAPEST_ARC đôi khi kẹt ở nghiệm
    # bỏ toàn bộ điểm (đo trên bộ 100 điểm, kể cả khi không có khung giờ theo xe).
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.ALL_UNPERFORMED
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
        seq: list[_Node] = []
        legs: list[int] = []
        load, distance = 0, 0
        prev_loc = slot.depot_location
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            seq.append(nodes[node])
            load += demand[node]
            distance += matrix.distance_m[prev_loc][node_location[node]]
            legs.append(matrix.duration_s[prev_loc][node_location[node]])
            prev_loc = node_location[node]
            index = assignment.Value(routing.NextVar(index))
        distance += matrix.distance_m[prev_loc][slot.depot_location]
        start_s, arrivals, end_s = _simulate(
            seq,
            legs[0],
            legs[1:],
            assignment.Value(time.CumulVar(routing.Start(v))),
            matrix.duration_s[prev_loc][slot.depot_location],
        )
        job_ids = [n.job.id for n in seq]
        served.update(job_ids)
        routes.append(
            Route(
                vehicle_id=slot.vehicle.id,
                depot_id=slot.depot_id,
                trip_seq=0,
                job_ids=job_ids,
                arrivals_s=arrivals,
                distance_m=distance,
                start_s=start_s,
                end_s=end_s,
                load=load,
                cost=distance * slot.vehicle.cost_per_km / 1000,
            )
        )
    # Đánh số lượt theo giờ xuất phát của từng xe.
    routes.sort(key=lambda r: (r.vehicle_id, r.start_s))
    trip_no: dict[str, int] = defaultdict(int)
    for route in routes:
        trip_no[route.vehicle_id] += 1
        route.trip_seq = trip_no[route.vehicle_id]
    unassigned = [j.id for j in jobs if j.id not in served]
    return Solution(routes=routes, unassigned=unassigned)
