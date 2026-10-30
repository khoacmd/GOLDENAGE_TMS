import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import CurrentUser, OfficeStaffDep, require_roles
from app.core.db import DbSession
from app.modules.costing import service
from app.modules.costing.models import TripCost
from app.modules.costing.schemas import AllocationOut, TripCostIn, TripCostOut
from app.modules.dispatch import service as dispatch
from app.modules.dispatch.models import Trip
from app.modules.identity.models import CompanyRole

router = APIRouter(prefix="/trips", tags=["costing"])

ManagerDep = Annotated[CurrentUser, Depends(require_roles(CompanyRole.MANAGER))]


def cost_out(cost: TripCost, trip: Trip) -> TripCostOut:
    items = {item.id: item for _, item in service.charged_items(trip)}
    fields = {f: getattr(cost, f) for f in TripCostOut.model_fields if f != "allocations"}
    out = TripCostOut(**fields)
    for a in cost.allocations:
        item = items.get(a.trip_item_id)
        if item is None or item.order_part is None:
            continue
        order = item.order_part.order
        out.allocations.append(
            AllocationOut(
                trip_item_id=a.trip_item_id,
                order_id=a.order_id,
                external_ref=order.external_ref,
                customer_code=order.customer.code,
                customer_name=order.customer.name,
                weight_kg=item.weight_kg,
                value=item.value,
                basis=a.basis,
                amount=a.amount,
            )
        )
    return out


@router.get("/{trip_id}/cost")
async def get_cost(trip_id: uuid.UUID, _: OfficeStaffDep, session: DbSession) -> TripCostOut | None:
    """`null` nếu chuyến chưa ghi nhận chi phí."""
    trip = await dispatch.get_trip(session, trip_id)
    cost = await service.get_cost(session, trip_id)
    return cost_out(cost, trip) if cost else None


@router.put("/{trip_id}/cost")
async def record_cost(
    trip_id: uuid.UUID, body: TripCostIn, user: ManagerDep, session: DbSession
) -> TripCostOut:
    """Quản lý ghi nhận km thực tế + chi phí phát sinh; hệ thống tính và phân bổ về đơn."""
    trip = await dispatch.get_trip(session, trip_id)
    cost = await service.record(session, trip, body, user.id)
    await session.commit()
    return cost_out(cost, trip)
