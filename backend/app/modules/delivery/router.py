import uuid
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.core.auth import CurrentUser, OfficeStaffDep, require_roles
from app.core.db import DbSession
from app.modules.delivery import service
from app.modules.delivery.schemas import ConfirmationOut, ConfirmIn, UploadedPhoto
from app.modules.devices import service as devices
from app.modules.devices.schemas import DeviceRegister, RegisteredDevice
from app.modules.dispatch import service as dispatch
from app.modules.dispatch.models import TripOrderStatus
from app.modules.dispatch.router import summary_out, trip_out
from app.modules.dispatch.schemas import TripOut, TripSummaryOut
from app.modules.identity.models import CompanyRole
from app.modules.tenancy.models import CompanySettings
from app.modules.tenancy.schemas import DeliveryRules

driver_router = APIRouter(prefix="/driver", tags=["driver"])
confirmations_router = APIRouter(prefix="/trips", tags=["dispatch"])

DriverDep = Annotated[CurrentUser, Depends(require_roles(CompanyRole.DRIVER))]
VISIBLE_TO_DRIVER = [
    TripOrderStatus.APPROVED,
    TripOrderStatus.PREPARED,
    TripOrderStatus.PICKED,
    TripOrderStatus.DISPATCHED,
    TripOrderStatus.CLOSED,
]


@driver_router.get("/rules")
async def rules(user: DriverDep, session: DbSession) -> DeliveryRules:
    settings = await session.get(CompanySettings, user.cid)
    return DeliveryRules.model_validate(settings, from_attributes=True)


@driver_router.post("/device")
async def register_device(
    body: DeviceRegister, user: DriverDep, session: DbSession
) -> RegisteredDevice:
    """App gọi khi đăng nhập / mở app; trả trạng thái duyệt của thiết bị."""
    settings = await session.get(CompanySettings, user.cid)
    assert settings is not None
    device = await devices.register_mobile(
        session,
        user.cid,
        user.id,
        user.username,
        body,
        require_approval=settings.require_device_approval,
    )
    await session.commit()
    return RegisteredDevice.model_validate(device)


@driver_router.get("/trips")
async def my_trips(
    user: DriverDep,
    session: DbSession,
    plan_date: Annotated[date | None, Query(description="Mặc định: hôm nay")] = None,
) -> list[TripSummaryOut]:
    """Chuyến đã duyệt được phân công cho tôi (lái xe hoặc phụ xe)."""
    if plan_date is None:
        settings = await session.get(CompanySettings, user.cid)
        plan_date = datetime.now(ZoneInfo(settings.timezone if settings else "UTC")).date()
    trips = await dispatch.list_trips(
        session, plan_date=plan_date, statuses=VISIBLE_TO_DRIVER, driver_id=user.id
    )
    return [summary_out(t) for t in trips]


@driver_router.get("/trips/{trip_id}")
async def my_trip(trip_id: uuid.UUID, user: DriverDep, session: DbSession) -> TripOut:
    trip = await dispatch.get_trip(session, trip_id)
    service.ensure_member(trip, user.id)
    return trip_out(trip)


@driver_router.post("/photos")
async def upload_photo(
    user: DriverDep, file: Annotated[UploadFile, File(description="Ảnh chứng từ giao nhận")]
) -> UploadedPhoto:
    key = await service.upload_photo(user.cid, await file.read(), file.content_type or "")
    return UploadedPhoto(key=key)


@driver_router.post("/trips/{trip_id}/items/{item_id}/confirm")
async def confirm_item(
    trip_id: uuid.UUID, item_id: uuid.UUID, body: ConfirmIn, user: DriverDep, session: DbSession
) -> ConfirmationOut:
    """Xác nhận kết quả giao. `accepted=false` kèm `violations` nếu vi phạm quy tắc (vẫn lưu)."""
    trip = await dispatch.get_trip(session, trip_id)
    confirmation = await service.confirm(session, user.cid, trip, item_id, user.id, body)
    await session.commit()
    return service.to_out(confirmation)


@confirmations_router.get("/{trip_id}/confirmations")
async def trip_confirmations(
    trip_id: uuid.UUID, _: OfficeStaffDep, session: DbSession
) -> list[ConfirmationOut]:
    await dispatch.get_trip(session, trip_id)  # 404 nếu không có / thuộc công ty khác
    return [service.to_out(c) for c in await service.list_for_trip(session, trip_id)]
