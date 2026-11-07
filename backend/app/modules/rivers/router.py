import uuid

from fastapi import APIRouter, status

from app.core.auth import CompanyAdminDep, OfficeStaffDep
from app.core.db import DbSession
from app.modules.rivers import service
from app.modules.rivers.schemas import BridgeIn, BridgeOut, LoadDefaultsOut, RiverOut

router = APIRouter(tags=["rivers"])


@router.get("/rivers")
async def list_rivers(_: OfficeStaffDep) -> list[RiverOut]:
    """Sông dùng để xác định bờ của điểm giao/kho (dữ liệu dùng chung)."""
    return service.rivers()


@router.get("/river-bridges")
async def list_bridges(_: OfficeStaffDep, session: DbSession) -> list[BridgeOut]:
    return [BridgeOut.model_validate(b) for b in await service.list_bridges(session)]


@router.post("/river-bridges", status_code=status.HTTP_201_CREATED)
async def create_bridge(body: BridgeIn, user: CompanyAdminDep, session: DbSession) -> BridgeOut:
    bridge = await service.create_bridge(session, user.cid, body, user.id)
    await session.commit()
    return BridgeOut.model_validate(bridge)


@router.post("/river-bridges/load-defaults")
async def load_defaults(user: CompanyAdminDep, session: DbSession) -> LoadDefaultsOut:
    """Thêm các cầu mẫu chưa có (Hà Nội: cầu qua sông Hồng)."""
    created = await service.load_defaults(session, user.cid, user.id)
    await session.commit()
    return LoadDefaultsOut(created=created)


@router.put("/river-bridges/{bridge_id}")
async def update_bridge(
    bridge_id: uuid.UUID, body: BridgeIn, user: CompanyAdminDep, session: DbSession
) -> BridgeOut:
    bridge = await service.update_bridge(session, bridge_id, body, user.id)
    await session.commit()
    return BridgeOut.model_validate(bridge)


@router.delete("/river-bridges/{bridge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bridge(bridge_id: uuid.UUID, user: CompanyAdminDep, session: DbSession) -> None:
    await service.delete_bridge(session, bridge_id, user.id)
    await session.commit()
