"""Kiểm thử bảo mật (M6): cô lập dữ liệu giữa công ty và ma trận phân quyền, quét MỌI endpoint
trong OpenAPI → endpoint mới tự được kiểm tra; endpoint mới mở cho khách/lái xe phải khai báo
vào danh sách cho phép bên dưới."""

import re
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.main import app
from tests.conftest import PLAN_DATE, Env, auth, create_company, create_user, login, stop, trip_body

PARAM = re.compile(r"{(\w+)}")
WRITE = {"post", "put", "patch", "delete"}

# Endpoint không cần đăng nhập (hoặc xác thực bằng cách khác).
PUBLIC = {
    ("get", "/health"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
    ("post", "/api/v1/integration/{kind}"),  # X-API-Key, kiểm tra riêng bên dưới
}
# Endpoint tài khoản chỉ có vai trò lái xe được gọi.
DRIVER_ALLOWED = {
    ("get", "/api/v1/auth/me"),
    ("post", "/api/v1/trips/{trip_id}/dispatch"),
} | {
    (m, p)
    for p, ops in app.openapi()["paths"].items()
    if p.startswith("/api/v1/driver/")
    for m in ops
}
# Tham số query bắt buộc → giá trị hợp lệ.
QUERY = {"plan_date": PLAN_DATE, "date_from": "2026-11-01", "date_to": "2026-11-30"}


def operations() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method, path, op)
        for path, ops in sorted(app.openapi()["paths"].items())
        for method, op in ops.items()
    ]


def required_query(op: dict[str, Any]) -> dict[str, str]:
    return {
        p["name"]: QUERY[p["name"]]
        for p in op.get("parameters", [])
        if p["in"] == "query" and p.get("required")
    }


@dataclass
class TenantA:
    env: Env
    ids: dict[str, str]  # tên tham số path → id thuộc công ty A
    trip: dict[str, Any]


@pytest.fixture
async def tenant_a(client: AsyncClient, env: Env, sysadmin_token: str) -> TenantA:
    """Công ty A (dữ liệu mẫu) có đủ loại dữ liệu: lệnh đã xuất phát, đơn, thiết bị, API key…"""
    m = auth(env.manager)
    body = trip_body(env, "XE02", "KHO01", [stop(env, ("DH2610-007", "DRY"))])
    trip = (await client.post("/api/v1/trips", headers=m, json=body)).json()
    url = f"/api/v1/trips/{trip['id']}"
    await client.post(f"{url}/approve", headers=m)
    await client.post(f"{url}/prepare", headers=auth(env.keeper))
    await client.post(f"{url}/pick", headers=auth(env.keeper))
    trip = (await client.post(f"{url}/dispatch", headers=auth(env.driver_token))).json()
    assert trip["order_status"] == "DISPATCHED", trip

    async def first(path: str) -> str:
        resp = await client.get(path, headers=auth(env.admin), params={"limit": 1})
        items = resp.json()
        return str((items["items"] if isinstance(items, dict) else items)[0]["id"])

    device = await client.post(
        "/api/v1/devices",
        headers=auth(env.admin),
        json={"device_type": "PRINTER", "name": "Máy in A", "identifier": "PRN-A"},
    )
    key = await client.post("/api/v1/api-keys", headers=auth(env.admin), json={"name": "erp"})
    run = await client.post(
        "/api/v1/planning/runs", headers=m, json={"plan_date": PLAN_DATE, "replace_drafts": False}
    )
    companies = (await client.get("/api/v1/admin/companies", headers=auth(sysadmin_token))).json()
    ids = {
        "trip_id": trip["id"],
        "item_id": trip["stops"][0]["items"][0]["id"],
        "customer_id": await first("/api/v1/customers"),
        "product_id": await first("/api/v1/products"),
        "vehicle_id": env.vehicles["XE01"],
        "warehouse_id": env.warehouses["KHO01"],
        "order_id": await first("/api/v1/orders"),
        "device_id": device.json()["id"],
        "key_id": key.json()["id"],
        "run_id": run.json()["id"],
        "user_id": env.driver_id,
        "company_id": next(c["id"] for c in companies if c["code"] == "NPP01"),
        "kind": "products",
    }
    return TenantA(env=env, ids=ids, trip=trip)


@pytest.fixture
async def b_token(client: AsyncClient, sysadmin_token: str) -> str:
    """Công ty B: một tài khoản có đủ mọi vai trò (mạnh nhất có thể trong công ty B)."""
    await create_company(client, sysadmin_token, "NPPB", "admin_b")
    admin_b = await login(client, "admin_b", "admin-pass-123")
    await create_user(
        client, admin_b, "b_all", ["company_admin", "manager", "warehouse_keeper", "driver"]
    )
    return await login(client, "b_all", "password-123")


