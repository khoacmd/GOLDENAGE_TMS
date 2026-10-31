from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient

from app.modules.planning import service as planning
from app.modules.routing import service as routing
from tests.conftest import PLAN_DATE, Env, auth


async def plan(client: AsyncClient, env: Env, **body: Any) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/planning/runs", headers=auth(env.manager), json={"plan_date": PLAN_DATE, **body}
    )
    assert resp.status_code == 202, resp.text
    run = resp.json()
    assert run["status"] == "SUCCEEDED", run
    detail: dict[str, Any] = (
        await client.get(f"/api/v1/planning/runs/{run['id']}", headers=auth(env.manager))
    ).json()
    return detail


async def test_auto_plan_assigns_every_part_or_explains(client: AsyncClient, env: Env) -> None:
    run = await plan(client, env)
    summary = run["summary"]
    assert summary["parts_total"] == len(env.parts)
    assert summary["parts_assigned"] + len(run["unassigned"]) == len(env.parts)
    assert summary["trips"] == len(run["trips"]) > 0
    assert all(u["reason"] for u in run["unassigned"])
    assert run["distance_source"] == "estimate"

    vehicles = (await client.get("/api/v1/vehicles", headers=auth(env.manager))).json()["items"]
    capacity = {v["id"]: float(v["capacity_kg"]) for v in vehicles}
    for trip in run["trips"]:
        assert trip["source"] == "AUTO" and trip["order_status"] == "DRAFT"
        assert float(trip["total_weight_kg"]) <= capacity[trip["vehicle_id"]]
        assert trip["planning_run_id"] == run["id"]
        assert float(trip["planned_distance_km"]) > 0 and trip["planned_start"]
    # Mọi phần đơn đã xếp không còn trong danh sách chờ.
    left = (
        await client.get(
            f"/api/v1/trips/available-parts?plan_date={PLAN_DATE}", headers=auth(env.manager)
        )
    ).json()
    assert {p["id"] for p in left} == {u["order_part_id"] for u in run["unassigned"]}
    assert run["current"]["distance_km"] == pytest.approx(summary["distance_km"], rel=0.01)


async def test_rerun_replaces_auto_drafts(client: AsyncClient, env: Env) -> None:
    first = await plan(client, env)
    second = await plan(client, env)
    assert second["summary"]["parts_assigned"] == first["summary"]["parts_assigned"]
    trips = (
        await client.get(f"/api/v1/trips?plan_date={PLAN_DATE}", headers=auth(env.manager))
    ).json()
    active = [t for t in trips if t["order_status"] != "CANCELLED"]
    assert {t["id"] for t in active} == {t["id"] for t in second["trips"]}


async def test_unassigned_reasons_when_no_cold_vehicle(client: AsyncClient, env: Env) -> None:
    for code in ("XE01", "XE02"):  # chỉ 2 ô tô chở được hàng lạnh/đông
        await client.patch(
            f"/api/v1/vehicles/{env.vehicles[code]}",
            headers=auth(env.admin),
            json={"is_active": False},
        )
    run = await plan(client, env)
    cold = [u for u in run["unassigned"] if u["temp_group"] == "COLD"]
    assert cold and all(u["reason"] == "Không có xe chở hàng lạnh/đông" for u in cold)
    assert run["warnings"][0].endswith("cần xử lý thủ công")


async def test_move_stop_between_trips_and_approve_rules(client: AsyncClient, env: Env) -> None:
    await client.put(
        "/api/v1/company/settings", headers=auth(env.admin), json={"max_trips_per_vehicle": 1}
    )
    run = await plan(client, env)
    trips = sorted(run["trips"], key=lambda t: float(t["total_weight_kg"]))
    assert len(trips) >= 2
    small, big = trips[0], trips[-1]
    detail = (await client.get(f"/api/v1/trips/{small['id']}", headers=auth(env.manager))).json()
    stop_id = detail["stops"][0]["id"]
    resp = await client.post(
        "/api/v1/planning/move-stop",
        headers=auth(env.manager),
        json={"from_trip_id": small["id"], "stop_id": stop_id, "to_trip_id": big["id"]},
    )
    if resp.status_code == 400:  # vượt tải / không tương thích → không thay đổi gì
        after = await client.get(f"/api/v1/trips/{small['id']}", headers=auth(env.manager))
        assert after.json()["stops"][0]["id"] == stop_id
    else:
        assert resp.status_code == 200, resp.text
        moved = {t["id"]: t for t in resp.json()["trips"]}
        assert big["id"] in moved
        assert moved[big["id"]]["stop_count"] >= big["stop_count"]

    # Lệnh tự động chưa có lái xe → không duyệt được.
    resp = await client.post(f"/api/v1/trips/{big['id']}/approve", headers=auth(env.manager))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "driver_required"


