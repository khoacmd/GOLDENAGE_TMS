from typing import Any

import pytest
from httpx import AsyncClient

from app.modules.delivery import service as delivery_service
from tests.conftest import (
    PLAN_DATE,
    Env,
    auth,
    create_company,
    login,
    stop,
    trip_body,
    zalo_activate,
)
from tests.test_delivery import NOW, confirm, dispatched_trip, photo

ORDERS = "/api/v1/customer/orders"


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_service, "utcnow", lambda: NOW)


async def customer_token(client: AsyncClient, env: Env, phone: str, zalo_id: str) -> str:
    """Kích hoạt Zalo cho liên hệ (theo SĐT) của KH001 trong dữ liệu mẫu."""
    customer = (
        await client.get("/api/v1/customers", headers=auth(env.admin), params={"q": "KH001"})
    ).json()["items"][0]
    contacts = (
        await client.get(f"/api/v1/customers/{customer['id']}/contacts", headers=auth(env.admin))
    ).json()
    contact = next(c for c in contacts if c["phone"] == phone)
    issue = f"/api/v1/customers/{customer['id']}/contacts/{contact['id']}/activation-code"
    session = await zalo_activate(client, env.admin, issue, zalo_id)
    token: str = session["access_token"]
    return token


async def orders(client: AsyncClient, token: str, day: str = PLAN_DATE) -> dict[str, Any]:
    resp = await client.get(ORDERS, headers=auth(token), params={"date": day})
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def by_ref(listing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {o["external_ref"]: o for o in listing["items"]}


async def test_owner_and_point_contacts_see_their_scope(client: AsyncClient, env: Env) -> None:
    owner = await customer_token(client, env, "0912000001", "zalo-owner")
    point = await customer_token(client, env, "0913000012", "zalo-dg2")  # KH001 / DG2

    mine = by_ref(await orders(client, owner))
    assert {"DH2610-001", "DH2610-002"} <= set(mine)
    assert all(o["customer_code"] == "KH001" for o in mine.values())
    assert mine["DH2610-001"]["order_value"] == "18400000.00"
    assert mine["DH2610-001"]["status"] == "WAITING"

    theirs = by_ref(await orders(client, point))
    assert set(theirs) == {"DH2610-002"}
    assert theirs["DH2610-002"]["order_value"] is None
    assert theirs["DH2610-002"]["can_see_value"] is False

    detail = (
        await client.get(f"{ORDERS}/{theirs['DH2610-002']['id']}", headers=auth(point))
    ).json()
    assert [(line["product_code"], line["amount"]) for line in detail["lines"]] == [
        ("NUOC-SUOI-500", None)
    ]
    owner_detail = (
        await client.get(f"{ORDERS}/{theirs['DH2610-002']['id']}", headers=auth(owner))
    ).json()
    assert owner_detail["lines"][0]["amount"] == "3200000.00"

    # Đơn của điểm giao khác (DG1) → 404 với liên hệ DG2.
    resp = await client.get(f"{ORDERS}/{mine['DH2610-001']['id']}", headers=auth(point))
    assert resp.status_code == 404
    assert (await orders(client, owner, "2026-11-20"))["items"] == []

    # Một Zalo vừa là liên hệ điểm giao vừa là chủ → quyền như chủ.
    both = await customer_token(client, env, "0912000001", "zalo-dg2")
    assert by_ref(await orders(client, both))["DH2610-002"]["order_value"] == "3200000.00"


async def test_delivery_progress_and_log(client: AsyncClient, env: Env) -> None:
    owner = await customer_token(client, env, "0912000001", "zalo-owner")

    async def status(ref: str = "DH2610-001") -> str:
        result: str = by_ref(await orders(client, owner))[ref]["status"]
        return result

    # Lệnh nháp là thông tin nội bộ: khách vẫn thấy "chưa lên lịch".
    draft = trip_body(
        env, "XE01", "KHO01", [stop(env, ("DH2610-002", "DRY"))], assistant_id=env.assistant_id
    )
    resp = await client.post("/api/v1/trips", headers=auth(env.manager), json=draft)
    assert resp.status_code == 201, resp.text
    assert await status("DH2610-002") == "WAITING"

    trip = await dispatched_trip(client, env)  # DH2610-001 (khô + lạnh), DH2610-007
    assert await status() == "IN_TRANSIT"

    items = {i["temp_group"]: i for i in trip["stops"][0]["items"]}
    key = await photo(client, env.driver_token)
    resp = await confirm(client, env, trip, items["COLD"]["id"], photo_keys=[key])
    assert resp.json()["accepted"], resp.text
    resp = await confirm(
        client, env, trip, items["DRY"]["id"], status="FAILED", reason="Khách đóng cửa"
    )
    assert resp.json()["accepted"], resp.text
    assert await status() == "PARTIAL"

    order_id = by_ref(await orders(client, owner))["DH2610-001"]["id"]
    detail = (await client.get(f"{ORDERS}/{order_id}", headers=auth(owner))).json()
    log = {d["temp_group"]: d for d in detail["deliveries"]}
    assert log["COLD"]["status"] == "DELIVERED"
    assert log["COLD"]["driver_name"] == "laixe1"
    assert log["COLD"]["photo_urls"] == [f"memory://{key}"]
    assert log["COLD"]["delivered_at"] is not None
    assert log["DRY"]["status"] == "FAILED"
    assert log["DRY"]["reason"] == "Khách đóng cửa"
    assert detail["delivered_at"] is not None


async def test_customer_cannot_read_other_company_orders(
    client: AsyncClient, env: Env, sysadmin_token: str
) -> None:
    order_id = by_ref(await orders(client, await customer_token(client, env, "0912000001", "z1")))[
        "DH2610-001"
    ]["id"]

    await create_company(client, sysadmin_token, "NPPB", "admin_b")
    admin_b = await login(client, "admin_b", "admin-pass-123")
    customer = (
        await client.post(
            "/api/v1/customers",
            headers=auth(admin_b),
            json={
                "code": "KH001",
                "name": "Đại lý B",
                "delivery_points": [
                    {"code": "DG1", "address": "HN", "latitude": "21", "longitude": "105.8"}
                ],
            },
        )
    ).json()
    contact = (
        await client.post(
            f"/api/v1/customers/{customer['id']}/contacts",
            headers=auth(admin_b),
            json={"name": "B", "phone": "0912000001"},
        )
    ).json()
    issue = f"/api/v1/customers/{customer['id']}/contacts/{contact['id']}/activation-code"
    token_b = (await zalo_activate(client, admin_b, issue, "zalo-b"))["access_token"]

    assert (await orders(client, token_b))["items"] == []
    resp = await client.get(f"{ORDERS}/{order_id}", headers=auth(token_b))
    assert resp.status_code == 404
