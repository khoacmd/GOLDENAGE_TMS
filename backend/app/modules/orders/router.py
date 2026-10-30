import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.auth import ManagerOrAdminDep, OfficeStaffDep
from app.core.db import DbSession
from app.core.schemas import Page, PageParams, page_params
from app.modules.orders import service
from app.modules.orders.models import OrderStatus
from app.modules.orders.schemas import OrderDetailOut, OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
async def list_orders(
    _: OfficeStaffDep,
    session: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    requested_from: Annotated[date | None, Query()] = None,
    requested_to: Annotated[date | None, Query()] = None,
    status: Annotated[OrderStatus | None, Query()] = None,
) -> Page[OrderOut]:
    items, total = await service.list_orders(
        session, params, requested_from=requested_from, requested_to=requested_to, status=status
    )
    return Page(items=[OrderOut.model_validate(o) for o in items], total=total)


@router.get("/{order_id}")
async def get_order(order_id: uuid.UUID, _: OfficeStaffDep, session: DbSession) -> OrderDetailOut:
    return OrderDetailOut.model_validate(await service.get_order(session, order_id))


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: uuid.UUID, _: ManagerOrAdminDep, session: DbSession
) -> OrderDetailOut:
    order = await service.cancel_order(session, order_id)
    await session.commit()
    return OrderDetailOut.model_validate(order)
