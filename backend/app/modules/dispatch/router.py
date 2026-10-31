import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import CurrentUser, OfficeStaffDep, require_roles
from app.core.db import DbSession
from app.core.errors import PermissionDeniedError
from app.modules.audit import service as audit
from app.modules.costing import service as costing
from app.modules.dispatch import service
from app.modules.dispatch.models import Trip, TripOrderStatus
from app.modules.dispatch.schemas import (
    AuditOut,
    AvailablePartOut,
    CancelIn,
    ItemUpdateIn,
    PickingLineOut,
    PickingListOut,
    TripIn,
    TripItemOut,
    TripOut,
    TripRouteOut,
    TripSummaryOut,
)
from app.modules.identity.models import CompanyRole
from app.modules.routing import service as routing

router = APIRouter(prefix="/trips", tags=["dispatch"])

ManagerDep = Annotated[CurrentUser, Depends(require_roles(CompanyRole.MANAGER))]
KeeperDep = Annotated[CurrentUser, Depends(require_roles(CompanyRole.WAREHOUSE_KEEPER))]
ManagerOrDriverDep = Annotated[
    CurrentUser, Depends(require_roles(CompanyRole.MANAGER, CompanyRole.DRIVER))
]


def summary_out(trip: Trip) -> TripSummaryOut:
    out = TripSummaryOut.model_validate(trip)
    out.stop_count = len(trip.stops)
    out.item_counts = service.item_counts(trip)
    return out


def trip_out(trip: Trip, warnings: list[str] | None = None) -> TripOut:
    out = TripOut.model_validate(trip)
    out.stop_count = len(trip.stops)
    out.item_counts = service.item_counts(trip)
    out.warnings = warnings or []
    for stop_out, stop in zip(out.stops, trip.stops, strict=True):
        point = stop.delivery_point
        if point is not None:
            stop_out.customer_code = point.customer.code
            stop_out.customer_name = point.customer.name
            stop_out.address = point.address
            stop_out.latitude = point.latitude
            stop_out.longitude = point.longitude
            stop_out.name = stop_out.name or point.name
    return out


async def _reload(session: DbSession, trip_id: uuid.UUID) -> Trip:
    """Nạp lại lệnh sau khi đổi xe/kho/lái xe/điểm dừng để quan hệ được load đầy đủ."""
    session.expunge_all()
    return await service.get_trip(session, trip_id)


@router.get("/available-parts")
async def available_parts(
    _: OfficeStaffDep, session: DbSession, plan_date: Annotated[date, Query()]
) -> list[AvailablePartOut]:
    """Phần đơn chờ xếp lệnh, ngày giao yêu cầu đến hết `plan_date`."""
    parts = await service.available_parts(session, plan_date)
    return [AvailablePartOut.model_validate(p) for p in parts]


@router.get("")
async def list_trips(
    _: OfficeStaffDep,
    session: DbSession,
    plan_date: Annotated[date | None, Query()] = None,
    order_status: Annotated[list[TripOrderStatus] | None, Query()] = None,
) -> list[TripSummaryOut]:
    trips = await service.list_trips(session, plan_date=plan_date, statuses=order_status)
    return [summary_out(t) for t in trips]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_trip(body: TripIn, user: ManagerDep, session: DbSession) -> TripOut:
    trip, warnings = await service.save_trip(session, user.cid, body, user.id)
    await session.commit()
    return trip_out(await _reload(session, trip.id), warnings)


@router.get("/{trip_id}")
async def get_trip(trip_id: uuid.UUID, _: OfficeStaffDep, session: DbSession) -> TripOut:
    return trip_out(await service.get_trip(session, trip_id))


@router.put("/{trip_id}")
async def update_trip(
    trip_id: uuid.UUID, body: TripIn, user: ManagerDep, session: DbSession
) -> TripOut:
    trip = await service.get_trip(session, trip_id)
    trip, warnings = await service.save_trip(session, user.cid, body, user.id, trip)
    await session.commit()
    return trip_out(await _reload(session, trip.id), warnings)


