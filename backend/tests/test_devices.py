import pytest
from httpx import AsyncClient

from app.modules.delivery import service as delivery_service
from tests.conftest import Env, auth, create_company, login
from tests.test_delivery import NOW, confirm, dispatched_trip, item_ids

PHONE = {
    "identifier": "install-0001",
    "platform": "android",
    "model": "SM-A155",
    "os_version": "14",
}


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_service, "utcnow", lambda: NOW)


async def register(client: AsyncClient, token: str, **overrides: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/driver/device", headers=auth(token), json={**PHONE, **overrides}
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, str] = resp.json()
    return body


async def test_admin_manages_pc_and_printer(client: AsyncClient, env: Env) -> None:
    printer = {
        "device_type": "PRINTER",
        "name": "Máy in kho Hà Đông",
        "identifier": "PRN-01",
        "warehouse_id": env.warehouses["KHO01"],
        "connection": "NETWORK",
        "address": "192.168.1.50",
        "paper_size": "A4",
    }
    resp = await client.post("/api/v1/devices", headers=auth(env.admin), json=printer)
    assert resp.status_code == 201, resp.text
    device = resp.json()
    assert device["status"] == "ACTIVE" and device["paper_size"] == "A4"

    dup = await client.post(
        "/api/v1/devices",
        headers=auth(env.admin),
        json={"device_type": "PC", "name": "PC", "identifier": "prn-01"},
    )
    assert dup.status_code == 409

    resp = await client.patch(
        f"/api/v1/devices/{device['id']}", headers=auth(env.admin), json={"status": "BLOCKED"}
    )
    assert resp.json()["status"] == "BLOCKED"
    listed = await client.get("/api/v1/devices?device_type=PRINTER", headers=auth(env.admin))
    assert listed.json()["total"] == 1

    # Chỉ admin công ty quản lý thiết bị.
    assert (await client.get("/api/v1/devices", headers=auth(env.manager))).status_code == 403

    resp = await client.delete(f"/api/v1/devices/{device['id']}", headers=auth(env.admin))
    assert resp.status_code == 204
    assert (await client.get("/api/v1/devices", headers=auth(env.admin))).json()["total"] == 0


async def test_mobile_registration_is_upsert(client: AsyncClient, env: Env) -> None:
    first = await register(client, env.driver_token)
    again = await register(client, env.driver_token, app_version="1.0.1")
    assert first["id"] == again["id"] and first["status"] == "ACTIVE"
    devices = (await client.get("/api/v1/devices", headers=auth(env.admin))).json()["items"]
    assert len(devices) == 1
    assert devices[0]["user_id"] == env.driver_id and devices[0]["app_version"] == "1.0.1"


async def test_device_approval_and_blocking(client: AsyncClient, env: Env) -> None:
    await client.put(
        "/api/v1/company/settings",
        headers=auth(env.admin),
        json={"require_device_approval": True, "photo_required_success": False},
    )
    trip = await dispatched_trip(client, env)
    first, second, third = item_ids(trip)

    # Thiết bị chưa đăng ký.
    resp = await confirm(client, env, trip, first)
    assert resp.json()["accepted"] is False
    assert "Thiết bị chưa được đăng ký" in resp.json()["violations"]

    device = await register(client, env.driver_token)
    assert device["status"] == "PENDING"
    resp = await confirm(client, env, trip, first, device_id=PHONE["identifier"])
    assert resp.json()["violations"] == ["Thiết bị đang chờ admin công ty duyệt"]

    await client.patch(
        f"/api/v1/devices/{device['id']}", headers=auth(env.admin), json={"status": "ACTIVE"}
    )
    resp = await confirm(client, env, trip, first, device_id=PHONE["identifier"])
    assert resp.json()["accepted"] is True, resp.json()
    assert resp.json()["device_id"] == device["id"]

    await client.patch(
        f"/api/v1/devices/{device['id']}", headers=auth(env.admin), json={"status": "BLOCKED"}
    )
    resp = await confirm(client, env, trip, second, device_id=PHONE["identifier"])
    assert resp.json()["violations"] == ["Thiết bị đã bị khóa"]

    # Không bật duyệt: thiết bị chưa đăng ký vẫn xác nhận được, nhưng thiết bị bị khóa thì không.
    await client.put(
        "/api/v1/company/settings",
        headers=auth(env.admin),
        json={"require_device_approval": False},
    )
    assert (await confirm(client, env, trip, second)).json()["accepted"] is True
    resp = await confirm(client, env, trip, third, device_id=PHONE["identifier"])
    assert resp.json()["accepted"] is False


async def test_devices_isolated_between_companies(
    client: AsyncClient, env: Env, sysadmin_token: str
) -> None:
    await register(client, env.driver_token)
    await create_company(client, sysadmin_token, "NPP02", "admin02")
    other = await login(client, "admin02", "admin-pass-123")
    assert (await client.get("/api/v1/devices", headers=auth(other))).json()["total"] == 0
