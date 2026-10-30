from httpx import AsyncClient

from tests.conftest import auth, create_company, login


async def test_company_admin_manages_users(client: AsyncClient, admin_token: str) -> None:
    resp = await client.post(
        "/api/v1/users",
        headers=auth(admin_token),
        json={
            "username": "thukho01",
            "full_name": "Thủ kho 1",
            "password": "thukho-pass",
            "roles": ["warehouse_keeper"],
        },
    )
    assert resp.status_code == 201, resp.text
    keeper = resp.json()
    keeper_token = await login(client, "thukho01", "thukho-pass")

    # Thủ kho đọc được dữ liệu gốc nhưng không ghi được.
    assert (await client.get("/api/v1/warehouses", headers=auth(keeper_token))).status_code == 200
    resp = await client.post("/api/v1/products", headers=auth(keeper_token), json={})
    assert resp.status_code == 403
    assert (await client.get("/api/v1/users", headers=auth(keeper_token))).status_code == 403

    resp = await client.put(
        f"/api/v1/users/{keeper['id']}/roles",
        headers=auth(admin_token),
        json={"roles": ["warehouse_keeper", "manager"]},
    )
    assert resp.json()["roles"] == ["manager", "warehouse_keeper"]

    resp = await client.patch(
        f"/api/v1/users/{keeper['id']}",
        headers=auth(admin_token),
        json={"password": "new-password", "is_active": False},
    )
    assert resp.json()["is_active"] is False
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "thukho01", "password": "new-password"}
    )
    assert resp.status_code == 401

    users = (await client.get("/api/v1/users", headers=auth(admin_token))).json()
    assert {u["username"] for u in users} == {"admin01", "thukho01"}


async def test_admin_cannot_lock_self_out(client: AsyncClient, admin_token: str) -> None:
    me = (await client.get("/api/v1/auth/me", headers=auth(admin_token))).json()
    resp = await client.put(
        f"/api/v1/users/{me['id']}/roles", headers=auth(admin_token), json={"roles": ["manager"]}
    )
    assert resp.json()["error"]["code"] == "self_lockout"


async def test_cannot_reset_password_of_other_company_user(
    client: AsyncClient, sysadmin_token: str, admin_token: str
) -> None:
    # admin02 thuộc NPP02, được thêm làm admin NPP01 (dùng tài khoản có sẵn).
    await create_company(client, sysadmin_token, "NPP02", "admin02")
    await create_company(client, sysadmin_token, "NPP03", "admin02")
    users = (await client.get("/api/v1/users", headers=auth(admin_token))).json()
    assert "admin02" not in {u["username"] for u in users}

    npp3_admin = await login(client, "admin02", "admin-pass-123", company_code="NPP03")
    me = (await client.get("/api/v1/auth/me", headers=auth(npp3_admin))).json()
    # NPP03 không phải công ty sở hữu tài khoản admin02 (NPP02) → không được đổi mật khẩu.
    resp = await client.patch(
        f"/api/v1/users/{me['id']}", headers=auth(npp3_admin), json={"password": "hacked-123"}
    )
    assert resp.status_code == 403


async def test_update_company_settings(client: AsyncClient, admin_token: str) -> None:
    resp = await client.put(
        "/api/v1/company/settings",
        headers=auth(admin_token),
        json={"working_weekdays": [6, 1, 2, 2], "cutover_time": "16:30:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["working_weekdays"] == [1, 2, 6]
    assert resp.json()["cutover_time"] == "16:30:00"

    resp = await client.put(
        "/api/v1/company/settings",
        headers=auth(admin_token),
        json={"shift_start": "20:00:00"},
    )
    assert resp.json()["error"]["code"] == "invalid_shift"
    resp = await client.put(
        "/api/v1/company/settings", headers=auth(admin_token), json={"timezone": "Mars/Base"}
    )
    assert resp.status_code == 422