@router.post("/{trip_id}/approve")
async def approve_trip(trip_id: uuid.UUID, user: ManagerDep, session: DbSession) -> TripOut:
    trip = await service.approve(session, await service.get_trip(session, trip_id), user.id)
    await session.commit()
    return trip_out(trip)


@router.post("/{trip_id}/cancel")
async def cancel_trip(
    trip_id: uuid.UUID, body: CancelIn, user: ManagerDep, session: DbSession
) -> TripOut:
    trip = await service.get_trip(session, trip_id)
    trip = await service.cancel(session, trip, body.reason, user.id)
    await session.commit()
    return trip_out(trip)


@router.post("/{trip_id}/prepare")
async def prepare_trip(trip_id: uuid.UUID, user: KeeperDep, session: DbSession) -> TripOut:
    trip = await service.prepare(session, await service.get_trip(session, trip_id), user.id)
    await session.commit()
    return trip_out(trip)


@router.post("/{trip_id}/pick")
async def pick_trip(trip_id: uuid.UUID, user: KeeperDep, session: DbSession) -> TripOut:
    trip = await service.pick(session, await service.get_trip(session, trip_id), user.id)
    await session.commit()
    return trip_out(trip)


@router.post("/{trip_id}/dispatch")
async def dispatch_trip(
    trip_id: uuid.UUID, user: ManagerOrDriverDep, session: DbSession
) -> TripOut:
    trip = await service.get_trip(session, trip_id)
    if not user.has_any_role(CompanyRole.MANAGER) and user.id not in (
        trip.driver_id,
        trip.assistant_id,
    ):
        raise PermissionDeniedError("Chỉ lái xe/phụ xe của chuyến được xác nhận xuất phát")
    trip = await service.dispatch(session, trip, user.id)
    await session.commit()
    return trip_out(trip)


@router.patch("/{trip_id}/items/{item_id}")
async def update_item(
    trip_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ItemUpdateIn,
    user: ManagerDep,
    session: DbSession,
) -> TripItemOut:
    """Quản lý cập nhật thủ công trạng thái giao (kể cả hủy item chưa giao)."""
    trip = await service.get_trip(session, trip_id)
    item = await service.update_item(
        session,
        trip,
        item_id,
        body.status,
        reason=body.reason,
        delivered_at=body.delivered_at,
        actor_id=user.id,
        manual=True,
    )
    await session.commit()
    return TripItemOut.model_validate(item)


@router.post("/{trip_id}/close")
async def close_trip(trip_id: uuid.UUID, user: ManagerDep, session: DbSession) -> TripOut:
    trip = await service.close(session, await service.get_trip(session, trip_id), user.id)
    # Chưa ghi nhận chi phí thì tính theo km kế hoạch/ước lượng để báo cáo luôn đủ số liệu.
    await costing.ensure(session, trip, user.id)
    await session.commit()
    return trip_out(trip)


@router.get("/{trip_id}/route")
async def trip_route(trip_id: uuid.UUID, _: OfficeStaffDep, session: DbSession) -> TripRouteOut:
    """Tuyến theo đường thực tế (OSRM); chưa có OSRM thì trả đường thẳng nối các điểm."""
    trip = await service.get_trip(session, trip_id)
    path = service.trip_path(trip)
    line = await routing.geometry(path, service.vehicle_profile(trip.vehicle))
    if line is None:
        return TripRouteOut(road=False, coordinates=[(lng, lat) for lat, lng in path])
    return TripRouteOut(road=True, coordinates=line)


@router.get("/{trip_id}/picking-list")
async def picking_list(trip_id: uuid.UUID, _: OfficeStaffDep, session: DbSession) -> PickingListOut:
    trip = await service.get_trip(session, trip_id)
    lines, adhoc = service.picking_lines(trip)
    return PickingListOut(
        trip=summary_out(trip),
        lines=[PickingLineOut.model_validate(line) for line in lines],
        adhoc_items=adhoc,
    )


@router.get("/{trip_id}/history")
async def trip_history(trip_id: uuid.UUID, _: OfficeStaffDep, session: DbSession) -> list[AuditOut]:
    await service.get_trip(session, trip_id)  # 404 nếu không có / thuộc công ty khác
    return [AuditOut.model_validate(a) for a in await audit.history(session, "trip", trip_id)]
