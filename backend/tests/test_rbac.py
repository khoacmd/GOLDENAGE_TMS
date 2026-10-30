from httpx import AsyncClient

from tests.conftest import auth, create_company, login


async def test_only_system_admin_manages_companies(
    client: AsyncClient, sysadmin_token: str
) -> None:
    await create_company(client, sysadmin_token, "NPP01", "admin01")
    admin_token = await login(client, "admin01", "admin-pass-123")

    resp = await client.get("/api/v1/admin/companies", headers=auth(admin_token))
    assert resp.status_code == 403
    resp = await client.get("/api/v1/admin/companies", headers=auth(sysadmin_token))
    assert [c["code"] for c in resp.json()] == ["NPP01"]


async def test_duplicate_company_code(client: AsyncClient, sysadmin_token: str) -> None:
    await create_company(client, sysadmin_token, "NPP01", "admin01")
    resp = await client.post(
        "/api/v1/admin/companies",
        headers=auth(sysadmin_token),
        json={"code": "npp01", "name": "Trùng", "admin": {"username": "admin01"}},
    )
    assert resp.status_code == 409


async def test_company_settings_defaults(client: AsyncClient, sysadmin_token: str) -> None:
    await create_company(client, sysadmin_token, "NPP01", "admin01")
    admin_token = await login(client, "admin01", "admin-pass-123")

    resp = await client.get("/api/v1/company/settings", headers=auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["working_weekdays"] == [1, 2, 3, 4, 5, 6]
    assert body["shift_start"] == "07:00:00"
    assert body["shift_end"] == "19:00:00"

    # System admin không thuộc công ty nào → không xem được cấu hình công ty.
    resp = await client.get("/api/v1/company/settings", headers=auth(sysadmin_token))
    assert resp.status_code == 403
