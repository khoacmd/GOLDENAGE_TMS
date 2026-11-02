import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.core.auth import CompanyAdminDep
from app.core.db import DbSession
from app.modules.identity import service as identity_service
from app.modules.master_data import service as master_data
from app.modules.zalo import auth as zalo_auth
from app.modules.zalo import client, portal, service
from app.modules.zalo.auth import CurrentCustomerDep
from app.modules.zalo.schemas import (
    ActivationCodeOut,
    CustomerMe,
    CustomerOrderDetail,
    CustomerOrderList,
    ZaloActivateRequest,
    ZaloLoginOut,
    ZaloLoginRequest,
    ZaloRefreshRequest,
    ZaloTarget,
)

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


# --- Đăng nhập Zalo Mini App (công khai, xác thực bằng token Zalo) ------------------------


@router.post("/auth/zalo/login")
async def zalo_login(body: ZaloLoginRequest, session: DbSession) -> ZaloLoginOut:
    """Zalo đã liên kết → token; nhiều tài khoản → chọn; chưa liên kết → nhập mã kích hoạt."""
    profile = await client.fetch_profile(body.access_token)
    return await zalo_auth.login(session, profile, body.company_id, body.kind)


@router.post("/auth/zalo/activate")
async def zalo_activate(
    body: ZaloActivateRequest, request: Request, session: DbSession
) -> ZaloLoginOut:
    profile = await client.fetch_profile(body.access_token)
    ip = request.client.host if request.client else None
    out = await zalo_auth.activate(session, profile, body.code, ip)
    await session.commit()
    return out


@router.post("/auth/zalo/refresh")
async def zalo_refresh(body: ZaloRefreshRequest, session: DbSession) -> ZaloLoginOut:
    return await zalo_auth.refresh(session, body.refresh_token)


# --- Khách hàng (Zalo Mini App) -----------------------------------------------------------


@router.get("/customer/me")
async def customer_me(customer: CurrentCustomerDep) -> CustomerMe:
    return CustomerMe(
        zalo_user_id=customer.zalo_user_id, company=customer.company, scopes=customer.scopes
    )


@router.get("/customer/orders")
async def customer_orders(
    customer: CurrentCustomerDep,
    session: DbSession,
    date: Annotated[date | None, Query(description="Ngày giao, mặc định: hôm nay")] = None,
) -> CustomerOrderList:
    """Đơn của khách theo ngày giao (ngày yêu cầu hoặc ngày của chuyến giao)."""
    return await portal.list_orders(session, customer, date)


@router.get("/customer/orders/{order_id}")
async def customer_order(
    order_id: uuid.UUID, customer: CurrentCustomerDep, session: DbSession
) -> CustomerOrderDetail:
    """Chi tiết đơn: mặt hàng, số lượng, các lượt giao (giờ giao, tài xế, ảnh chứng từ)."""
    return await portal.get_order(session, customer, order_id)
