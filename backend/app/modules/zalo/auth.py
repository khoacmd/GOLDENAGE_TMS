"""Đăng nhập Zalo Mini App: Zalo ID đã liên kết → phiên lái xe (token nhân viên, via=zalo)
hoặc phiên khách hàng (token customer_*, chỉ dùng cho /customer/*)."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import revocation
from app.core.db import DbSession, set_tenant_context
from app.core.errors import AuthenticationError, NotFoundError
from app.core.security import create_token, decode_token
from app.modules.identity import service as identity_service
from app.modules.identity.models import CompanyRole
from app.modules.master_data.models import Customer, CustomerContact, DeliveryPoint
from app.modules.tenancy.models import Company
from app.modules.zalo import service
from app.modules.zalo.client import ZaloProfile
from app.modules.zalo.models import ZaloLink
from app.modules.zalo.schemas import (
    AccountKind,
    CompanyRef,
    CustomerScope,
    ZaloAccount,
    ZaloLoginOut,
    ZaloLoginStatus,
)


@dataclass(frozen=True)
class _Account:
    account: ZaloAccount
    user_id: uuid.UUID | None = None  # tài khoản lái xe


async def _active_company(session: AsyncSession, company_id: uuid.UUID) -> Company | None:
    company = await session.get(Company, company_id)
    return company if company is not None and company.is_active else None


async def customer_scopes(
    session: AsyncSession, company_id: uuid.UUID, zalo_user_id: str
) -> list[CustomerScope]:
    """Liên hệ đang hiệu lực của Zalo tại công ty (liên hệ, khách hàng, điểm giao còn hoạt động)."""
    await set_tenant_context(session, company_id=company_id, user_id=None)
    rows = await session.execute(
        select(CustomerContact, Customer, DeliveryPoint)
        .join(ZaloLink, ZaloLink.contact_id == CustomerContact.id)
        .join(Customer, Customer.id == CustomerContact.customer_id)
        .outerjoin(DeliveryPoint, DeliveryPoint.id == CustomerContact.delivery_point_id)
        .where(
            ZaloLink.zalo_user_id == zalo_user_id,
            ZaloLink.revoked_at.is_(None),
            CustomerContact.is_active.is_(True),
            Customer.is_active.is_(True),
        )
        .order_by(Customer.code)
    )
    return [
        CustomerScope(
            customer_id=customer.id,
            customer_code=customer.code,
            customer_name=customer.name,
            delivery_point_id=point.id if point else None,
            delivery_point_code=point.code if point else None,
            delivery_point_name=point.name if point else None,
        )
        for contact, customer, point in rows
        if point is None or point.is_active
    ]


async def _driver_ok(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Như đăng nhập PIN: chỉ tài khoản đang hoạt động và chỉ có vai trò lái xe."""
    await set_tenant_context(session, company_id=company_id, user_id=None)
    try:
        user, roles = await identity_service.get_company_user(session, company_id, user_id)
    except NotFoundError:
        return False
    return user.is_active and set(roles) == {CompanyRole.DRIVER}


async def _accounts(session: AsyncSession, zalo_user_id: str) -> list[_Account]:
    # Chưa biết công ty: policy zalo_link_lookup cho đọc đúng liên kết của Zalo ID này.
    await set_tenant_context(session, company_id=None, user_id=None)
    await session.execute(
        text("SELECT set_config('app.zalo_user_id', :z, true)"), {"z": zalo_user_id}
    )
    links = list(
        await session.scalars(
            select(ZaloLink).where(
                ZaloLink.zalo_user_id == zalo_user_id, ZaloLink.revoked_at.is_(None)
            )
        )
    )
    accounts: dict[tuple[uuid.UUID, AccountKind], _Account] = {}
    for link in links:
        kind = AccountKind.CUSTOMER if link.contact_id else AccountKind.DRIVER
        if (link.company_id, kind) in accounts:
            continue
        company = await _active_company(session, link.company_id)
        if company is None:
            continue
        ref = CompanyRef(id=company.id, code=company.code, name=company.name)
        if kind == AccountKind.CUSTOMER:
            if await customer_scopes(session, company.id, zalo_user_id):
                accounts[(company.id, kind)] = _Account(ZaloAccount(kind=kind, company=ref))
        elif link.user_id and await _driver_ok(session, company.id, link.user_id):
            accounts[(company.id, kind)] = _Account(
                ZaloAccount(kind=kind, company=ref), user_id=link.user_id
            )
    return sorted(accounts.values(), key=lambda a: (a.account.company.code, a.account.kind))


