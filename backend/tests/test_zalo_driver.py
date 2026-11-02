import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.modules.delivery import service as delivery_service
from tests.conftest import Env, auth, zalo_activate
from tests.test_delivery import DG1, NOW, dispatched_trip, item_ids, photo

SETTINGS = "/api/v1/company/settings"
NEAR = f"mock:{DG1[0]},{DG1[1]}"
FAR = "mock:21.5,105.0"


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_service, "utcnow", lambda: NOW)


async def zalo_driver(client: AsyncClient, env: Env) -> dict[str, str]:
    url = f"/api/v1/users/{env.driver_id}/activation-code"
    session = await zalo_activate(client, env.admin, url, "zalo-driver")
    return auth(session["access_token"])


async def confirm(
    client: AsyncClient, headers: dict[str, str], trip: dict[str, Any], item: str, **body: Any
) -> Any:
    return await client.post(
        f"/api/v1/driver/trips/{trip['id']}/items/{item}/confirm",
        headers=headers,
        json={
            "client_id": str(uuid.uuid4()),
            "status": "SUCCESS",
            "device_time": NOW.isoformat(),
            **body,
        },
    )


async def enable(client: AsyncClient, env: Env, **settings: Any) -> None:
    resp = await client.put(
        SETTINGS, headers=auth(env.admin), json={"zalo_confirm_enabled": True, **settings}
    )
    assert resp.status_code == 200, resp.text


async def test_company_must_allow_confirming_via_zalo(client: AsyncClient, env: Env) -> None:
    driver = await zalo_driver(client, env)
    trip = await dispatched_trip(client, env)
    item = item_ids(trip)[0]

    # Mặc định tắt: tài xế vẫn xem được chuyến nhưng không xác nhận được, không ghi gì.
    assert (await client.get("/api/v1/driver/rules", headers=driver)).json()[
        "zalo_confirm_enabled"
    ] is False
    assert (
        await client.get(f"/api/v1/driver/trips/{trip['id']}", headers=driver)
    ).status_code == 200
    resp = await confirm(
        client, driver, trip, item, zalo_access_token="t", zalo_location_token=NEAR
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["message"] == "Công ty chưa cho phép xác nhận giao qua Zalo"
    logged = await client.get(
        f"/api/v1/trips/{trip['id']}/confirmations", headers=auth(env.manager)
    )
    assert logged.json() == []

    # Công tắc chỉ áp dụng cho kênh Zalo, app native không bị ảnh hưởng.
    key = await photo(client, env.driver_token)
    resp = await confirm(
        client,
        auth(env.driver_token),
        trip,
        item,
        photo_keys=[key],
        latitude=DG1[0],
        longitude=DG1[1],
    )
    assert resp.status_code == 200 and resp.json()["accepted"], resp.text


async def test_location_comes_from_zalo_not_from_client(client: AsyncClient, env: Env) -> None:
    await enable(client, env, require_device_approval=True)
    driver = await zalo_driver(client, env)
    trip = await dispatched_trip(client, env)
    first, second, *_ = item_ids(trip)
    key = await photo(client, env.driver_token)

    # Client tự khai tọa độ đúng nhưng không có token Zalo → không có vị trí.
    resp = await confirm(
        client, driver, trip, first, photo_keys=[key], latitude=DG1[0], longitude=DG1[1]
    )
    body = resp.json()
    assert body["accepted"] is False and body["latitude"] is None
    assert "Không lấy được vị trí GPS" in body["violations"]

    # Vị trí từ Zalo xa điểm giao → bị từ chối dù client khai đúng chỗ.
    resp = await confirm(
        client,
        driver,
        trip,
        first,
        photo_keys=[key],
        latitude=DG1[0],
        longitude=DG1[1],
        zalo_access_token="t",
        zalo_location_token=FAR,
    )
    body = resp.json()
    assert body["accepted"] is False and float(body["latitude"]) == 21.5
    assert any("vượt bán kính" in v for v in body["violations"])

    # Đúng chỗ: được chấp nhận, không vướng duyệt thiết bị (liên kết Zalo do admin cấp mã).
    resp = await confirm(
        client,
        driver,
        trip,
        first,
        photo_keys=[key],
        zalo_access_token="t",
        zalo_location_token=NEAR,
    )
    assert resp.json()["accepted"] is True, resp.text
    resp = await confirm(
        client,
        driver,
        trip,
        second,
        status="FAILED",
        reason="Đóng cửa",
        photo_keys=[key],
        zalo_access_token="t",
        zalo_location_token=NEAR,
    )
    assert resp.json()["accepted"] is True, resp.text
