"""Bờ sông và chi phí qua sông cho xe máy (thuần Python, không truy cập DB).

Sông là đường tâm (danh sách điểm vĩ độ, kinh độ) chạy qua vùng phục vụ. Bờ của một điểm = phía
của điểm so với đoạn sông gần nhất; điểm nằm ngoài 2 đầu đường tâm thì không xét (không có bờ).
Tọa độ được chiếu phẳng quanh vĩ độ của điểm (đủ chính xác trong phạm vi một thành phố).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

type Point = tuple[float, float]  # (vĩ độ, kinh độ)

DETOUR_FACTOR = 1.35  # quãng đường thực / đường chim bay (như ước lượng của module routing)
EARTH_RADIUS_M = 6_371_000


def haversine_m(a: Point, b: Point) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def side(point: Point, path: Sequence[Point]) -> int | None:
    """1 hoặc -1 theo phía của điểm so với đường tâm sông; None nếu điểm ở ngoài 2 đầu sông."""
    k = math.cos(math.radians(point[0]))
    px, py = point[1] * k, point[0]
    best: tuple[float, int, float] | None = None  # (khoảng cách², chỉ số đoạn, t)
    for i in range(len(path) - 1):
        ax, ay = path[i][1] * k, path[i][0]
        bx, by = path[i + 1][1] * k, path[i + 1][0]
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        t = 0.0 if length == 0 else ((px - ax) * dx + (py - ay) * dy) / length
        tc = min(1.0, max(0.0, t))
        d2 = (px - ax - tc * dx) ** 2 + (py - ay - tc * dy) ** 2
        if best is None or d2 < best[0]:
            best = (d2, i, t)
    if best is None:
        return None
    _, i, t = best
    if (i == 0 and t < 0) or (i == len(path) - 2 and t > 1):
        return None
    ax, ay = path[i][1] * k, path[i][0]
    bx, by = path[i + 1][1] * k, path[i + 1][0]
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if cross == 0:
        return None
    return 1 if cross > 0 else -1


@dataclass(frozen=True)
class Bridge:
    name: str
    location: Point
    penalty: int  # đồng mỗi lần xe máy qua cầu


@dataclass(frozen=True)
class River:
    name: str
    path: Sequence[Point]
    bridges: Sequence[Bridge]


@dataclass(frozen=True)
class Crossing:
    river: str
    bridge: str
    cost: int  # phạt của cầu + chi phí đi vòng đến cầu


def crossing(a: Point, b: Point, river: River, rate_per_km: float) -> Crossing | None:
    """Cầu xe máy sẽ chọn khi đi từ a đến b (chi phí phạt + đi vòng nhỏ nhất); None nếu cùng bờ."""
    sa, sb = side(a, river.path), side(b, river.path)
    if sa is None or sb is None or sa == sb or not river.bridges:
        return None
    return _best_bridge(a, b, river, rate_per_km)


def _best_bridge(a: Point, b: Point, river: River, rate_per_km: float) -> Crossing:
    direct = haversine_m(a, b)
    options = []
    for bridge in river.bridges:
        detour_m = max(
            0.0, haversine_m(a, bridge.location) + haversine_m(bridge.location, b) - direct
        )
        options.append(
            (bridge.penalty + detour_m * DETOUR_FACTOR * rate_per_km / 1000, bridge.name)
        )
    cost, name = min(options)
    return Crossing(river.name, name, round(cost))


def penalty_matrix(
    points: Sequence[Point], rivers: Sequence[River], rate_per_km: float
) -> list[list[int]]:
    """Chi phí qua sông (đồng) giữa mọi cặp điểm, cộng vào chi phí di chuyển của xe máy."""
    n = len(points)
    sides = [[side(p, r.path) for p in points] for r in rivers]
    out = [[0] * n for _ in range(n)]
    for r, river in enumerate(rivers):
        if not river.bridges:
            continue
        for i in range(n):
            for j in range(i + 1, n):
                si, sj = sides[r][i], sides[r][j]
                if si is None or sj is None or si == sj:
                    continue
                cost = _best_bridge(points[i], points[j], river, rate_per_km).cost
                out[i][j] += cost
                out[j][i] += cost
    return out