def write_body(path: str, a: TenantA) -> Any:
    """Body hợp lệ để request đi tới bước tìm dữ liệu (không dừng ở 422)."""
    bodies: dict[str, Any] = {
        "/api/v1/trips/{trip_id}": trip_body(
            a.env, "XE02", "KHO01", [stop(a.env, ("DH2610-001", "DRY"))]
        ),
        "/api/v1/trips/{trip_id}/cancel": {"reason": "thử"},
        "/api/v1/trips/{trip_id}/items/{item_id}": {"status": "SUCCESS"},
        "/api/v1/trips/{trip_id}/cost": {"extra_cost": 1},
        "/api/v1/orders/{order_id}/cancel": {"reason": "thử"},
        "/api/v1/users/{user_id}/roles": {"roles": ["manager"]},
        "/api/v1/driver/trips/{trip_id}/items/{item_id}/confirm": {
            "client_id": str(uuid.uuid4()),
            "status": "SUCCESS",
            "device_time": "2026-11-02T10:00:00+07:00",
            "latitude": 21,
            "longitude": 105,
            "photo_keys": [],
        },
    }
    return bodies.get(path, {})


async def snapshot(client: AsyncClient, a: TenantA) -> list[Any]:
    token = auth(a.env.admin)
    paths = [
        f"/api/v1/trips/{a.ids['trip_id']}",
        f"/api/v1/trips/{a.ids['trip_id']}/cost",
        f"/api/v1/customers/{a.ids['customer_id']}",
        f"/api/v1/products/{a.ids['product_id']}",
        f"/api/v1/vehicles/{a.ids['vehicle_id']}",
        f"/api/v1/warehouses/{a.ids['warehouse_id']}",
        f"/api/v1/orders/{a.ids['order_id']}",
        "/api/v1/devices",
        "/api/v1/api-keys",
        "/api/v1/users",
        "/api/v1/company/settings",
    ]
    return [(await client.get(p, headers=token)).json() for p in paths]


async def test_other_company_cannot_touch_any_object(
    client: AsyncClient, tenant_a: TenantA, b_token: str
) -> None:
    """Công ty B gọi mọi endpoint có id với id của công ty A → 403/404, dữ liệu A không đổi."""
    before = await snapshot(client, tenant_a)
    leaks = []
    for method, path, op in operations():
        names = PARAM.findall(path)
        if not names or names == ["kind"] or (method, path) in PUBLIC:
            continue
        url = path.format(**{n: tenant_a.ids[n] for n in names})
        kwargs: dict[str, Any] = {"params": required_query(op)}
        if method in WRITE and "requestBody" in op:
            if "multipart/form-data" in op["requestBody"]["content"]:
                kwargs["files"] = {"file": ("a.csv", b"code,name\n")}
            else:
                kwargs["json"] = write_body(path, tenant_a)
        resp = await client.request(method, url, headers=auth(b_token), **kwargs)
        if resp.status_code not in (403, 404):
            leaks.append((method.upper(), path, resp.status_code, resp.text[:200]))
    assert leaks == []
    assert await snapshot(client, tenant_a) == before


async def test_lists_do_not_leak_other_company(
    client: AsyncClient, tenant_a: TenantA, b_token: str
) -> None:
    secrets = set(tenant_a.ids.values()) - {"products"}
    leaks = []
    for method, path, op in operations():
        if method != "get" or PARAM.search(path) or (method, path) in PUBLIC:
            continue
        resp = await client.get(path, headers=auth(b_token), params=required_query(op))
        if resp.status_code == 403:  # vd. /admin/companies
            continue
        assert resp.status_code == 200, (path, resp.text)
        found = [s for s in secrets if s in resp.text]
        if found or "DH2610" in resp.text or "L261102" in resp.text:
            leaks.append((path, found))
    assert leaks == []


async def test_body_references_to_other_company_are_rejected(
    client: AsyncClient, tenant_a: TenantA, b_token: str
) -> None:
    """Khóa ngoại của PostgreSQL không chịu RLS → service phải tự từ chối id của công ty khác."""

    async def trips_of_a() -> list[Any]:
        resp = await client.get(
            f"/api/v1/trips?plan_date={PLAN_DATE}", headers=auth(tenant_a.env.manager)
        )
        return sorted((t["id"], t["order_status"]) for t in resp.json())

    before = await trips_of_a()
    a, b = tenant_a.ids, auth(b_token)
    # Lệnh giao dùng xe/kho/phần đơn/lái xe của A.
    body = trip_body(tenant_a.env, "XE01", "KHO01", [stop(tenant_a.env, ("DH2610-001", "DRY"))])
    resp = await client.post("/api/v1/trips", headers=b, json=body)
    assert resp.status_code in (400, 404, 422), resp.text
    # Kho của B, nhưng xe và lái xe của A.
    wh_b = await client.post(
        "/api/v1/warehouses",
        headers=b,
        json={"code": "KB", "name": "Kho B", "address": "x", "latitude": 21, "longitude": 105},
    )
    body = {**body, "warehouse_id": wh_b.json()["id"], "stops": []}
    resp = await client.post("/api/v1/trips", headers=b, json=body)
    assert resp.status_code in (400, 404, 422), resp.text
    # Xe của B được gán kho của A.
    vehicle = {
        "code": "XB",
        "name": "Xe B",
        "plate_no": "29B-00000",
        "vehicle_type": "CAR",
        "capacity_kg": 1000,
        "cost_per_km": 5000,
        "warehouse_ids": [a["warehouse_id"]],
    }
    resp = await client.post("/api/v1/vehicles", headers=b, json=vehicle)
    assert resp.status_code in (400, 404, 422), resp.text
    # Thiết bị của B gán kho / người dùng của A.
    for ref in ({"warehouse_id": a["warehouse_id"]}, {"user_id": a["user_id"]}):
        resp = await client.post(
            "/api/v1/devices", headers=b, json={"device_type": "PC", "name": "PC B", **ref}
        )
        assert resp.status_code in (400, 404, 422), (ref, resp.text)
    # Chuyển điểm dừng giữa các lệnh của A.
    resp = await client.post(
        "/api/v1/planning/move-stop",
        headers=b,
        json={
            "from_trip_id": a["trip_id"],
            "stop_id": tenant_a.trip["stops"][0]["id"],
            "to_trip_id": a["trip_id"],
        },
    )
    assert resp.status_code in (403, 404), resp.text
    # Không tạo / đổi gì ở A.
    assert await trips_of_a() == before


