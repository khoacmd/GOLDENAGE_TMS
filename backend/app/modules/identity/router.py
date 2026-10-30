import uuid

from fastapi import APIRouter, status

from app.core.auth import CompanyAdminDep, CurrentUserDep
from app.core.db import DbSession
from app.core.errors import AppError, NotFoundError
from app.core.security import hash_password
from app.modules.identity import service
from app.modules.identity.models import CompanyRole, User
from app.modules.identity.schemas import (
    CompanyUserCreate,
    CompanyUserOut,
    CompanyUserUpdate,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RolesUpdate,
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


users_router = APIRouter(prefix="/users", tags=["users"])


def _user_out(user: User, roles: list[CompanyRole]) -> CompanyUserOut:
    return CompanyUserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        roles=roles,
    )


@users_router.get("")
async def list_users(admin: CompanyAdminDep, session: DbSession) -> list[CompanyUserOut]:
    return [_user_out(u, r) for u, r in await service.list_company_users(session, admin.cid)]


@users_router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CompanyUserCreate, admin: CompanyAdminDep, session: DbSession
) -> CompanyUserOut:
    user = await service.create_user(
        session,
        username=body.username,
        password=body.password,
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        home_company_id=admin.cid,
    )
    await service.set_roles(session, admin.cid, user.id, set(body.roles), actor_id=admin.id)
    await session.commit()
    return _user_out(user, sorted(set(body.roles)))


@users_router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: CompanyUserUpdate, admin: CompanyAdminDep, session: DbSession
) -> CompanyUserOut:
    user, roles = await service.get_company_user(session, admin.cid, user_id)
    changes = body.model_dump(exclude_unset=True)
    if "password" in changes or "is_active" in changes:
        service.ensure_home_company(user, admin.cid)
        if user.id == admin.id and changes.get("is_active") is False:
            raise AppError("Không thể tự khóa tài khoản của chính mình", code="self_lockout")
    if (password := changes.pop("password", None)) is not None:
        user.password_hash = hash_password(password)
    for field, value in changes.items():
        setattr(user, field, value)
    await session.commit()
    return _user_out(user, roles)


@users_router.put("/{user_id}/roles")
async def set_user_roles(
    user_id: uuid.UUID, body: RolesUpdate, admin: CompanyAdminDep, session: DbSession
) -> CompanyUserOut:
    user, _ = await service.get_company_user(session, admin.cid, user_id)
    await service.set_roles(session, admin.cid, user.id, set(body.roles), actor_id=admin.id)
    await session.commit()
    return _user_out(user, sorted(set(body.roles)))
