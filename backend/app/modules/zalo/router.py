import uuid

from fastapi import APIRouter, status

from app.core.auth import CompanyAdminDep
from app.core.db import DbSession
from app.modules.identity import service as identity_service
from app.modules.master_data import service as master_data
from app.modules.zalo import service
from app.modules.zalo.schemas import ActivationCodeOut, ZaloTarget

router = APIRouter(tags=["zalo"])


# --- Mã kích hoạt Zalo Mini App (admin công ty) ------------------------------------------


@router.post(
    "/customers/{customer_id}/contacts/{contact_id}/activation-code",
    status_code=status.HTTP_201_CREATED,
)
async def issue_contact_code(
    customer_id: uuid.UUID, contact_id: uuid.UUID, admin: CompanyAdminDep, session: DbSession
) -> ActivationCodeOut:
    target = await service.contact_target(session, customer_id, contact_id)
    out = await service.issue_code(session, admin.cid, target, admin.id)
    await session.commit()
    return out


@router.delete(
    "/customers/{customer_id}/contacts/{contact_id}/zalo", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_contact_zalo(
    customer_id: uuid.UUID, contact_id: uuid.UUID, admin: CompanyAdminDep, session: DbSession
) -> None:
    contact = await master_data.get_contact(session, customer_id, contact_id)
    await service.revoke(session, admin.cid, ZaloTarget(contact_id=contact.id), admin.id)
    await session.commit()


@router.post("/users/{user_id}/activation-code", status_code=status.HTTP_201_CREATED)
async def issue_driver_code(
    user_id: uuid.UUID, admin: CompanyAdminDep, session: DbSession
) -> ActivationCodeOut:
    target = await service.driver_target(session, admin.cid, user_id)
    out = await service.issue_code(session, admin.cid, target, admin.id)
    await session.commit()
    return out


@router.delete("/users/{user_id}/zalo", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_driver_zalo(
    user_id: uuid.UUID, admin: CompanyAdminDep, session: DbSession
) -> None:
    user, _ = await identity_service.get_company_user(session, admin.cid, user_id)
    await service.revoke(session, admin.cid, ZaloTarget(user_id=user.id), admin.id)
    await session.commit()
