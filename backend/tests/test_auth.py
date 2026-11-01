import asyncio
from typing import Any

from httpx import AsyncClient

from tests.conftest import SYSADMIN, auth, create_company, create_user, login


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


async def test_driver_pin_login(client: AsyncClient, admin_token: str) -> None:
    driver_id = await create_user(client, admin_token, "laixe9", ["driver"])
    manager_id = await create_user(client, admin_token, "quanly9", ["manager", "driver"])
    pin_url = f"/api/v1/users/{driver_id}/pin"

    async def pin_login(username: str, pin: str) -> Any:
        return await client.post("/api/v1/auth/login-pin", json={"username": username, "pin": pin})

    # Chưa đặt PIN → không đăng nhập được bằng PIN.
    assert (await pin_login("laixe9", "246810")).status_code == 401

    # PIN phải đúng 6 chữ số và không quá dễ đoán; chỉ đặt cho tài khoản chỉ là lái xe.
    for weak in ("1234", "12345a", "111111", "123456", "987654"):
        resp = await client.put(pin_url, headers=auth(admin_token), json={"pin": weak})
        assert resp.status_code == 422, weak
    resp = await client.put(
        f"/api/v1/users/{manager_id}/pin", headers=auth(admin_token), json={"pin": "246810"}
    )
    assert resp.json()["error"]["code"] == "pin_not_allowed"

    user = (await client.put(pin_url, headers=auth(admin_token), json={"pin": "246810"})).json()
    assert user["has_pin"] is True
    assert (await pin_login("laixe9", "135790")).status_code == 401
    resp = await pin_login("LAIXE9", "246810")
    assert resp.status_code == 200, resp.text
    me = await client.get("/api/v1/auth/me", headers=auth(resp.json()["access_token"]))
    assert me.json()["roles"] == ["driver"]
    assert (await login(client, "laixe9", "password-123")) is not None  # mật khẩu vẫn dùng được

    # Thêm vai trò khác → PIN không còn dùng được (phải đăng nhập bằng mật khẩu).
    roles_url = f"/api/v1/users/{driver_id}/roles"
    await client.put(roles_url, headers=auth(admin_token), json={"roles": ["driver", "manager"]})
    assert (await pin_login("laixe9", "246810")).status_code == 401
    await client.put(roles_url, headers=auth(admin_token), json={"roles": ["driver"]})

    # Admin xóa PIN.
    user = (await client.delete(pin_url, headers=auth(admin_token))).json()
    assert user["has_pin"] is False
    assert (await pin_login("laixe9", "246810")).status_code == 401


async def test_pin_login_throttled(client: AsyncClient, admin_token: str) -> None:
    driver_id = await create_user(client, admin_token, "laixe8", ["driver"])
    pin_url = f"/api/v1/users/{driver_id}/pin"
    await client.put(pin_url, headers=auth(admin_token), json={"pin": "246810"})
    for i in range(5):
        resp = await client.post(
            "/api/v1/auth/login-pin", json={"username": "laixe8", "pin": f"10000{i}"}
        )
        assert resp.status_code == 401
    # Bị khóa tạm thời, kể cả khi nhập đúng PIN.
    resp = await client.post("/api/v1/auth/login-pin", json={"username": "laixe8", "pin": "246810"})
    assert resp.status_code == 429


async def _tokens(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    tokens: dict[str, str] = resp.json()
    return tokens


async def test_change_password(client: AsyncClient, admin_token: str) -> None:
    await create_user(client, admin_token, "laixe01", ["driver"])
    old = await _tokens(client, "laixe01", "password-123")
    await asyncio.sleep(1.1)  # iat tính theo giây: token cũ phải cấp trước giây đổi mật khẩu

    resp = await client.post(
        "/api/v1/auth/change-password",
        headers=auth(old["access_token"]),
        json={"current_password": "password-123", "new_password": "mat-khau-moi-1"},
    )
    assert resp.status_code == 200, resp.text
    new = resp.json()

    # Phiên hiện tại tiếp tục bằng token mới; token cũ (access + refresh) hết hiệu lực.
    assert (
        await client.get("/api/v1/auth/me", headers=auth(new["access_token"]))
    ).status_code == 200
    assert (
        await client.get("/api/v1/auth/me", headers=auth(old["access_token"]))
    ).status_code == 401
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert resp.status_code == 401
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]})
    assert resp.status_code == 200

    # Đăng nhập: mật khẩu cũ bị từ chối, mật khẩu mới dùng được.
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "laixe01", "password": "password-123"}
    )
    assert resp.status_code == 401
    await login(client, "laixe01", "mat-khau-moi-1")


async def test_change_password_validation(client: AsyncClient, admin_token: str) -> None:
    url, headers = "/api/v1/auth/change-password", auth(admin_token)
    resp = await client.post(
        url, headers=headers, json={"current_password": "sai", "new_password": "mat-khau-moi-1"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "wrong_password"
    resp = await client.post(
        url,
        headers=headers,
        json={"current_password": "admin-pass-123", "new_password": "admin-pass-123"},
    )
    assert resp.json()["error"]["code"] == "same_password"
    resp = await client.post(
        url, headers=headers, json={"current_password": "admin-pass-123", "new_password": "ngan"}
    )
    assert resp.status_code == 422


async def test_change_password_throttled(client: AsyncClient, admin_token: str) -> None:
    body = {"current_password": "sai", "new_password": "mat-khau-moi-1"}
    for _ in range(5):
        await client.post("/api/v1/auth/change-password", headers=auth(admin_token), json=body)
    resp = await client.post(
        "/api/v1/auth/change-password",
        headers=auth(admin_token),
        json={"current_password": "admin-pass-123", "new_password": "mat-khau-moi-1"},
    )
    assert resp.status_code == 429


async def test_admin_reset_password_revokes_tokens(client: AsyncClient, admin_token: str) -> None:
    user_id = await create_user(client, admin_token, "quanly01", ["manager"])
    token = await login(client, "quanly01", "password-123")
    await asyncio.sleep(1.1)
    resp = await client.patch(
        f"/api/v1/users/{user_id}", headers=auth(admin_token), json={"password": "dat-lai-123"}
    )
    assert resp.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=auth(token))).status_code == 401
    await login(client, "quanly01", "dat-lai-123")


async def test_logout_ends_session(client: AsyncClient, admin_token: str) -> None:
    tokens = await _tokens(client, "admin01", "admin-pass-123")
    other = await _tokens(client, "admin01", "admin-pass-123")  # phiên trên máy khác

    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth(tokens["access_token"]),
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 204
    # Access + refresh token của phiên đã đăng xuất hết hiệu lực ngay.
    assert (
        await client.get("/api/v1/auth/me", headers=auth(tokens["access_token"]))
    ).status_code == 401
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401
    # Phiên khác không bị ảnh hưởng.
    assert (
        await client.get("/api/v1/auth/me", headers=auth(other["access_token"]))
    ).status_code == 200


async def test_logout_ignores_invalid_tokens(client: AsyncClient, admin_token: str) -> None:
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "rac"})
    assert resp.status_code == 204
    # Access token của người khác gửi kèm không bị thu hồi.
    tokens = await _tokens(client, "admin01", "admin-pass-123")
    await create_user(client, admin_token, "quanly02", ["manager"])
    other = await _tokens(client, "quanly02", "password-123")
    await client.post(
        "/api/v1/auth/logout",
        headers=auth(other["access_token"]),
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert (
        await client.get("/api/v1/auth/me", headers=auth(other["access_token"]))
    ).status_code == 200
