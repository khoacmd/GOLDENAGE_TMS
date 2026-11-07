"""Danh mục cầu vượt sông (theo công ty) và dữ liệu sông dùng chung cho bộ lập kế hoạch."""

import json
import uuid
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.audit import service as audit
from app.modules.rivers import geometry
from app.modules.rivers.models import RiverBridge
from app.modules.rivers.schemas import BridgeIn, RiverOut

DATA_DIR = Path(__file__).parent / "data"
ENTITY = "river_bridge"


@cache
def _data() -> tuple[dict[str, RiverOut], list[dict[str, Any]]]:
    rivers: dict[str, RiverOut] = {}
    bridges: list[dict[str, Any]] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        content = json.loads(path.read_text(encoding="utf-8"))
        for river in content["rivers"]:
            rivers[river["code"]] = RiverOut.model_validate(river)
        bridges += content.get("bridges", [])
    return rivers, bridges


def rivers() -> list[RiverOut]:
    return list(_data()[0].values())


def _check_river(code: str) -> None:
    if code not in _data()[0]:
        raise AppError(f"Không có sông mã '{code}'", code="invalid_river")


async def list_bridges(session: AsyncSession) -> list[RiverBridge]:
    stmt = select(RiverBridge).order_by(RiverBridge.river_code, RiverBridge.code)
    return list(await session.scalars(stmt))


async def _get(session: AsyncSession, bridge_id: uuid.UUID) -> RiverBridge:
    bridge = await session.get(RiverBridge, bridge_id)
    if bridge is None:
        raise NotFoundError("Không tìm thấy cầu")
    return bridge


async def _check_code(session: AsyncSession, code: str, exclude: uuid.UUID | None = None) -> None:
    stmt = select(RiverBridge.id).where(func.lower(RiverBridge.code) == code.lower())
    if exclude is not None:
        stmt = stmt.where(RiverBridge.id != exclude)
    if await session.scalar(stmt) is not None:
        raise ConflictError(f"Mã cầu '{code}' đã tồn tại")


async def create_bridge(
    session: AsyncSession, company_id: uuid.UUID, data: BridgeIn, actor_id: uuid.UUID
) -> RiverBridge:
    _check_river(data.river_code)
    await _check_code(session, data.code)
    bridge = RiverBridge(company_id=company_id, **data.model_dump())
    session.add(bridge)
    await session.flush()
    audit.record(session, company_id, ENTITY, bridge.id, "created", actor_id, code=data.code)
    return bridge


async def update_bridge(
    session: AsyncSession, bridge_id: uuid.UUID, data: BridgeIn, actor_id: uuid.UUID
) -> RiverBridge:
    bridge = await _get(session, bridge_id)
    _check_river(data.river_code)
    await _check_code(session, data.code, exclude=bridge.id)
    for key, value in data.model_dump().items():
        setattr(bridge, key, value)
    await session.flush()
    audit.record(
        session,
        bridge.company_id,
        ENTITY,
        bridge.id,
        "updated",
        actor_id,
        code=data.code,
        motorbike_penalty=data.motorbike_penalty,
        is_active=data.is_active,
    )
    return bridge


async def delete_bridge(session: AsyncSession, bridge_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    bridge = await _get(session, bridge_id)
    audit.record(
        session, bridge.company_id, ENTITY, bridge.id, "deleted", actor_id, code=bridge.code
    )
    await session.delete(bridge)
    await session.flush()


async def load_defaults(session: AsyncSession, company_id: uuid.UUID, actor_id: uuid.UUID) -> int:
    """Thêm các cầu mẫu (trong file dữ liệu) chưa có mã trong công ty; cầu đã có giữ nguyên."""
    existing = {c.lower() for c in await session.scalars(select(RiverBridge.code))}
    created = 0
    for item in _data()[1]:
        if item["code"].lower() in existing:
            continue
        await create_bridge(session, company_id, BridgeIn.model_validate(item), actor_id)
        created += 1
    return created


async def planning_rivers(session: AsyncSession) -> list[geometry.River]:
    """Sông có ít nhất 1 cầu đang dùng; sông không có cầu thì không xét bờ."""
    stmt = select(RiverBridge).where(RiverBridge.is_active.is_(True))
    by_river: dict[str, list[geometry.Bridge]] = {}
    for bridge in await session.scalars(stmt):
        location = (float(bridge.latitude), float(bridge.longitude))
        by_river.setdefault(bridge.river_code, []).append(
            geometry.Bridge(bridge.name, location, bridge.motorbike_penalty)
        )
    known = _data()[0]
    return [
        geometry.River(known[code].name, known[code].path, tuple(items))
        for code, items in sorted(by_river.items())
        if code in known
    ]
