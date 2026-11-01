from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import SessionFactory
from app.core.errors import AppError
from app.modules.zalo import service
from app.modules.zalo.models import ActivationCode
from tests.conftest import auth, create_company, create_user, login


async def _customer_with_contacts(client: AsyncClient, admin: str) -> tuple[str, dict[str, Any]]:
    body = {
        "code": "KH001",
        "name": "Đại lý A",
        "delivery_points": [
            {"code": "DG1", "address": "HN", "latitude": "21", "longitude": "105.8"}
        ],
    }
    customer = (await client.post("/api/v1/customers", headers=auth(admin), json=body)).json()
    url = f"/api/v1/customers/{customer['id']}/contacts"
    contact = (
        await client.post(url, headers=auth(admin), json={"name": "Chủ", "phone": "0912000001"})
    ).json()
    return url, contact


async def _contacts(client: AsyncClient, admin: str, url: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = (await client.get(url, headers=auth(admin))).json()
    return data


async def _redeem(code: str, zalo_user_id: str = "zalo-1", ip: str = "1.2.3.4") -> Any:
    async with SessionFactory() as session:
        link = await service.redeem(
            session, code, zalo_user_id=zalo_user_id, display_name="Anh Chủ", ip=ip
        )
        await session.commit()
        return link


async def test_contact_activation_flow(client: AsyncClient, admin_token: str) -> None:
    url, contact = await _customer_with_contacts(client, admin_token)
    assert contact["zalo"]["status"] == "NOT_INVITED"
    code_url = f"{url}/{contact['id']}/activation-code"

    first = (await client.post(code_url, headers=auth(admin_token))).json()
    assert len(first["code"]) == 9 and first["code"][4] == "-"
    assert first["link"] is None  # chưa cấu hình TMS_ZALO_ACTIVATION_URL
    [listed] = await _contacts(client, admin_token, url)
    assert listed["zalo"]["status"] == "PENDING"

    # Tạo lại mã → mã cũ mất hiệu lực.
    second = (await client.post(code_url, headers=auth(admin_token))).json()
    with pytest.raises(AppError, match="không đúng hoặc đã hết hạn"):
        await _redeem(first["code"])

    # Nhập mã (không phân biệt hoa thường, bỏ dấu gạch) → liên kết; mã chỉ dùng 1 lần.
    link = await _redeem(second["code"].replace("-", "").lower())
    assert str(link.contact_id) == contact["id"]
    [listed] = await _contacts(client, admin_token, url)
    assert listed["zalo"]["status"] == "ACTIVE"
    assert listed["zalo"]["display_name"] == "Anh Chủ"
    with pytest.raises(AppError):
        await _redeem(second["code"], zalo_user_id="zalo-2")

    # Đổi điện thoại: mã mới → Zalo mới thay liên kết cũ.
    third = (await client.post(code_url, headers=auth(admin_token))).json()
    [listed] = await _contacts(client, admin_token, url)
    assert listed["zalo"]["status"] == "ACTIVE" and listed["zalo"]["code_expires_at"]
    await _redeem(third["code"], zalo_user_id="zalo-3")

    # Thu hồi → về chưa mời.
    resp = await client.delete(f"{url}/{contact['id']}/zalo", headers=auth(admin_token))
    assert resp.status_code == 204
    [listed] = await _contacts(client, admin_token, url)
    assert listed["zalo"]["status"] == "NOT_INVITED"


async def test_expired_code_and_inactive_contact(
    client: AsyncClient, admin_token: str, owner_engine: AsyncEngine
) -> None:
    url, contact = await _customer_with_contacts(client, admin_token)
    code_url = f"{url}/{contact['id']}/activation-code"
    code = (await client.post(code_url, headers=auth(admin_token))).json()["code"]
    company_id = (await client.get("/api/v1/auth/me", headers=auth(admin_token))).json()["company"][
        "id"
    ]
    async with owner_engine.begin() as conn:
        # Bảng có FORCE RLS: owner cũng cần context công ty.
        await conn.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": company_id})
        await conn.execute(
            update(ActivationCode).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
    with pytest.raises(AppError):
        await _redeem(code)
    [listed] = await _contacts(client, admin_token, url)
    assert listed["zalo"]["status"] == "NOT_INVITED"

    code = (await client.post(code_url, headers=auth(admin_token))).json()["code"]
    await client.put(
        f"{url}/{contact['id']}",
        headers=auth(admin_token),
        json={"name": "Chủ", "phone": "0912000001", "is_active": False},
    )
    with pytest.raises(AppError, match="ngưng hoạt động"):
        await _redeem(code)
    resp = await client.post(code_url, headers=auth(admin_token))
    assert resp.json()["error"]["code"] == "contact_inactive"


async def test_redeem_throttled(client: AsyncClient, admin_token: str) -> None:
    url, contact = await _customer_with_contacts(client, admin_token)
    code = (
        await client.post(f"{url}/{contact['id']}/activation-code", headers=auth(admin_token))
    ).json()["code"]
    for _ in range(5):
        with pytest.raises(AppError):
            await _redeem("SAIMA123")
    with pytest.raises(AppError, match="quá nhiều lần"):
        await _redeem(code)
    await _redeem(code, zalo_user_id="zalo-khac", ip="5.6.7.8")  # Zalo + IP khác vẫn nhập được


async def test_driver_activation(client: AsyncClient, admin_token: str) -> None:
    driver_id = await create_user(client, admin_token, "laixe1", ["driver"])
    manager_id = await create_user(client, admin_token, "quanly1", ["manager"])
    resp = await client.post(
        f"/api/v1/users/{manager_id}/activation-code", headers=auth(admin_token)
    )
    assert resp.json()["error"]["code"] == "not_driver"

    code = (
        await client.post(f"/api/v1/users/{driver_id}/activation-code", headers=auth(admin_token))
    ).json()["code"]
    users = {
        u["username"]: u
        for u in (await client.get("/api/v1/users", headers=auth(admin_token))).json()
    }
    assert users["laixe1"]["zalo"]["status"] == "PENDING"
    assert users["quanly1"]["zalo"] is None
    link = await _redeem(code)
    assert str(link.user_id) == driver_id
    users = {
        u["username"]: u
        for u in (await client.get("/api/v1/users", headers=auth(admin_token))).json()
    }
    assert users["laixe1"]["zalo"]["status"] == "ACTIVE"
    resp = await client.delete(f"/api/v1/users/{driver_id}/zalo", headers=auth(admin_token))
    assert resp.status_code == 204


async def test_only_company_admin_issues_codes(
    client: AsyncClient, admin_token: str, sysadmin_token: str
) -> None:
    url, contact = await _customer_with_contacts(client, admin_token)
    await create_user(client, admin_token, "quanly1", ["manager"])
    manager = await login(client, "quanly1", "password-123")
    resp = await client.post(f"{url}/{contact['id']}/activation-code", headers=auth(manager))
    assert resp.status_code == 403
    # Admin công ty khác không cấp được mã cho liên hệ của công ty này.
    await create_company(client, sysadmin_token, "NPPB", "admin_b")
    admin_b = await login(client, "admin_b", "admin-pass-123")
    resp = await client.post(f"{url}/{contact['id']}/activation-code", headers=auth(admin_b))
    assert resp.status_code == 404
