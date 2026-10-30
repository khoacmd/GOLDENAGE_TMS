"""Xác nhận giao hàng từ app mobile: kiểm tra quy tắc ở server, idempotent theo client_id."""

import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.core.storage import get_storage
from app.modules.delivery.models import DeliveryConfirmation, DeliveryPhoto
from app.modules.delivery.schemas import ConfirmationOut, ConfirmIn, PhotoOut
from app.modules.dispatch import service as dispatch
from app.modules.dispatch.models import ItemStatus, Trip, TripOrderStatus, TripStop
from app.modules.tenancy.models import CompanySettings

ALLOWED_PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
# Cho phép đồng hồ thiết bị chạy nhanh hơn server tối đa 5 phút.
CLOCK_SKEW = timedelta(minutes=5)
EARTH_RADIUS_M = 6_371_000


def utcnow() -> datetime:
    """Giờ server (tách riêng để test giả lập)."""
    return datetime.now(UTC)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def stop_location(stop: TripStop) -> tuple[float, float] | None:
    point = stop.delivery_point
    lat = point.latitude if point else stop.latitude
    lng = point.longitude if point else stop.longitude
    return (float(lat), float(lng)) if lat is not None and lng is not None else None


def ensure_member(trip: Trip, user_id: uuid.UUID) -> None:
    if user_id not in (trip.driver_id, trip.assistant_id):
        raise PermissionDeniedError("Bạn không được phân công cho chuyến này")


async def upload_photo(company_id: uuid.UUID, data: bytes, content_type: str) -> str:
    ext = ALLOWED_PHOTO_TYPES.get(content_type)
    if ext is None:
        raise AppError("Ảnh phải là JPEG, PNG hoặc WebP", code="invalid_photo")
    if not data or len(data) > get_settings().max_photo_bytes:
        raise AppError("Ảnh rỗng hoặc vượt dung lượng cho phép", code="invalid_photo")
    key = f"{company_id}/delivery/{datetime.now(UTC):%Y/%m/%d}/{uuid.uuid4().hex}.{ext}"
    await get_storage().put(key, data, content_type)
    return key


def to_out(c: DeliveryConfirmation) -> ConfirmationOut:
    storage = get_storage()
    fields = {f: getattr(c, f) for f in ConfirmationOut.model_fields if f != "photos"}
    photos = [PhotoOut(key=p.object_key, url=storage.url(p.object_key)) for p in c.photos]
    return ConfirmationOut(**fields, photos=photos)


async def check_rules(
    rules: CompanySettings,
    trip: Trip,
    stop: TripStop,
    data: ConfirmIn,
    received_at: datetime,
    company_id: uuid.UUID,
) -> tuple[list[str], dict[str, Any], float | None]:
    """Trả (vi phạm, chi tiết kiểm tra, khoảng cách tới điểm giao)."""
    violations: list[str] = []
    check: dict[str, Any] = {}
    tz = ZoneInfo(rules.timezone)

    delay = received_at - data.device_time
    check["delay_minutes"] = round(delay.total_seconds() / 60, 1)
    if delay < -CLOCK_SKEW:
        violations.append("Giờ trên thiết bị không đúng (nhanh hơn giờ hệ thống)")
    elif delay > timedelta(minutes=rules.offline_max_delay_minutes):
        violations.append(
            f"Xác nhận gửi quá muộn (sau {rules.offline_max_delay_minutes} phút kể từ lúc thao tác)"
        )

    if rules.confirm_time_rule:
        local = data.device_time.astimezone(tz)
        grace = timedelta(minutes=rules.confirm_grace_minutes)
        start = datetime.combine(trip.plan_date, rules.shift_start, tz) - grace
        end = datetime.combine(trip.plan_date, rules.shift_end, tz) + grace
        check["time_window"] = [start.isoformat(), end.isoformat()]
        if not start <= local <= end:
            violations.append(
                f"Ngoài thời gian cho phép ({start:%H:%M} - {end:%H:%M} "
                f"ngày {trip.plan_date:%d/%m})"
            )

    distance = None
    target = stop_location(stop)
    if data.latitude is not None and data.longitude is not None and target is not None:
        distance = haversine_m(float(data.latitude), float(data.longitude), *target)
        check["distance_m"] = round(distance, 1)
    if rules.confirm_geofence:
        check["radius_m"] = rules.confirm_radius_m
        if data.is_mock_location:
            violations.append("Thiết bị đang dùng vị trí giả lập")
        elif distance is None:
            violations.append("Không lấy được vị trí GPS")
        elif distance > rules.confirm_radius_m:
            violations.append(
                f"Cách điểm giao {distance:,.0f} m, "
                f"vượt bán kính cho phép {rules.confirm_radius_m} m"
            )

    photo_required = (
        rules.photo_required_success
        if data.status == ItemStatus.SUCCESS
        else rules.photo_required_failed
    )
    storage = get_storage()
    valid_photos = [
        k for k in data.photo_keys if k.startswith(f"{company_id}/") and await storage.exists(k)
    ]
    check["photos"] = len(valid_photos)
    if len(valid_photos) != len(data.photo_keys):
        violations.append("Ảnh chứng từ không hợp lệ hoặc chưa tải lên")
    elif photo_required and not valid_photos:
        violations.append("Cần chụp ảnh chứng từ giao nhận")
    return violations, check, distance


