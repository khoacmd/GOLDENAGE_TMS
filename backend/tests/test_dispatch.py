from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import auth, login

PLAN_DATE = "2026-11-02"  # Thứ 2, ngày giao của đơn mẫu
SAMPLES = Path(__file__).parents[2] / "docs" / "samples"
KINDS = ["warehouses", "vehicles", "products", "customers", "inventory", "orders"]


@dataclass
class Env:
    admin: str
    manager: str
    keeper: str
    driver_token: str
    driver_id: str
    assistant_id: str
    vehicles: dict[str, str]
    warehouses: dict[str, str]
    parts: dict[tuple[str, str], dict[str, Any]]  # (số đơn, DRY/COLD) → phần đơn


async def _user(client: AsyncClient, admin: str, username: str, roles: list[str]) -> str:
    resp = await client.post(
        "/api/v1/users",
        headers=auth(admin),
        json={
            "username": username,
            "full_name": username,
            "password": "password-123",
            "roles": roles,
        },
    )
    assert resp.status_code == 201, resp.text
    user_id: str = resp.json()["id"]
    return user_id


@pytest.fixture
async def env(client: AsyncClient, admin_token: str) -> Env:
    for path, kind in zip(sorted(SAMPLES.glob("*.csv")), KINDS, strict=True):
        resp = await client.post(
            f"/api/v1/imports/{kind}",
            headers=auth(admin_token),
            files={"file": (path.name, path.read_bytes())},
        )
        assert resp.json()["status"] == "SUCCEEDED", resp.json()["errors"]
    await _user(client, admin_token, "quanly", ["manager"])
    await _user(client, admin_token, "thukho", ["warehouse_keeper"])
    driver_id = await _user(client, admin_token, "laixe1", ["driver"])
    assistant_id = await _user(client, admin_token, "phuxe1", ["driver"])
    manager = await login(client, "quanly", "password-123")
    vehicles = (await client.get("/api/v1/vehicles", headers=auth(manager))).json()["items"]
    warehouses = (await client.get("/api/v1/warehouses", headers=auth(manager))).json()["items"]
    parts = (
        await client.get(
            f"/api/v1/trips/available-parts?plan_date={PLAN_DATE}", headers=auth(manager)
        )
    ).json()
    return Env(
        admin=admin_token,
        manager=manager,
        keeper=await login(client, "thukho", "password-123"),
        driver_token=await login(client, "laixe1", "password-123"),
        driver_id=driver_id,
        assistant_id=assistant_id,
        vehicles={v["code"]: v["id"] for v in vehicles},
        warehouses={w["code"]: w["id"] for w in warehouses},
        parts={(p["external_ref"], p["temp_group"]): p for p in parts},
    )


def stop(env: Env, *keys: tuple[str, str]) -> dict[str, Any]:
    parts = [env.parts[k] for k in keys]
    return {
        "delivery_point_id": parts[0]["delivery_point_id"],
        "order_part_ids": [p["id"] for p in parts],
    }


def trip_body(
    env: Env, vehicle: str, warehouse: str, stops: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {
        "plan_date": PLAN_DATE,
        "vehicle_id": env.vehicles[vehicle],
        "warehouse_id": env.warehouses[warehouse],
        "driver_id": env.driver_id,
        "stops": stops,
        **extra,
    }


async def test_available_parts(env: Env) -> None:
    assert len(env.parts) == 12  # 8 đơn, 4 đơn có cả phần khô và lạnh/đông
    part = env.parts[("DH2610-001", "COLD")]
    assert (part["customer_code"], part["delivery_point_code"]) == ("KH001", "DG1")


async def test_create_trip_and_parts_become_planned(client: AsyncClient, env: Env) -> None:
    body = trip_body(
        env,
        "XE02",
        "KHO01",
        [
            stop(env, ("DH2610-001", "COLD"), ("DH2610-001", "DRY")),
            stop(env, ("DH2610-007", "DRY")),
        ],
    )
    resp = await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    assert resp.status_code == 201, resp.text
    trip = resp.json()
    assert trip["code"] == "L261102-01"
    assert (trip["order_status"], trip["trip_seq"], trip["stop_count"]) == ("DRAFT", 1, 2)
    assert float(trip["total_weight_kg"]) == pytest.approx(111 + 184 + 92)
    assert trip["stops"][0]["customer_code"] == "KH001"
    assert trip["warnings"] == []

    remaining = (
        await client.get(
            f"/api/v1/trips/available-parts?plan_date={PLAN_DATE}", headers=auth(env.manager)
        )
    ).json()
    assert len(remaining) == 9

    # Phần đơn đã xếp không được xếp vào lệnh khác.
    resp = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json=trip_body(env, "XE02", "KHO01", [stop(env, ("DH2610-007", "DRY"))]),
    )
    assert resp.json()["error"]["code"] == "invalid_trip"
    assert "đã được xếp lệnh khác" in resp.json()["error"]["details"][0]

    # Lượt thứ 2 của cùng xe trong ngày.
    resp = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json=trip_body(env, "XE02", "KHO01", [stop(env, ("DH2610-006", "DRY"))]),
    )
    assert resp.json()["trip_seq"] == 2


