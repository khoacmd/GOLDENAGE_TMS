import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import revocation
from app.core.db import set_tenant_context
from app.core.errors import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import (
    TokenPayload,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
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


def issue_tokens(user_id: uuid.UUID, company_id: uuid.UUID | None) -> TokenPair:
    return TokenPair(
        access_token=create_token(user_id, company_id, "access"),
        refresh_token=create_token(user_id, company_id, "refresh"),
    )


def set_password(user: User, password: str) -> None:
    """Đặt mật khẩu mới; mọi token cấp trước thời điểm này hết hiệu lực."""
    user.password_hash = hash_password(password)
    user.password_changed_at = datetime.now(UTC)


def token_revoked(user: User, payload: TokenPayload) -> bool:
    """Token cấp trước lần đổi mật khẩu gần nhất (iat tính theo giây)."""
    if user.password_changed_at is None or payload.issued_at is None:
        return False
    return payload.issued_at.timestamp() < int(user.password_changed_at.timestamp())


async def change_password(
    session: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    """Người dùng tự đổi mật khẩu (cần mật khẩu hiện tại)."""
    valid, _ = verify_password(current_password, user.password_hash)
    if not valid:
        raise AppError("Mật khẩu hiện tại không đúng", code="wrong_password")
    if new_password == current_password:
        raise AppError("Mật khẩu mới phải khác mật khẩu hiện tại", code="same_password")
    set_password(user, new_password)
    await session.flush()


async def login(
    session: AsyncSession, username: str, password: str, company_code: str | None
) -> TokenPair:
    user = await get_user_by_username(session, username)
    valid, new_hash = verify_password(password, user.password_hash if user else None)
    if user is None or not valid or not user.is_active:
        raise AuthenticationError("Sai tên đăng nhập hoặc mật khẩu")
    if new_hash:
        user.password_hash = new_hash
    company_id, _ = await _resolve_company(session, user, company_code)
    return issue_tokens(user.id, company_id)


async def login_pin(
    session: AsyncSession, username: str, pin: str, company_code: str | None
) -> TokenPair:
    """Đăng nhập app bằng mã PIN - chỉ cho tài khoản chỉ có vai trò lái xe tại công ty."""
    user = await get_user_by_username(session, username)
    valid, new_hash = verify_password(pin, user.pin_hash if user else None)
    if user is None or not valid or not user.is_active:
        raise AuthenticationError("Sai tên đăng nhập hoặc mã PIN")
    if new_hash:
        user.pin_hash = new_hash
    company_id, roles = await _resolve_company(session, user, company_code)
    if company_id is None or set(roles) != {CompanyRole.DRIVER}:
        raise AuthenticationError(
            "Mã PIN chỉ dùng cho tài khoản lái xe, vui lòng đăng nhập bằng mật khẩu"
        )
    return issue_tokens(user.id, company_id)


async def _resolve_company(
    session: AsyncSession, user: User, company_code: str | None
) -> tuple[uuid.UUID | None, list[CompanyRole]]:
    """Chọn công ty đăng nhập; trả về (company_id, vai trò tại công ty đó)."""
    await set_tenant_context(session, company_id=None, user_id=user.id)
    memberships = await list_memberships(session, user.id)

    if company_code is not None:
        match = next(
            (m for m in memberships if m.company.code.lower() == company_code.lower()), None
        )
        if match is None:
            raise AuthenticationError("Tài khoản không thuộc công ty này")
        return match.company.id, match.roles
    if len(memberships) == 1:
        return memberships[0].company.id, memberships[0].roles
    if not memberships and user.is_system_admin:
        return None, []
    if not memberships:
        raise AuthenticationError("Tài khoản chưa được gán vào công ty nào")
    raise AppError("Tài khoản thuộc nhiều công ty, cần chọn company_code", code="company_required")


async def logout(refresh_token: str, access_token: str | None) -> None:
    """Thu hồi refresh token (và access token đi kèm nếu cùng tài khoản); token sai thì bỏ qua."""
    try:
        refresh_payload = decode_token(refresh_token, "refresh")
    except AuthenticationError:
        return
    payloads = [refresh_payload]
    if access_token:
        try:
            access_payload = decode_token(access_token, "access")
        except AuthenticationError:
            pass
        else:
            if access_payload.user_id == refresh_payload.user_id:
                payloads.append(access_payload)
    for p in payloads:
        if p.jti and p.expires_at:
            await revocation.revoke(p.jti, p.expires_at)


async def refresh(session: AsyncSession, refresh_token: str) -> TokenPair:
    payload = decode_token(refresh_token, "refresh")
    if await revocation.is_revoked(payload.jti):
        raise AuthenticationError("Phiên đăng nhập đã kết thúc")
    await set_tenant_context(session, company_id=payload.company_id, user_id=payload.user_id)
    user = await session.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Tài khoản không tồn tại hoặc đã bị khóa")
    if token_revoked(user, payload):
        raise AuthenticationError("Mật khẩu đã thay đổi, vui lòng đăng nhập lại")
    if payload.company_id is not None:
        memberships = await list_memberships(session, user.id)
        if all(m.company.id != payload.company_id for m in memberships):
            raise AuthenticationError("Tài khoản không còn quyền trong công ty này")
    return issue_tokens(user.id, payload.company_id)


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    full_name: str,
    email: str | None = None,
    phone: str | None = None,
    is_system_admin: bool = False,
    home_company_id: uuid.UUID | None = None,
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
        home_company_id=home_company_id,
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


# --- Quản lý user trong công ty (admin công ty) ---------------------------------------


async def list_company_users(
    session: AsyncSession, company_id: uuid.UUID
) -> list[tuple[User, list[CompanyRole]]]:
    rows = await session.execute(
        select(User, UserRole.role)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.company_id == company_id)
        .order_by(User.username)
    )
    users: dict[uuid.UUID, User] = {}
    roles: defaultdict[uuid.UUID, list[CompanyRole]] = defaultdict(list)
    for user, role in rows:
        users[user.id] = user
        roles[user.id].append(CompanyRole(role))
    return [(user, sorted(roles[uid])) for uid, user in users.items()]


async def get_company_user(
    session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[User, list[CompanyRole]]:
    user = await session.get(User, user_id)
    roles = await session.scalars(
        select(UserRole.role).where(UserRole.company_id == company_id, UserRole.user_id == user_id)
    )
    role_list = sorted(CompanyRole(r) for r in roles)
    if user is None or not role_list:
        raise NotFoundError("Không tìm thấy người dùng trong công ty")
    return user, role_list


async def set_roles(
    session: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: set[CompanyRole],
    *,
    actor_id: uuid.UUID,
) -> None:
    if user_id == actor_id and CompanyRole.COMPANY_ADMIN not in roles:
        raise AppError("Không thể tự bỏ quyền admin công ty của chính mình", code="self_lockout")
    current = {
        CompanyRole(r.role): r
        for r in await session.scalars(
            select(UserRole).where(UserRole.company_id == company_id, UserRole.user_id == user_id)
        )
    }
    for role, row in current.items():
        if role not in roles:
            await session.delete(row)
    for role in roles - set(current):
        session.add(UserRole(company_id=company_id, user_id=user_id, role=role))
    await session.flush()


def ensure_home_company(user: User, company_id: uuid.UUID) -> None:
    if user.home_company_id != company_id:
        raise PermissionDeniedError(
            "Tài khoản thuộc quản lý của công ty khác, không thể đổi mật khẩu/khóa"
        )