async def confirm(
    session: AsyncSession,
    company_id: uuid.UUID,
    trip: Trip,
    item_id: uuid.UUID,
    user_id: uuid.UUID,
    data: ConfirmIn,
) -> DeliveryConfirmation:
    existing = await session.scalar(
        select(DeliveryConfirmation).where(DeliveryConfirmation.client_id == data.client_id)
    )
    if existing is not None:
        return existing  # gửi lại (offline) → trả kết quả lần trước

    ensure_member(trip, user_id)
    if data.status not in (ItemStatus.SUCCESS, ItemStatus.FAILED):
        raise AppError("Chỉ xác nhận giao thành công hoặc không thành công", code="invalid_status")
    if data.status == ItemStatus.FAILED and not data.reason:
        raise AppError("Cần ghi lý do giao không thành công", code="reason_required")
    if trip.order_status != TripOrderStatus.DISPATCHED:
        raise AppError("Chuyến chưa xuất phát hoặc đã kết thúc", code="invalid_status")
    stop = next((s for s in trip.stops if any(i.id == item_id for i in s.items)), None)
    if stop is None:
        raise NotFoundError("Không tìm thấy mục hàng trong chuyến")
    item = next(i for i in stop.items if i.id == item_id)
    if item.status != ItemStatus.PENDING:
        raise AppError("Mục hàng đã có kết quả giao", code="already_confirmed")

    rules = await session.get(CompanySettings, company_id)
    assert rules is not None
    received_at = utcnow()
    violations, check, distance = await check_rules(
        rules, trip, stop, data, received_at, company_id
    )
    confirmation = DeliveryConfirmation(
        company_id=company_id,
        client_id=data.client_id,
        trip_id=trip.id,
        item_id=item_id,
        user_id=user_id,
        status=data.status,
        reason=data.reason,
        device_time=data.device_time,
        latitude=data.latitude,
        longitude=data.longitude,
        accuracy_m=data.accuracy_m,
        is_mock_location=data.is_mock_location,
        distance_m=Decimal(str(round(distance, 1))) if distance is not None else None,
        accepted=not violations,
        violations=violations,
        rule_check=check,
        photos=[DeliveryPhoto(company_id=company_id, object_key=k) for k in data.photo_keys],
    )
    session.add(confirmation)
    if not violations:
        await dispatch.update_item(
            session,
            trip,
            item_id,
            data.status,
            reason=data.reason,
            delivered_at=data.device_time,
            actor_id=user_id,
            manual=False,
        )
    await session.flush()
    return confirmation


async def list_for_trip(session: AsyncSession, trip_id: uuid.UUID) -> list[DeliveryConfirmation]:
    stmt = (
        select(DeliveryConfirmation)
        .where(DeliveryConfirmation.trip_id == trip_id)
        .order_by(DeliveryConfirmation.created_at)
    )
    return list(await session.scalars(stmt))