def _session_out(profile_name: str | None, chosen: _Account, zalo_user_id: str) -> ZaloLoginOut:
    company_id = chosen.account.company.id
    if chosen.user_id is not None:
        tokens = identity_service.issue_tokens(chosen.user_id, company_id, via="zalo")
        access, refresh = tokens.access_token, tokens.refresh_token
    else:
        access = create_token(zalo_user_id, company_id, "customer_access")
        refresh = create_token(zalo_user_id, company_id, "customer_refresh")
    return ZaloLoginOut(
        status=ZaloLoginStatus.OK,
        zalo_name=profile_name,
        account=chosen.account,
        access_token=access,
        refresh_token=refresh,
    )


async def login(
    session: AsyncSession,
    profile: ZaloProfile,
    company_id: uuid.UUID | None = None,
    kind: AccountKind | None = None,
) -> ZaloLoginOut:
    accounts = await _accounts(session, profile.id)
    if not accounts:
        return ZaloLoginOut(status=ZaloLoginStatus.NOT_LINKED, zalo_name=profile.name)
    matches = [
        a
        for a in accounts
        if (company_id is None or a.account.company.id == company_id)
        and (kind is None or a.account.kind == kind)
    ]
    if not matches:
        raise AuthenticationError("Zalo chưa liên kết với tài khoản đã chọn")
    if len(matches) > 1:
        return ZaloLoginOut(
            status=ZaloLoginStatus.CHOOSE_ACCOUNT,
            zalo_name=profile.name,
            accounts=[a.account for a in matches],
        )
    return _session_out(profile.name, matches[0], profile.id)


async def activate(
    session: AsyncSession, profile: ZaloProfile, code: str, ip: str | None
) -> ZaloLoginOut:
    """Nhập mã kích hoạt rồi đăng nhập luôn vào tài khoản vừa liên kết."""
    link = await service.redeem(
        session, code, zalo_user_id=profile.id, display_name=profile.name, ip=ip
    )
    kind = AccountKind.CUSTOMER if link.contact_id else AccountKind.DRIVER
    return await login(session, profile, link.company_id, kind)


async def refresh(session: AsyncSession, refresh_token: str) -> ZaloLoginOut:
    """Làm mới phiên Zalo (khách hàng hoặc lái xe), kiểm tra lại liên kết còn hiệu lực."""
    try:
        payload = decode_token(refresh_token, "customer_refresh")
        kind = AccountKind.CUSTOMER
    except AuthenticationError:
        payload = decode_token(refresh_token, "refresh")
        if payload.via != "zalo":
            raise AuthenticationError("Không phải phiên Zalo Mini App") from None
        kind = AccountKind.DRIVER
    if await revocation.is_revoked(payload.jti) or payload.company_id is None:
        raise AuthenticationError("Phiên đăng nhập đã kết thúc")
    zalo_user_id = (
        payload.subject
        if kind == AccountKind.CUSTOMER
        else await _driver_zalo_id(session, payload.company_id, payload.user_id)
    )
    if zalo_user_id is None:
        raise AuthenticationError("Liên kết Zalo đã bị thu hồi")
    accounts = await _accounts(session, zalo_user_id)
    chosen = next(
        (
            a
            for a in accounts
            if a.account.company.id == payload.company_id and a.account.kind == kind
        ),
        None,
    )
    if chosen is None:
        raise AuthenticationError("Liên kết Zalo đã bị thu hồi")
    return _session_out(None, chosen, zalo_user_id)


async def _driver_zalo_id(
    session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID
) -> str | None:
    await set_tenant_context(session, company_id=company_id, user_id=None)
    return await session.scalar(
        select(ZaloLink.zalo_user_id).where(
            ZaloLink.user_id == user_id, ZaloLink.revoked_at.is_(None)
        )
    )


# --- Phiên khách hàng ---------------------------------------------------------------------


@dataclass(frozen=True)
class CurrentCustomer:
    zalo_user_id: str
    company: CompanyRef
    scopes: list[CustomerScope]


_bearer = HTTPBearer(auto_error=False)


async def get_current_customer(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentCustomer:
    if credentials is None:
        raise AuthenticationError("Thiếu access token")
    payload = decode_token(credentials.credentials, "customer_access")
    if await revocation.is_revoked(payload.jti) or payload.company_id is None:
        raise AuthenticationError("Phiên đăng nhập đã kết thúc")
    company = await _active_company(session, payload.company_id)
    if company is None:
        raise AuthenticationError("Công ty không tồn tại hoặc đã bị đóng")
    scopes = await customer_scopes(session, company.id, payload.subject)
    if not scopes:
        raise AuthenticationError("Liên kết Zalo đã bị thu hồi")
    return CurrentCustomer(
        zalo_user_id=payload.subject,
        company=CompanyRef(id=company.id, code=company.code, name=company.name),
        scopes=scopes,
    )


CurrentCustomerDep = Annotated[CurrentCustomer, Depends(get_current_customer)]
