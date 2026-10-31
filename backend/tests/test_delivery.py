import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.modules.delivery import service as delivery_service
from tests.conftest import Env, auth, login, stop, trip_body

VN = ZoneInfo("Asia/Ho_Chi_Minh")
# Giờ server giả lập: 10h sáng ngày giao (trong ca 7h-19h).
NOW = datetime(2026, 11, 2, 10, 0, tzinfo=VN)
DG1 = (20.9705, 105.7782)  # tọa độ điểm giao DG1 của KH001 trong dữ liệu mẫu
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_service, "utcnow", lambda: NOW)


async def dispatched_trip(client: AsyncClient, env: Env) -> dict[str, Any]:
    body = trip_body(
        env,
        "XE02",
        "KHO01",
        [
            stop(env, ("DH2610-001", "COLD"), ("DH2610-001", "DRY")),
            stop(env, ("DH2610-007", "DRY")),
        ],
    )
    trip = (await client.post("/api/v1/trips", headers=auth(env.manager), json=body)).json()
    url = f"/api/v1/trips/{trip['id']}"
    await client.post(f"{url}/approve", headers=auth(env.manager))
    await client.post(f"{url}/prepare", headers=auth(env.keeper))
    await client.post(f"{url}/pick", headers=auth(env.keeper))
    resp = await client.post(f"{url}/dispatch", headers=auth(env.driver_token))
    assert resp.json()["order_status"] == "DISPATCHED", resp.text
    trip_data: dict[str, Any] = resp.json()
    return trip_data


async def photo(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/driver/photos", headers=auth(token), files={"file": ("a.png", PNG, "image/png")}
    )
    assert resp.status_code == 200, resp.text
    key: str = resp.json()["key"]
    return key


def item_ids(trip: dict[str, Any]) -> list[str]:
    return [i["id"] for s in trip["stops"] for i in s["items"]]


async def confirm(
    client: AsyncClient, env: Env, trip: dict[str, Any], item_id: str, **overrides: Any
) -> Any:
    body = {
        "client_id": str(uuid.uuid4()),
        "status": "SUCCESS",
        "device_time": NOW.isoformat(),
        "latitude": DG1[0] + 0.0005,  # ~55 m
        "longitude": DG1[1],
        "accuracy_m": 12,
        "photo_keys": [],
        **overrides,
    }
    return await client.post(
        f"/api/v1/driver/trips/{trip['id']}/items/{item_id}/confirm",
        headers=auth(env.driver_token),
        json=body,
    )


async def test_driver_sees_assigned_trips(client: AsyncClient, env: Env) -> None:
    trip = await dispatched_trip(client, env)
    mine = (
        await client.get(
            "/api/v1/driver/trips?plan_date=2026-11-02", headers=auth(env.driver_token)
        )
    ).json()
    assert [t["code"] for t in mine] == [trip["code"]]
    detail = await client.get(f"/api/v1/driver/trips/{trip['id']}", headers=auth(env.driver_token))
    assert detail.status_code == 200

    other = await login(client, "phuxe1", "password-123")  # có vai trò driver nhưng không được gán
    assert (
        await client.get(f"/api/v1/driver/trips/{trip['id']}", headers=auth(other))
    ).status_code == 403
    rules = (await client.get("/api/v1/driver/rules", headers=auth(env.driver_token))).json()
    assert (rules["confirm_radius_m"], rules["photo_required_success"]) == (300, True)


async def test_successful_confirmation_with_photo(client: AsyncClient, env: Env) -> None:
    trip = await dispatched_trip(client, env)
    key = await photo(client, env.driver_token)
    first = item_ids(trip)[0]
    resp = await confirm(client, env, trip, first, photo_keys=[key])
    body = resp.json()
    assert body["accepted"] is True, body
    assert body["violations"] == []
    assert 40 < float(body["distance_m"]) < 70

    detail = (await client.get(f"/api/v1/trips/{trip['id']}", headers=auth(env.manager))).json()
    item = next(i for s in detail["stops"] for i in s["items"] if i["id"] == first)
    assert (item["status"], item["is_manual_update"]) == ("SUCCESS", False)

    confirmations = (
        await client.get(f"/api/v1/trips/{trip['id']}/confirmations", headers=auth(env.manager))
    ).json()
    assert confirmations[0]["photos"][0]["key"] == key