async def test_constraint_errors(client: AsyncClient, env: Env) -> None:
    # Xe máy chỉ chở hàng khô, 250 kg; KH003 yêu cầu ô tô; đơn 004 nặng 724 kg.
    body = trip_body(
        env,
        "XE03",
        "KHO01",
        [
            stop(env, ("DH2610-001", "COLD")),
            stop(env, ("DH2610-004", "DRY")),
        ],
    )
    resp = await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    details = resp.json()["error"]["details"]
    assert any("không chở hàng lạnh/đông" in d for d in details)
    assert any("yêu cầu ô tô" in d for d in details)
    assert any("vượt trọng tải" in d for d in details)

    # Xe tải yêu cầu phụ xe; xe máy XE04 không được lấy hàng ở KHO01.
    resp = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json=trip_body(env, "XE01", "KHO01", [stop(env, ("DH2610-004", "DRY"))]),
    )
    assert "Xe XE01 yêu cầu phụ xe" in resp.json()["error"]["details"]
    resp = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json=trip_body(env, "XE04", "KHO01", [stop(env, ("DH2610-008", "DRY"))]),
    )
    assert "không được lấy hàng tại kho" in resp.json()["error"]["details"][0]

    # Phần đơn phải giao đúng điểm dừng.
    wrong = {
        "delivery_point_id": env.parts[("DH2610-003", "DRY")]["delivery_point_id"],
        "order_part_ids": [env.parts[("DH2610-008", "DRY")]["id"]],
    }
    resp = await client.post(
        "/api/v1/trips", headers=auth(env.manager), json=trip_body(env, "XE02", "KHO01", [wrong])
    )
    assert any("không giao tới điểm dừng 1" in d for d in resp.json()["error"]["details"])


async def test_stock_warning(client: AsyncClient, env: Env) -> None:
    # KHO02 không có SUA-TT-1L (đơn 004 cần 30 thùng).
    body = trip_body(
        env, "XE01", "KHO02", [stop(env, ("DH2610-004", "DRY"))], assistant_id=env.assistant_id
    )
    resp = await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    assert resp.status_code == 201, resp.text
    assert any("Tồn kho không đủ SUA-TT-1L" in w for w in resp.json()["warnings"])


