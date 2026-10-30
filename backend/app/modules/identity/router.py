from fastapi import APIRouter

from app.core.auth import CurrentUserDep
from app.core.db import DbSession
from app.core.errors import NotFoundError
from app.modules.identity import service
from app.modules.identity.models import User
from app.modules.identity.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenPair,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, session: DbSession) -> TokenPair:
    tokens = await service.login(session, body.username, body.password, body.company_code)
    await session.commit()
    return tokens


@router.post("/refresh")
async def refresh(body: RefreshRequest, session: DbSession) -> TokenPair:
    return await service.refresh(session, body.refresh_token)


@router.get("/me")
async def me(current: CurrentUserDep, session: DbSession) -> MeResponse:
    user = await session.get(User, current.id)
    if user is None:
        raise NotFoundError("Không tìm thấy tài khoản")
    memberships = await service.list_memberships(session, user.id)
    company = next((m.company for m in memberships if m.company.id == current.company_id), None)
    return MeResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        is_system_admin=user.is_system_admin,
        company=company,
        roles=sorted(current.roles),
        memberships=memberships,
    )