async def test_resend_is_idempotent(client: AsyncClient, env: Env) -> None:
    trip = await dispatched_trip(client, env)
    key = await photo(client, env.driver_token)
    client_id = str(uuid.uuid4())
    first = await confirm(
        client, env, trip, item_ids(trip)[0], client_id=client_id, photo_keys=[key]
    )
    again = await confirm(
        client, env, trip, item_ids(trip)[0], client_id=client_id, photo_keys=[key]
    )
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    confirmations = (
        await client.get(f"/api/v1/trips/{trip['id']}/confirmations", headers=auth(env.manager))
    ).json()
    assert len(confirmations) == 1


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"latitude": DG1[0] + 0.01}, "vượt bán kính cho phép 300 m"),  # ~1.1 km
        ({"is_mock_location": True}, "vị trí giả lập"),
        ({"latitude": None, "longitude": None}, "Không lấy được vị trí GPS"),
        ({"device_time": (NOW.replace(hour=21)).isoformat()}, "Ngoài thời gian cho phép"),
        ({"device_time": (NOW - timedelta(hours=5)).isoformat()}, "gửi quá muộn"),
        ({"device_time": (NOW + timedelta(minutes=30)).isoformat()}, "Giờ trên thiết bị"),
        ({"photo_keys": ["other-company/x.png"]}, "Ảnh chứng từ không hợp lệ"),
        ({}, "Cần chụp ảnh chứng từ"),
    ],
)
async def test_rule_violations_are_recorded_not_applied(
    client: AsyncClient, env: Env, overrides: dict[str, Any], expected: str
) -> None:
    trip = await dispatched_trip(client, env)
    if "photo_keys" not in overrides and expected != "Cần chụp ảnh chứng từ":
        overrides["photo_keys"] = [await photo(client, env.driver_token)]
    resp = await confirm(client, env, trip, item_ids(trip)[0], **overrides)
    body = resp.json()
    assert body["accepted"] is False
    assert any(expected in v for v in body["violations"]), body["violations"]
    detail = (await client.get(f"/api/v1/trips/{trip['id']}", headers=auth(env.manager))).json()
    assert detail["stops"][0]["items"][0]["status"] == "PENDING"


async def test_failed_delivery_needs_reason_and_rules_configurable(
    client: AsyncClient, env: Env
) -> None:
    trip = await dispatched_trip(client, env)
    resp = await confirm(client, env, trip, item_ids(trip)[0], status="FAILED")
    assert resp.json()["error"]["code"] == "reason_required"

    # Tắt kiểm tra vị trí → ở xa vẫn được chấp nhận (ảnh không bắt buộc khi thất bại).
    await client.put(
        "/api/v1/company/settings", headers=auth(env.admin), json={"confirm_geofence": False}
    )
    resp = await confirm(
        client,
        env,
        trip,
        item_ids(trip)[0],
        status="FAILED",
        reason="Khách vắng nhà",
        latitude=21.5,
    )
    assert resp.json()["accepted"] is True, resp.json()

    # Mục đã có kết quả thì không xác nhận lại được.
    resp = await confirm(client, env, trip, item_ids(trip)[0], status="FAILED", reason="x")
    assert resp.json()["error"]["code"] == "already_confirmed"


async def test_all_items_confirmed_finishes_trip(client: AsyncClient, env: Env) -> None:
    trip = await dispatched_trip(client, env)
    key = await photo(client, env.driver_token)
    for n, item_id in enumerate(item_ids(trip)):
        # Điểm dừng 2 (KH007) ở xa DG1 → dùng tọa độ của chính điểm đó.
        loc = (
            {}
            if n < 2
            else {
                "latitude": float(trip["stops"][1]["latitude"]),
                "longitude": float(trip["stops"][1]["longitude"]),
            }
        )
        resp = await confirm(client, env, trip, item_id, photo_keys=[key], **loc)
        assert resp.json()["accepted"] is True, resp.json()
    detail = (await client.get(f"/api/v1/trips/{trip['id']}", headers=auth(env.manager))).json()
    assert detail["delivery_status"] == "FINISHED"


async def test_photo_validation(client: AsyncClient, env: Env) -> None:
    resp = await client.post(
        "/api/v1/driver/photos",
        headers=auth(env.driver_token),
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert resp.json()["error"]["code"] == "invalid_photo"
    assert (
        await client.post(
            "/api/v1/driver/photos",
            headers=auth(env.manager),
            files={"file": ("a.png", PNG, "image/png")},
        )
    ).status_code == 403
