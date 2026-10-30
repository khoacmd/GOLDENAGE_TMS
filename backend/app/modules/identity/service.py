import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import set_tenant_context
from app.core.errors import AppError, AuthenticationError, ConflictError
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.modules.identity.models import CompanyRole, User, UserRole
from app.modules.identity.schemas import CompanyRef, Membership, TokenPair
from app.modules.tenancy.models import Company


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    return await session.scalar(select(User).where(func.lower(User.username) == username.lower()))


async def list_memberships(session: AsyncSession, user_id: uuid.UUID) -> list[Membership]:
    """Các công ty (đang hoạt động) mà user có vai trò.

    Đọc được xuyên công ty nhờ policy `own_roles` trên user_roles (user luôn thấy vai trò của mình).
    """
    rows = await session.execute(
        select(Company, UserRole.role)
        .join(UserRole, UserRole.company_id == Company.id)
        .where(UserRole.user_id == user_id, Company.is_active.is_(True))
        .order_by(Company.code)
    )
    companies: dict[uuid.UUID, Company] = {}
    roles: defaultdict[uuid.UUID, list[CompanyRole]] = defaultdict(list)
    for company, role in rows:
        companies[company.id] = company
        roles[company.id].append(CompanyRole(role))
    return [
        Membership(company=CompanyRef.model_validate(company), roles=sorted(roles[company_id]))
        for company_id, company in companies.items()
    ]


def _issue_tokens(user_id: uuid.UUID, company_id: uuid.UUID | None) -> TokenPair:
    return TokenPair(
        access_token=create_token(user_id, company_id, "access"),
        refresh_token=create_token(user_id, company_id, "refresh"),
    )


async def login(
    session: AsyncSession, username: str, password: str, company_code: str | None
) -> TokenPair:
    user = await get_user_by_username(session, username)
    valid, new_hash = verify_password(password, user.password_hash if user else None)
    if user is None or not valid or not user.is_active:
        raise AuthenticationError("Sai tên đăng nhập hoặc mật khẩu")
    if new_hash:
        user.password_hash = new_hash

    await set_tenant_context(session, company_id=None, user_id=user.id)
    memberships = await list_memberships(session, user.id)

    company_id: uuid.UUID | None
    if company_code is not None:
        match = next(
            (m for m in memberships if m.company.code.lower() == company_code.lower()), None
        )
        if match is None:
            raise AuthenticationError("Tài khoản không thuộc công ty này")
        company_id = match.company.id
    elif len(memberships) == 1:
        company_id = memberships[0].company.id
    elif not memberships and user.is_system_admin:
        company_id = None
    elif not memberships:
        raise AuthenticationError("Tài khoản chưa được gán vào công ty nào")
    else:
        raise AppError(
            "Tài khoản thuộc nhiều công ty, cần chọn company_code", code="company_required"
        )

    return _issue_tokens(user.id, company_id)


async def refresh(session: AsyncSession, refresh_token: str) -> TokenPair:
    payload = decode_token(refresh_token, "refresh")
    await set_tenant_context(session, company_id=payload.company_id, user_id=payload.user_id)
    user = await session.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Tài khoản không tồn tại hoặc đã bị khóa")
    if payload.company_id is not None:
        memberships = await list_memberships(session, user.id)
        if all(m.company.id != payload.company_id for m in memberships):
            raise AuthenticationError("Tài khoản không còn quyền trong công ty này")
    return _issue_tokens(user.id, payload.company_id)


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    full_name: str,
    email: str | None = None,
    phone: str | None = None,
    is_system_admin: bool = False,
) -> User:
    if await get_user_by_username(session, username) is not None:
        raise ConflictError(f"Tên đăng nhập '{username}' đã tồn tại")
    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
        email=email,
        phone=phone,
        is_system_admin=is_system_admin,
    )
    session.add(user)
    await session.flush()
    return user


async def grant_role(
    session: AsyncSession, *, company_id: uuid.UUID, user_id: uuid.UUID, role: CompanyRole
) -> None:
    """Gán vai trò; session phải đang ở context của `company_id` (RLS kiểm tra WITH CHECK)."""
    exists = await session.scalar(
        select(UserRole.id).where(
            UserRole.company_id == company_id, UserRole.user_id == user_id, UserRole.role == role
        )
    )
    if exists is None:
        session.add(UserRole(company_id=company_id, user_id=user_id, role=role))
        await session.flush()