async def test_full_lifecycle(client: AsyncClient, env: Env) -> None:
    body = trip_body(
        env,
        "XE02",
        "KHO01",
        [
            stop(env, ("DH2610-001", "COLD"), ("DH2610-001", "DRY")),
            stop(env, ("DH2610-002", "DRY")),
            stop(env, ("DH2610-007", "DRY")),
        ],
        driver_id=None,
    )
    trip = (await client.post("/api/v1/trips", headers=auth(env.manager), json=body)).json()
    tid = trip["id"]
    url = f"/api/v1/trips/{tid}"

    # Chưa có lái xe → chưa duyệt được; thủ kho chưa xuất được lệnh nháp.
    resp = await client.post(f"{url}/approve", headers=auth(env.manager))
    assert resp.json()["error"]["code"] == "driver_required"
    assert (await client.post(f"{url}/pick", headers=auth(env.keeper))).json()["error"][
        "code"
    ] == "invalid_status"

    body["driver_id"] = env.driver_id
    await client.put(url, headers=auth(env.manager), json=body)
    assert (await client.post(f"{url}/approve", headers=auth(env.manager))).json()[
        "order_status"
    ] == "APPROVED"

    # Sửa lệnh đã duyệt → quay về nháp, phải duyệt lại.
    edited = (await client.put(url, headers=auth(env.manager), json=body)).json()
    assert edited["order_status"] == "DRAFT"
    await client.post(f"{url}/approve", headers=auth(env.manager))

    # Quản lý không có quyền xuất kho; thủ kho xác nhận.
    assert (await client.post(f"{url}/pick", headers=auth(env.manager))).status_code == 403
    picking = (await client.get(f"{url}/picking-list", headers=auth(env.keeper))).json()
    assert {line["product_code"] for line in picking["lines"]} == {
        "SUA-TT-180",
        "SUA-CHUA-100",
        "KEM-QUE-60",
        "NUOC-SUOI-500",
    }
    assert (await client.post(f"{url}/pick", headers=auth(env.keeper))).json()[
        "order_status"
    ] == "PICKED"
    trip = (await client.post(f"{url}/dispatch", headers=auth(env.driver_token))).json()
    assert (trip["order_status"], trip["delivery_status"]) == ("DISPATCHED", "IN_PROGRESS")

    items = {
        (i["external_ref"], i["temp_group"]): i["id"] for s in trip["stops"] for i in s["items"]
    }

    async def set_item(key: tuple[str, str], status: str, reason: str | None = None) -> Any:
        return await client.patch(
            f"{url}/items/{items[key]}",
            headers=auth(env.manager),
            json={"status": status, "reason": reason},
        )

    assert (await set_item(("DH2610-001", "COLD"), "SUCCESS")).status_code == 200
    assert (await set_item(("DH2610-001", "DRY"), "SUCCESS")).status_code == 200
    resp = await set_item(("DH2610-002", "DRY"), "FAILED")
    assert resp.json()["error"]["code"] == "reason_required"
    await set_item(("DH2610-002", "DRY"), "FAILED", "Khách đóng cửa")

    # Chưa giao hết → chưa kết thúc được.
    resp = await client.post(f"{url}/close", headers=auth(env.manager))
    assert resp.json()["error"]["code"] == "trip_not_finished"
    await set_item(("DH2610-007", "DRY"), "CANCELLED", "Khách hoãn")

    trip = (await client.get(url, headers=auth(env.manager))).json()
    assert trip["delivery_status"] == "FINISHED"
    assert trip["item_counts"] == {"SUCCESS": 2, "FAILED": 1, "CANCELLED": 1}
    closed = (await client.post(f"{url}/close", headers=auth(env.manager))).json()
    assert closed["order_status"] == "CLOSED"

    # Đơn 001 giao đủ → hoàn thành; đơn 002 thất bại và 007 bị hủy → quay lại hàng chờ.
    orders = {
        o["external_ref"]: o
        for o in (await client.get("/api/v1/orders", headers=auth(env.manager))).json()["items"]
    }
    assert orders["DH2610-001"]["status"] == "COMPLETED"
    pool = {
        (p["external_ref"], p["status"], p["attempt_count"])
        for p in (
            await client.get(
                f"/api/v1/trips/available-parts?plan_date={PLAN_DATE}", headers=auth(env.manager)
            )
        ).json()
    }
    assert ("DH2610-002", "FAILED", 1) in pool
    assert ("DH2610-007", "PENDING", 0) in pool

    history = (await client.get(f"{url}/history", headers=auth(env.manager))).json()
    assert [h["action"] for h in history][:4] == [
        "created",
        "updated",
        "approved",
        "updated_reopened",
    ]
    assert history[-1]["action"] == "closed"


async def test_cancel_releases_parts(client: AsyncClient, env: Env) -> None:
    trip = (
        await client.post(
            "/api/v1/trips",
            headers=auth(env.manager),
            json=trip_body(env, "XE02", "KHO01", [stop(env, ("DH2610-007", "DRY"))]),
        )
    ).json()
    resp = await client.post(
        f"/api/v1/trips/{trip['id']}/cancel", headers=auth(env.manager), json={"reason": "Đổi xe"}
    )
    assert resp.json()["order_status"] == "CANCELLED"
    pool = (
        await client.get(
            f"/api/v1/trips/available-parts?plan_date={PLAN_DATE}", headers=auth(env.manager)
        )
    ).json()
    assert len(pool) == 12


async def test_adhoc_trip_without_orders(client: AsyncClient, env: Env) -> None:
    body = trip_body(
        env,
        "XE02",
        "KHO02",
        [
            {
                "name": "Hội chợ triển lãm",
                "address": "Giảng Võ, Ba Đình",
                "latitude": "21.0287",
                "longitude": "105.8150",
                "adhoc_items": [{"description": "Vật phẩm trưng bày", "weight_kg": "120"}],
            }
        ],
    )
    resp = await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    assert resp.status_code == 201, resp.text
    trip = resp.json()
    assert trip["stops"][0]["items"][0]["description"] == "Vật phẩm trưng bày"
    assert float(trip["total_weight_kg"]) == 120

    resp = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json=trip_body(
            env, "XE02", "KHO02", [{"name": "Thiếu tọa độ", "adhoc_items": [{"description": "x"}]}]
        ),
    )
    assert resp.status_code == 422


async def test_driver_cannot_plan_and_staff_listing(client: AsyncClient, env: Env) -> None:
    body = trip_body(env, "XE02", "KHO01", [stop(env, ("DH2610-007", "DRY"))])
    assert (
        await client.post("/api/v1/trips", headers=auth(env.driver_token), json=body)
    ).status_code == 403
    drivers = (await client.get("/api/v1/staff?role=driver", headers=auth(env.manager))).json()
    assert {d["username"] for d in drivers} == {"laixe1", "phuxe1"}
