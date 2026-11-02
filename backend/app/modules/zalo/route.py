"""Tuyến xe đã đi cho khách (D33): chỉ vẽ đường, không lộ vị trí điểm dừng của khách khác.

Đường đi = kho → các điểm xe đã đến theo thứ tự thời gian, kết thúc tại điểm của khách khi xe đã
đến đó (các điểm sau không hiện). Phần đường sát điểm dừng khác bị cắt nên một tuyến có thể thành
nhiều đoạn. Chưa có OSRM thì không có đường để vẽ (đường thẳng nối các điểm sẽ lộ đúng tọa độ).
"""

import uuid
from collections.abc import Sequence

from app.modules.dispatch import service as dispatch
from app.modules.dispatch.models import ItemStatus, Trip, TripStop
from app.modules.routing import service as routing
from app.modules.routing.service import Point
from app.modules.zalo.schemas import CustomerRoute, RoutePoint

TRIM_RADIUS_M = 200.0

LngLat = tuple[float, float]


def _visited(trip: Trip) -> list[TripStop]:
    """Điểm xe đã đến (có mục đã xác nhận, kể cả thất bại), theo giờ xác nhận sớm nhất."""
    first_seen = {}
    for stop in trip.stops:
        times = [
            item.delivered_at
            for item in stop.items
            if item.status in (ItemStatus.SUCCESS, ItemStatus.FAILED) and item.delivered_at
        ]
        if times:
            first_seen[stop.id] = min(times)
    return sorted((s for s in trip.stops if s.id in first_seen), key=lambda s: first_seen[s.id])


def trim_line(
    line: Sequence[LngLat], avoid: Sequence[Point], radius_m: float
) -> list[list[LngLat]]:
    """Bỏ các đỉnh trong bán kính quanh `avoid`; phần còn lại thành các đoạn (ít nhất 2 đỉnh)."""
    segments: list[list[LngLat]] = []
    current: list[LngLat] = []
    for lng, lat in line:
        if any(routing.haversine_m((lat, lng), p) <= radius_m for p in avoid):
            if len(current) > 1:
                segments.append(current)
            current = []
        else:
            current.append((lng, lat))
    if len(current) > 1:
        segments.append(current)
    return segments


async def customer_route(trip: Trip, own_stop_id: uuid.UUID) -> CustomerRoute:
    own = next(s for s in trip.stops if s.id == own_stop_id)
    visited = _visited(trip)
    reached = own in visited
    if reached:
        visited = visited[: visited.index(own) + 1]
    own_point = dispatch.stop_point(own)
    depot = (float(trip.warehouse.latitude), float(trip.warehouse.longitude))
    line = await routing.geometry(
        [depot, *(dispatch.stop_point(s) for s in visited)],
        dispatch.vehicle_profile(trip.vehicle),
    )
    others = [p for s in trip.stops if (p := dispatch.stop_point(s)) != own_point]
    return CustomerRoute(
        trip_code=trip.code,
        warehouse=RoutePoint(latitude=depot[0], longitude=depot[1]),
        destination=RoutePoint(latitude=own_point[0], longitude=own_point[1]),
        reached=reached,
        segments=trim_line(line or [], others, TRIM_RADIUS_M),
    )