async def test_api_key_only_writes_own_company(
    client: AsyncClient, tenant_a: TenantA, b_token: str
) -> None:
    key_b = (
        await client.post("/api/v1/api-keys", headers=auth(b_token), json={"name": "b"})
    ).json()
    row = {
        "code": "SP-B",
        "name": "Hàng của B",
        "temp_class": "DRY",
        "uom": "Thùng",
        "weight_kg": 1,
    }
    resp = await client.post(
        "/api/v1/integration/products",
        headers={"X-API-Key": key_b["api_key"]},
        json={"rows": [row]},
    )
    assert resp.status_code == 200, resp.text
    products_a = await client.get(
        "/api/v1/products", headers=auth(tenant_a.env.manager), params={"q": "SP-B"}
    )
    assert products_a.json()["items"] == []
    # Key đã thu hồi / key sai → 401.
    await client.post(f"/api/v1/api-keys/{key_b['id']}/revoke", headers=auth(b_token))
    for key in (key_b["api_key"], "tms_invalid"):
        resp = await client.post(
            "/api/v1/integration/products", headers={"X-API-Key": key}, json={"rows": [row]}
        )
        assert resp.status_code == 401


async def test_anonymous_and_bad_tokens_are_rejected(client: AsyncClient, env: Env) -> None:
    forged = env.manager[:-4] + ("AAAA" if not env.manager.endswith("AAAA") else "BBBB")
    open_ = []
    for method, path, op in operations():
        if (method, path) in PUBLIC:
            continue
        url = PARAM.sub(str(uuid.uuid4()), path)
        for headers in ({}, auth(forged), auth("not-a-jwt")):
            resp = await client.request(method, url, headers=headers, params=required_query(op))
            if resp.status_code != 401:
                open_.append((method.upper(), path, headers != {}, resp.status_code))
    assert open_ == []


async def test_driver_only_reaches_driver_endpoints(client: AsyncClient, tenant_a: TenantA) -> None:
    driver = auth(tenant_a.env.driver_token)
    allowed = []
    for method, path, op in operations():
        if (method, path) in PUBLIC | DRIVER_ALLOWED:
            continue
        url = path.format(**{n: tenant_a.ids[n] for n in PARAM.findall(path)})
        kwargs: dict[str, Any] = {"params": required_query(op)}
        if method in WRITE and "requestBody" in op:
            if "multipart/form-data" in op["requestBody"]["content"]:
                kwargs["files"] = {"file": ("a.csv", b"code,name\n")}
            else:
                kwargs["json"] = write_body(path, tenant_a)
        resp = await client.request(method, url, headers=driver, **kwargs)
        if resp.status_code != 403:
            allowed.append((method.upper(), path, resp.status_code))
    assert allowed == []


async def test_login_locked_after_repeated_failures(client: AsyncClient, admin_token: str) -> None:
    url = "/api/v1/auth/login"
    for _ in range(5):
        resp = await client.post(url, json={"username": "admin01", "password": "sai-mat-khau"})
        assert resp.status_code == 401
    # Đúng mật khẩu cũng bị chặn trong cửa sổ khóa.
    resp = await client.post(url, json={"username": "ADMIN01", "password": "admin-pass-123"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "too_many_attempts"
    # Tài khoản khác cùng IP vẫn đăng nhập được (ngưỡng theo IP cao hơn).
    resp = await client.post(url, json={"username": "sysadmin", "password": "sysadmin-pass"})
    assert resp.status_code in (200, 401)
    assert resp.status_code != 429


async def test_import_file_size_limit(
    client: AsyncClient, admin_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_import_bytes", 1024)
    resp = await client.post(
        "/api/v1/imports/products",
        headers=auth(admin_token),
        files={"file": ("big.csv", b"code,name\n" + b"x" * 2048)},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "file_too_large"
