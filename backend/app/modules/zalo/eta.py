"""Giờ đến dự kiến của các điểm dừng còn lại trên chuyến đang giao.

Tính khi đọc theo trạng thái hiện tại nên luôn khớp thứ tự điểm dừng, kể cả sau khi quản lý sửa
lệnh: mốc = lần xác nhận giao gần nhất (hoặc giờ xuất phát) + thời gian di chuyển (OSRM x hệ số kẹt
xe) + thời gian phục vụ các điểm trước đó. Xe chưa xác nhận điểm kế tiếp thì không thể đã đến trong
quá khứ, nên giờ đến không sớm hơn hiện tại (trễ thì đẩy lùi cả các điểm sau).
"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.dispatch import service as dispatch
from app.modules.dispatch.models import ItemStatus, Trip, TripOrderStatus, TripStop
from app.modules.routing import service as routing
from app.modules.tenancy.models import CompanySettings
from app.modules.zalo.schemas import CustomerEta

MIN_MARGIN = timedelta(minutes=10)
MARGIN_RATIO = 0.2  # sai số 20% thời gian còn lại, tối thiểu MIN_MARGIN


def utcnow() -> datetime:
    """Giờ server (tách riêng để test giả lập)."""
    return datetime.now(UTC)


def _window(arrival: datetime, now: datetime) -> CustomerEta:
    margin = max(MIN_MARGIN, (arrival - now) * MARGIN_RATIO)
    return CustomerEta(earliest=max(now, arrival - margin), latest=arrival + margin)


def _anchor(trip: Trip, now: datetime) -> tuple[datetime, TripStop | None]:
    """Lần xác nhận giao gần nhất (kèm điểm dừng), chưa có thì giờ xuất phát tại kho."""
    start = trip.dispatched_at or now
    done = [
        (item.delivered_at, stop)
        for stop in trip.stops
        for item in stop.items
        if item.status in (ItemStatus.SUCCESS, ItemStatus.FAILED) and item.delivered_at
    ]
    if not done:
        return start, None
    latest, stop = max(done, key=lambda d: d[0])
    return max(latest, start), stop


def _not_before_window(
    clock: datetime, windows: tuple[tuple[int, int], ...], tz: ZoneInfo
) -> datetime:
    """Xe bị giới hạn giờ vào vùng: chưa đến khung giờ thì phải chờ, ETA không được sớm hơn."""
    local = clock.astimezone(tz)
    second = local.hour * 3600 + local.minute * 60 + local.second
    start = next((a for a, b in windows if second <= b), None)
    if start is None or start <= second:
        return clock
    return clock + timedelta(seconds=start - second)


async def stop_etas(
    trip: Trip,
    settings: CompanySettings,
    windows: dict[uuid.UUID, tuple[tuple[int, int], ...]] | None = None,
) -> dict[uuid.UUID, CustomerEta]:
    """Điểm dừng còn mục chưa giao → khoảng giờ đến; rỗng nếu chuyến không đang giao."""
    if trip.order_status != TripOrderStatus.DISPATCHED:
        return {}
    remaining = [s for s in trip.stops if any(i.status == ItemStatus.PENDING for i in s.items)]
    if not remaining:
        return {}
    now = utcnow()
    clock, anchor = _anchor(trip, now)
    depot = (float(trip.warehouse.latitude), float(trip.warehouse.longitude))
    origin = dispatch.stop_point(anchor) if anchor else depot
    points = [origin, *(dispatch.stop_point(s) for s in remaining)]
    matrix, _ = await routing.matrix(
        points, dispatch.vehicle_profile(trip.vehicle), settings.travel_time_factor
    )
    service = timedelta(minutes=settings.service_minutes)
    etas: dict[uuid.UUID, CustomerEta] = {}
    for index, stop in enumerate(remaining, start=1):
        clock = max(clock + timedelta(seconds=matrix.duration_s[index - 1][index]), now)
        if windows and stop.id in windows:
            clock = _not_before_window(clock, windows[stop.id], ZoneInfo(settings.timezone))
        etas[stop.id] = _window(clock, now)
        if stop is not anchor:  # đang ở điểm này (mới giao một phần) thì đã tính giờ phục vụ
            clock += service
    return etas
