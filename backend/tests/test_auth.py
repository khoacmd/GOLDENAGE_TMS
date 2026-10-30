from httpx import AsyncClient

from tests.conftest import SYSADMIN, auth, create_company, login


async def test_sysadmin_login_without_company(client: AsyncClient, sysadmin_token: str) -> None:
    resp = await client.get("/api/v1/auth/me", headers=auth(sysadmin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_system_admin"] is True
    assert body["company"] is None
    assert body["roles"] == []


async def test_wrong_password_rejected(client: AsyncClient, sysadmin_token: str) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": SYSADMIN["username"], "password": "sai"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


async def test_missing_or_invalid_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=auth("rac"))).status_code == 401


async def test_company_admin_login_and_me(client: AsyncClient, sysadmin_token: str) -> None:
    company = await create_company(client, sysadmin_token, "NPP01", "admin01")
    token = await login(client, "ADMIN01", "admin-pass-123")  # username không phân biệt hoa/thường

    body = (await client.get("/api/v1/auth/me", headers=auth(token))).json()
    assert body["company"]["id"] == company["id"]
    assert body["roles"] == ["company_admin"]


async def test_refresh_token(client: AsyncClient, sysadmin_token: str) -> None:
    await create_company(client, sysadmin_token, "NPP01", "admin01")
    tokens = (
        await client.post(
            "/api/v1/auth/login", json={"username": "admin01", "password": "admin-pass-123"}
        )
    ).json()

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=auth(resp.json()["access_token"]))).json()[
        "roles"
    ] == ["company_admin"]

    # Access token không được dùng để refresh.
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401


async def test_user_in_many_companies_must_choose(client: AsyncClient, sysadmin_token: str) -> None:
    await create_company(client, sysadmin_token, "NPP01", "admin01")
    # Gán admin01 làm admin công ty thứ hai (dùng tài khoản có sẵn).
    await create_company(client, sysadmin_token, "NPP02", "admin01")

    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin01", "password": "admin-pass-123"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "company_required"

    token = await login(client, "admin01", "admin-pass-123", company_code="npp02")
    body = (await client.get("/api/v1/auth/me", headers=auth(token))).json()
    assert body["company"]["code"] == "NPP02"
    assert {m["company"]["code"] for m in body["memberships"]} == {"NPP01", "NPP02"}


async def test_closed_company_blocks_login(client: AsyncClient, sysadmin_token: str) -> None:
    company = await create_company(client, sysadmin_token, "NPP01", "admin01")
    token = await login(client, "admin01", "admin-pass-123")

    resp = await client.patch(
        f"/api/v1/admin/companies/{company['id']}",
        headers=auth(sysadmin_token),
        json={"is_active": False},
    )
    assert resp.status_code == 200

    assert (await client.get("/api/v1/auth/me", headers=auth(token))).status_code == 401
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin01", "password": "admin-pass-123"}
    )
    assert resp.status_code == 401
