import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import CompanyAdminDep
from app.core.db import DbSession
from app.core.schemas import Page, PageParams, page_params
from app.modules.devices import service
from app.modules.devices.models import DeviceStatus, DeviceType
from app.modules.devices.schemas import DeviceCreate, DeviceOut, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("")
async def list_devices(
    _: CompanyAdminDep,
    session: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    device_type: Annotated[DeviceType | None, Query()] = None,
    device_status: Annotated[DeviceStatus | None, Query(alias="status")] = None,
) -> Page[DeviceOut]:
    items, total = await service.list_devices(session, params, device_type, device_status)
    return Page(items=[DeviceOut.model_validate(d) for d in items], total=total)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_device(body: DeviceCreate, user: CompanyAdminDep, session: DbSession) -> DeviceOut:
    device = await service.create_device(session, user.cid, body, user.id)
    await session.commit()
    return DeviceOut.model_validate(device)


@router.patch("/{device_id}")
async def update_device(
    device_id: uuid.UUID, body: DeviceUpdate, user: CompanyAdminDep, session: DbSession
) -> DeviceOut:
    device = await service.update_device(session, user.cid, device_id, body, user.id)
    await session.commit()
    return DeviceOut.model_validate(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: uuid.UUID, user: CompanyAdminDep, session: DbSession) -> None:
    await service.delete_device(session, user.cid, device_id, user.id)
    await session.commit()
