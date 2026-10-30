"""Dependency xác thực & phân quyền cho router."""

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.db import DbSession, set_tenant_context
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.modules.identity.models import CompanyRole, User, UserRole
from app.modules.tenancy.models import Company

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    username: str
    is_system_admin: bool
    company_id: uuid.UUID | None
    roles: frozenset[CompanyRole]

    def has_any_role(self, *roles: CompanyRole) -> bool:
        return not self.roles.isdisjoint(roles)

    @property
    def cid(self) -> uuid.UUID:
        """Công ty đang làm việc; chỉ dùng sau `require_roles` (đã bảo đảm có công ty)."""
        if self.company_id is None:
            raise PermissionDeniedError("Cần đăng nhập vào một công ty")
        return self.company_id


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None:
        raise AuthenticationError("Thiếu access token")
    payload = decode_token(credentials.credentials, "access")
    # Đặt context trước mọi truy vấn để RLS lọc theo công ty của token.
    await set_tenant_context(session, company_id=payload.company_id, user_id=payload.user_id)

    user = await session.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Tài khoản không tồn tại hoặc đã bị khóa")

    roles: frozenset[CompanyRole] = frozenset()
    if payload.company_id is not None:
        company = await session.get(Company, payload.company_id)
        if company is None or not company.is_active:
            raise AuthenticationError("Công ty không tồn tại hoặc đã bị đóng")
        result = await session.scalars(
            select(UserRole.role).where(
                UserRole.user_id == user.id, UserRole.company_id == payload.company_id
            )
        )
        roles = frozenset(CompanyRole(r) for r in result)
        if not roles:
            raise AuthenticationError("Tài khoản không còn quyền trong công ty này")

    return CurrentUser(
        id=user.id,
        username=user.username,
        is_system_admin=user.is_system_admin,
        company_id=payload.company_id,
        roles=roles,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def require_system_admin(user: CurrentUserDep) -> CurrentUser:
    if not user.is_system_admin:
        raise PermissionDeniedError("Chỉ admin hệ thống được thực hiện thao tác này")
    return user


def require_roles(
    *roles: CompanyRole,
) -> Callable[[CurrentUser], Coroutine[Any, Any, CurrentUser]]:
    """Yêu cầu user đang làm việc trong một công ty và có ít nhất một vai trò trong `roles`."""

    async def _check(user: CurrentUserDep) -> CurrentUser:
        if user.company_id is None or not user.has_any_role(*roles):
            raise PermissionDeniedError("Không có quyền thực hiện thao tác này")
        return user

    return _check


SystemAdminDep = Annotated[CurrentUser, Depends(require_system_admin)]

CompanyAdminDep = Annotated[CurrentUser, Depends(require_roles(CompanyRole.COMPANY_ADMIN))]
ManagerOrAdminDep = Annotated[
    CurrentUser, Depends(require_roles(CompanyRole.COMPANY_ADMIN, CompanyRole.MANAGER))
]
# Đọc dữ liệu gốc: mọi vai trò văn phòng (không gồm lái xe).
OfficeStaffDep = Annotated[
    CurrentUser,
    Depends(
        require_roles(CompanyRole.COMPANY_ADMIN, CompanyRole.MANAGER, CompanyRole.WAREHOUSE_KEEPER)
    ),
]
