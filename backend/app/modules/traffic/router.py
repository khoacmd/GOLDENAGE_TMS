import uuid
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, status

from app.core.auth import CompanyAdminDep, OfficeStaffDep
from app.core.db import DbSession
from app.modules.tenancy.models import CompanySettings
from app.modules.traffic import service
from app.modules.traffic.schemas import PermitIn, PermitOut, ZoneOut

router = APIRouter(tags=["traffic"])


@router.get("/traffic/zones")
async def list_zones(
    user: OfficeStaffDep, session: DbSession, day: Annotated[date | None, Query()] = None
) -> list[ZoneOut]:
    """Vùng hạn chế đang hiệu lực (mặc định: hôm nay), để hiện trên bản đồ."""
    settings = await session.get(CompanySettings, user.cid)
    today = datetime.now(ZoneInfo(settings.timezone if settings else "UTC")).date()
    return await service.zones(session, day or today)


@router.get("/vehicles/{vehicle_id}/permits")
async def list_permits(
    vehicle_id: uuid.UUID, _: OfficeStaffDep, session: DbSession
) -> list[PermitOut]:
    await service.get_vehicle(session, vehicle_id)
    return [PermitOut.model_validate(p) for p in await service.list_permits(session, vehicle_id)]


@router.post("/vehicles/{vehicle_id}/permits", status_code=status.HTTP_201_CREATED)
async def create_permit(
    vehicle_id: uuid.UUID, body: PermitIn, user: CompanyAdminDep, session: DbSession
) -> PermitOut:
    permit = await service.create_permit(session, user.cid, vehicle_id, body, user.id)
    await session.commit()
    return PermitOut.model_validate(permit)


@router.put("/vehicles/{vehicle_id}/permits/{permit_id}")
async def update_permit(
    vehicle_id: uuid.UUID,
    permit_id: uuid.UUID,
    body: PermitIn,
    user: CompanyAdminDep,
    session: DbSession,
) -> PermitOut:
    permit = await service.update_permit(session, vehicle_id, permit_id, body, user.id)
    await session.commit()
    return PermitOut.model_validate(permit)


@router.delete("/vehicles/{vehicle_id}/permits/{permit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permit(
    vehicle_id: uuid.UUID, permit_id: uuid.UUID, user: CompanyAdminDep, session: DbSession
) -> None:
    await service.delete_permit(session, vehicle_id, permit_id, user.id)
    await session.commit()
