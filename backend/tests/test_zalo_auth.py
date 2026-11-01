from typing import Any

from httpx import AsyncClient

from tests.conftest import auth, create_company, create_user, login, zalo_activate

LOGIN = "/api/v1/auth/zalo/login"


async def _customer(client: AsyncClient, admin: str, code: str = "KH001") -> dict[str, Any]:
    body = {
        "code": code,
        "name": f"Đại lý {code}",
        "delivery_points": [
            {"code": "DG1", "address": "HN", "latitude": "21", "longitude": "105.8"},
            {"code": "DG2", "address": "HN", "latitude": "21.01", "longitude": "105.8"},
        ],
    }
    customer: dict[str, Any] = (
        await client.post("/api/v1/customers", headers=auth(admin), json=body)
    ).json()
    return customer


async def _contact(
    client: AsyncClient, admin: str, customer: dict[str, Any], phone: str, point: str | None = None
) -> str:
    point_id = (
        next(p["id"] for p in customer["delivery_points"] if p["code"] == point) if point else None
    )
    resp = await client.post(
        f"/api/v1/customers/{customer['id']}/contacts",
        headers=auth(admin),
        json={"name": phone, "phone": phone, "delivery_point_id": point_id},
    )
    return f"/api/v1/customers/{customer['id']}/contacts/{resp.json()['id']}/activation-code"


async def test_customer_activate_login_and_me(client: AsyncClient, admin_token: str) -> None:
    resp = await client.post(LOGIN, json={"access_token": "mock:zalo-1:Anh A"})
    assert resp.json()["status"] == "not_linked"

    customer = await _customer(client, admin_token)
    owner = await _contact(client, admin_token, customer, "0912000001")
    point = await _contact(client, admin_token, customer, "0912000002", "DG2")
    session = await zalo_activate(client, admin_token, point, "zalo-1", "Anh A")
    assert session["status"] == "ok" and session["account"]["kind"] == "customer"

    me = (await client.get("/api/v1/customer/me", headers=auth(session["access_token"]))).json()
    assert [(s["customer_code"], s["delivery_point_code"]) for s in me["scopes"]] == [
        ("KH001", "DG2")
    ]

    # Cùng Zalo được liên kết thêm làm liên hệ chủ → có cả 2 phạm vi.
    await zalo_activate(client, admin_token, owner, "zalo-1")
    session = (await client.post(LOGIN, json={"access_token": "mock:zalo-1:Anh A"})).json()
    me = (await client.get("/api/v1/customer/me", headers=auth(session["access_token"]))).json()
    assert {s["delivery_point_code"] for s in me["scopes"]} == {None, "DG2"}

    # Token khách hàng làm mới qua /auth/zalo/refresh, không qua /auth/refresh.
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}
    )
    assert resp.status_code == 401
    resp = await client.post(
        "/api/v1/auth/zalo/refresh", json={"refresh_token": session["refresh_token"]}
    )
    assert resp.status_code == 200 and resp.json()["account"]["kind"] == "customer"

    # Thu hồi cả 2 liên hệ → token hiện tại hết hiệu lực, đăng nhập lại báo chưa liên kết.
    for url in (owner, point):
        await client.delete(url.replace("/activation-code", "/zalo"), headers=auth(admin_token))
    assert (
        await client.get("/api/v1/customer/me", headers=auth(session["access_token"]))
    ).status_code == 401
    resp = await client.post(
        "/api/v1/auth/zalo/refresh", json={"refresh_token": session["refresh_token"]}
    )
    assert resp.status_code == 401
    assert (await client.post(LOGIN, json={"access_token": "mock:zalo-1"})).json()["status"] == (
        "not_linked"
    )


async def test_logout_customer_session(client: AsyncClient, admin_token: str) -> None:
    customer = await _customer(client, admin_token)
    session = await zalo_activate(
        client, admin_token, await _contact(client, admin_token, customer, "0912000001"), "zalo-1"
    )
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth(session["access_token"]),
        json={"refresh_token": session["refresh_token"]},
    )
    assert resp.status_code == 204
    assert (
        await client.get("/api/v1/customer/me", headers=auth(session["access_token"]))
    ).status_code == 401
    resp = await client.post(
        "/api/v1/auth/zalo/refresh", json={"refresh_token": session["refresh_token"]}
    )
    assert resp.status_code == 401


async def test_driver_via_zalo_and_choose_account(
    client: AsyncClient, admin_token: str, sysadmin_token: str
) -> None:
    driver_id = await create_user(client, admin_token, "laixe1", ["driver"])
    session = await zalo_activate(
        client, admin_token, f"/api/v1/users/{driver_id}/activation-code", "zalo-9"
    )
    assert session["account"]["kind"] == "driver"
    # Phiên lái xe qua Zalo = token nhân viên → gọi được API lái xe.
    driver = auth(session["access_token"])
    assert (await client.get("/api/v1/auth/me", headers=driver)).json()["roles"] == ["driver"]
    assert (
        await client.get("/api/v1/driver/trips", headers=driver, params={"plan_date": "2026-11-02"})
    ).status_code == 200
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}
    )
    assert resp.status_code == 401  # phiên Zalo làm mới qua /auth/zalo/refresh
    resp = await client.post(
        "/api/v1/auth/zalo/refresh", json={"refresh_token": session["refresh_token"]}
    )
    assert resp.json()["account"]["kind"] == "driver"

    # Cùng Zalo là khách hàng của công ty khác → phải chọn tài khoản.
    await create_company(client, sysadmin_token, "NPPB", "admin_b")
    admin_b = await login(client, "admin_b", "admin-pass-123")
    customer_b = await _customer(client, admin_b, "KHB")
    await zalo_activate(
        client, admin_b, await _contact(client, admin_b, customer_b, "0912000009"), "zalo-9"
    )
    resp = (await client.post(LOGIN, json={"access_token": "mock:zalo-9"})).json()
    assert resp["status"] == "choose_account"
    assert {(a["company"]["code"], a["kind"]) for a in resp["accounts"]} == {
        ("NPP01", "driver"),
        ("NPPB", "customer"),
    }
    company_b = next(a["company"]["id"] for a in resp["accounts"] if a["kind"] == "customer")
    chosen = (
        await client.post(
            LOGIN, json={"access_token": "mock:zalo-9", "company_id": company_b, "kind": "customer"}
        )
    ).json()
    assert chosen["status"] == "ok" and chosen["account"]["company"]["code"] == "NPPB"

    # Lái xe được thêm vai trò khác → không đăng nhập Zalo dạng lái xe nữa (như PIN).
    await client.put(
        f"/api/v1/users/{driver_id}/roles",
        headers=auth(admin_token),
        json={"roles": ["driver", "manager"]},
    )
    resp = (await client.post(LOGIN, json={"access_token": "mock:zalo-9"})).json()
    assert resp["status"] == "ok" and resp["account"]["kind"] == "customer"


async def test_mock_token_rejected_when_mock_disabled(
    client: AsyncClient, monkeypatch: Any
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "zalo_mock", False)
    resp = await client.post(LOGIN, json={"access_token": "mock:zalo-1"})
    assert resp.status_code == 401  # chưa cấu hình app secret → không xác thực được