async def test_planning_permissions(client: AsyncClient, env: Env) -> None:
    body = {"plan_date": PLAN_DATE}
    assert (
        await client.post("/api/v1/planning/runs", headers=auth(env.driver_token), json=body)
    ).status_code == 403
    assert (
        await client.post("/api/v1/planning/runs", headers=auth(env.admin), json=body)
    ).status_code == 403
    assert (await client.get("/api/v1/planning/runs", headers=auth(env.admin))).status_code == 200


async def test_scheduled_run_once_per_day(
    client: AsyncClient, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await client.put(
        "/api/v1/company/settings",
        headers=auth(env.admin),
        json={"auto_plan_enabled": True, "cutover_time": "17:00:00"},
    )
    # Thứ 7 31/10/2026 18:00 giờ VN → ngày làm việc kế tiếp là Thứ 2 02/11 (bỏ Chủ nhật).
    monkeypatch.setattr(planning, "now", lambda: datetime(2026, 10, 31, 11, 0, tzinfo=UTC))
    created = await planning.create_due_runs()
    assert len(created) == 1
    assert await planning.create_due_runs() == []
    run_id, company_id = created[0]
    await planning.process_run(run_id, company_id)
    runs = (await client.get("/api/v1/planning/runs", headers=auth(env.manager))).json()
    assert runs[0]["trigger"] == "SCHEDULED" and runs[0]["plan_date"] == PLAN_DATE
    assert runs[0]["status"] == "SUCCEEDED"

    # Trước giờ cut-over thì chưa lập.
    monkeypatch.setattr(planning, "now", lambda: datetime(2026, 11, 2, 3, 0, tzinfo=UTC))
    assert await planning.create_due_runs() == []


async def test_failed_delivery_is_replanned(client: AsyncClient, env: Env) -> None:
    from tests.test_delivery import dispatched_trip, item_ids

    trip = await dispatched_trip(client, env)
    failed = item_ids(trip)[0]
    resp = await client.patch(
        f"/api/v1/trips/{trip['id']}/items/{failed}",
        headers=auth(env.manager),
        json={"status": "FAILED", "reason": "Khách vắng nhà"},
    )
    assert resp.status_code == 200, resp.text
    part_id = resp.json()["order_part_id"]
    run = await plan(client, env)
    planned = {
        i["order_part_id"]
        for t in run["trips"]
        for s in (await client.get(f"/api/v1/trips/{t['id']}", headers=auth(env.manager))).json()[
            "stops"
        ]
        for i in s["items"]
    }
    assert part_id in planned


async def test_move_stop_rejects_other_warehouse(client: AsyncClient, env: Env) -> None:
    run = await plan(client, env)
    by_wh: dict[str, list[dict[str, Any]]] = {}
    for t in run["trips"]:
        by_wh.setdefault(t["warehouse_id"], []).append(t)
    if len(by_wh) < 2:
        pytest.skip("Dữ liệu mẫu chỉ sinh chuyến ở 1 kho")
    a, b = (group[0] for group in list(by_wh.values())[:2])
    detail = (await client.get(f"/api/v1/trips/{a['id']}", headers=auth(env.manager))).json()
    resp = await client.post(
        "/api/v1/planning/move-stop",
        headers=auth(env.manager),
        json={"from_trip_id": a["id"], "stop_id": detail["stops"][0]["id"], "to_trip_id": b["id"]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "different_warehouse"


async def test_travel_time_factor_is_company_setting(
    client: AsyncClient, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    resp = await client.put(
        "/api/v1/company/settings", headers=auth(env.admin), json={"travel_time_factor": 9}
    )
    assert resp.status_code == 422
    resp = await client.put(
        "/api/v1/company/settings", headers=auth(env.admin), json={"travel_time_factor": 2.5}
    )
    assert resp.json()["travel_time_factor"] == 2.5

    factors: list[float] = []
    real = routing.matrix

    async def spy(points: Any, profile: Any, duration_factor: float = 1.0) -> Any:
        factors.append(duration_factor)
        return await real(points, profile, duration_factor)

    monkeypatch.setattr(routing, "matrix", spy)
    monkeypatch.setattr(planning, "current_cost", _no_cost)  # chỉ đo quãng đường, bỏ qua
    await plan(client, env)
    assert factors and set(factors) == {2.5}


async def _no_cost(trips: Any) -> tuple[float, float]:
    return 0.0, 0.0
