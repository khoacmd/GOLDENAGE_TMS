"""Thiết bị: admin công ty quản lý PC/máy in; app mobile tự đăng ký, admin duyệt hoặc khóa."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.schemas import PageParams, paginate
from app.modules.audit import service as audit
from app.modules.devices.models import Device, DeviceStatus, DeviceType
from app.modules.devices.schemas import DeviceCreate, DeviceRegister, DeviceUpdate
from app.modules.identity import service as identity
from app.modules.master_data import service as master_data


async def list_devices(
    session: AsyncSession,
    params: PageParams,
    device_type: DeviceType | None = None,
    status: DeviceStatus | None = None,
) -> tuple[list[Device], int]:
    stmt = select(Device)
    if device_type is not None:
        stmt = stmt.where(Device.device_type == device_type)
    if status is not None:
        stmt = stmt.where(Device.status == status)
    if params.q:
        pattern = f"%{params.q.strip()}%"
        columns = [Device.name, Device.identifier, Device.model, Device.address]
        stmt = stmt.where(or_(*(col.ilike(pattern) for col in columns)))
    return await paginate(session, stmt.order_by(Device.device_type, Device.name), params)


async def get_device(session: AsyncSession, device_id: uuid.UUID) -> Device:
    device = await session.get(Device, device_id)
    if device is None:
        raise NotFoundError("Không tìm thấy thiết bị")
    return device


async def find_by_identifier(session: AsyncSession, identifier: str) -> Device | None:
    return await session.scalar(select(Device).where(Device.identifier == identifier))


async def _check_refs(
    session: AsyncSession,
    company_id: uuid.UUID,
    data: DeviceCreate | DeviceUpdate,
    device_id: uuid.UUID | None = None,
) -> None:
    if data.warehouse_id is not None:
        await master_data.get_warehouse(session, data.warehouse_id)
    if data.user_id is not None:
        await identity.get_company_user(session, company_id, data.user_id)
    if data.identifier:
        existing = await session.scalar(
            select(Device.id).where(func.lower(Device.identifier) == data.identifier.lower())
        )
        if existing is not None and existing != device_id:
            raise ConflictError(f"Mã thiết bị '{data.identifier}' đã tồn tại")


async def create_device(
    session: AsyncSession, company_id: uuid.UUID, data: DeviceCreate, actor_id: uuid.UUID
) -> Device:
    await _check_refs(session, company_id, data)
    device = Device(company_id=company_id, **data.model_dump())
    session.add(device)
    await session.flush()
    audit.record(session, company_id, "device", device.id, "create", actor_id, name=device.name)
    return device


async def update_device(
    session: AsyncSession,
    company_id: uuid.UUID,
    device_id: uuid.UUID,
    data: DeviceUpdate,
    actor_id: uuid.UUID,
) -> Device:
    device = await get_device(session, device_id)
    await _check_refs(session, company_id, data, device.id)
    old_status = device.status
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    await session.flush()
    if device.status != old_status:
        audit.record(
            session,
            company_id,
            "device",
            device.id,
            "status",
            actor_id,
            old=old_status.value,
            new=device.status.value,
        )
    return device


async def delete_device(
    session: AsyncSession, company_id: uuid.UUID, device_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    device = await get_device(session, device_id)
    audit.record(session, company_id, "device", device.id, "delete", actor_id, name=device.name)
    await session.delete(device)
    await session.flush()


async def register_mobile(
    session: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    username: str,
    data: DeviceRegister,
    *,
    require_approval: bool,
) -> Device:
    """Upsert điện thoại theo mã cài đặt; thiết bị mới chờ duyệt nếu công ty yêu cầu."""
    device = await find_by_identifier(session, data.identifier)
    info = data.model_dump(exclude={"identifier"})
    if device is None:
        device = Device(
            company_id=company_id,
            device_type=DeviceType.MOBILE,
            identifier=data.identifier,
            name=f"{data.model or 'Điện thoại'} ({username})",
            status=DeviceStatus.PENDING if require_approval else DeviceStatus.ACTIVE,
        )
        session.add(device)
        await session.flush()
        audit.record(session, company_id, "device", device.id, "register", user_id)
    for field, value in info.items():
        if value is not None:
            setattr(device, field, value)
    device.user_id = user_id
    device.last_seen_at = datetime.now(UTC)
    await session.flush()
    return device


async def check_mobile(
    session: AsyncSession, identifier: str | None, *, require_approval: bool
) -> tuple[Device | None, str | None]:
    """Thiết bị dùng để xác nhận giao → (thiết bị, vi phạm nếu có)."""
    device = await find_by_identifier(session, identifier) if identifier else None
    if device is None:
        return None, "Thiết bị chưa được đăng ký" if require_approval else None
    device.last_seen_at = datetime.now(UTC)
    if device.status == DeviceStatus.BLOCKED:
        return device, "Thiết bị đã bị khóa"
    if device.status == DeviceStatus.PENDING:
        return device, "Thiết bị đang chờ admin công ty duyệt"
    return device, None
