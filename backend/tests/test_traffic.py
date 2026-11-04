"""Quy định lưu hành: phép tính khung giờ, nạp vùng, lập kế hoạch và kiểm tra lệnh theo vùng."""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import SessionFactory
from app.modules.master_data.models import RegulatoryClass, VehicleType
from app.modules.master_data.models import Vehicle as MasterVehicle
from app.modules.planning import service as planning
from app.modules.traffic import rules as tr
from app.modules.traffic import service as traffic
from app.modules.traffic.models import TrafficRule, VehicleClass, WeightBasis
from app.modules.zalo.eta import _not_before_window
from optimization import Depot, Job, Matrix, Problem, Vehicle, solve
from tests.conftest import PLAN_DATE, Env, auth, create_user, login, stop, trip_body

H = 3600


# --- Phép tính khung giờ -------------------------------------------------------------------


def test_expand_splits_windows_crossing_midnight() -> None:
    assert tr.expand([["21:00", "06:00"]]) == ((0, 6 * H), (21 * H, 24 * H))
    assert tr.expand([["09:00", "16:00"], ["19:30", "06:00"]]) == (
        (0, 6 * H),
        (9 * H, 16 * H),
        (19 * H + 1800, 24 * H),
    )


def test_intersect_and_merge() -> None:
    a = ((0, 6 * H), (9 * H, 16 * H))
    assert tr.intersect(a, ((7 * H, 19 * H),)) == ((9 * H, 16 * H),)
    assert tr.intersect(((0, 6 * H),), ((7 * H, 19 * H),)) == ()
    assert tr.merge([(1, 5), (3, 8), (10, 12)]) == ((1, 8), (10, 12))


def test_fmt_windows_joins_night() -> None:
    assert tr.fmt_windows(tr.expand([["21:00", "06:00"]])) == "21:00-06:00"
    assert (
        tr.fmt_windows(tr.expand([["09:00", "16:00"], ["19:30", "06:00"]]))
        == "09:00-16:00, 19:30-06:00"
    )
    assert tr.fmt_windows(()) == ""


def test_arrival_windows_keep_time_to_enter_and_leave() -> None:
    # Xe phải rời vùng trước 16:00: đến muộn nhất = 16:00 - giao 10' - ra 15'.
    got = tr.arrival_windows(((9 * H, 16 * H),), 900, 600)
    assert got == ((9 * H + 900, 16 * H - 1500),)
    # Mốc nửa đêm không phải cửa ra: giữ nguyên.
    assert tr.arrival_windows(((21 * H, 24 * H),), 900, 600) == ((21 * H + 900, 24 * H),)
    # Khung quá ngắn: bỏ.
    assert tr.arrival_windows(((9 * H, 9 * H + 600),), 900, 600) == ()


# --- Xếp xe vào quy tắc ---------------------------------------------------------------------


def _rules() -> list[TrafficRule]:
    data = json.loads(traffic.DEFAULT_DATA.read_text(encoding="utf-8"))["zones"][0]["rules"]
    return [
        TrafficRule(
            vehicle_class=VehicleClass(r["vehicle_class"]),
            weight_basis=WeightBasis(r["weight_basis"]),
            min_kg=Decimal(r["min_kg"]),
            max_kg=Decimal(r["max_kg"]) if r["max_kg"] else None,
            max_inclusive=r.get("max_inclusive", True),
            windows=r["windows"],
        )
        for r in data
    ]


def _windows_of(**values: Any) -> list[list[str]] | str | None:
    vehicle = MasterVehicle(vehicle_type=VehicleType.CAR, **values)
    rule = traffic._rule_for(vehicle, _rules())
    return "không có quy tắc" if rule is None else rule.windows


OFF_PEAK = [["09:00", "16:00"], ["19:30", "06:00"]]
NIGHT = [["21:00", "06:00"]]


@pytest.mark.parametrize(
    ("capacity", "expected"),
    [
        ("945", OFF_PEAK),
        ("2000", OFF_PEAK),  # đúng 2.000 kg vẫn thuộc nhóm nhỏ
        ("2000.01", NIGHT),
        ("10000", NIGHT),  # đúng 10.000 kg vẫn chạy đêm
        ("10000.01", []),  # giả định: chỉ vào khi có văn bản
    ],
)
def test_truck_classified_by_payload_not_gross(capacity: str, expected: Any) -> None:
    # Tổng trọng lượng không ảnh hưởng đến xe tải.
    got = _windows_of(capacity_kg=Decimal(capacity), gross_weight_kg=Decimal(30000))
    assert got == expected


def test_van_classified_by_gross_then_falls_back_to_truck() -> None:
    van = {"regulatory_class": RegulatoryClass.VAN, "capacity_kg": Decimal(945)}
    assert _windows_of(**van, gross_weight_kg=Decimal("3499.99")) is None
    assert _windows_of(**van, gross_weight_kg=Decimal(3500)) == OFF_PEAK
    assert _windows_of(**van) == OFF_PEAK  # chưa khai tổng trọng lượng
    big = {"regulatory_class": RegulatoryClass.VAN, "capacity_kg": Decimal(2500)}
    assert _windows_of(**big, gross_weight_kg=Decimal(4800)) == NIGHT


def test_pickup_has_no_rule() -> None:
    got = _windows_of(regulatory_class=RegulatoryClass.PICKUP, capacity_kg=Decimal(1000))
    assert got == "không có quy tắc"


# --- Bộ giải -------------------------------------------------------------------------------


def _line(n: int, km: int = 3) -> Matrix:
    dist = [[abs(i - j) * km * 1000 for j in range(n)] for i in range(n)]
    return Matrix(dist, [[d * 3600 // 30000 for d in row] for row in dist])


def _problem(jobs: list[Job], vehicles: list[Vehicle], n: int) -> Problem:
    return Problem(
        depots=[Depot("K", 0)],
        vehicles=vehicles,
        jobs=jobs,
        matrices={"car": _line(n)},
        shift_start_s=7 * H,
        shift_end_s=19 * H,
        time_limit_s=1,
    )


def test_solver_serves_within_vehicle_window_and_departs_late() -> None:
    van = Vehicle("VAN", "car", 1000, 5000, ("K",))
    window = {"VAN": ((9 * H, 15 * H),)}
    sol = solve(_problem([Job("A", 1, "K", 100, ("VAN",), 600, window)], [van], 2))
    (route,) = sol.routes
    assert route.arrivals_s == [9 * H]
    # Đi muộn để đến đúng đầu khung giờ, không rời kho từ đầu ca rồi chờ trong vùng.
    assert route.start_s == 9 * H - 360


def test_solver_prefers_vehicle_with_window_when_other_is_blocked_for_the_shift() -> None:
    van = Vehicle("VAN", "car", 1000, 5000, ("K",))
    bike = Vehicle("XM", "car", 200, 9000, ("K",))
    # VAN không có giờ vào; xe máy không giới hạn → điểm phải đi xe máy dù đắt hơn.
    job = Job("A", 1, "K", 100, ("VAN", "XM"), 600, {"VAN": ()})
    sol = solve(_problem([job], [van, bike], 2))
    assert [r.vehicle_id for r in sol.routes] == ["XM"]


def test_solver_drops_job_when_no_vehicle_has_window() -> None:
    van = Vehicle("VAN", "car", 1000, 5000, ("K",))
    sol = solve(_problem([Job("A", 1, "K", 100, ("VAN",), 600, {"VAN": ()})], [van], 2))
    assert sol.unassigned == ["A"] and sol.routes == []


def test_solver_skips_depot_vehicle_cannot_leave() -> None:
    truck = Vehicle("TAI", "car", 1000, 5000, ("K",), depot_windows={"K": ()})
    sol = solve(_problem([Job("A", 1, "K", 100, ("TAI",), 600)], [truck], 2))
    assert sol.unassigned == ["A"]


def test_solver_depot_window_limits_departure() -> None:
    van = Vehicle("VAN", "car", 1000, 5000, ("K",), depot_windows={"K": ((9 * H, 16 * H),)})
    sol = solve(_problem([Job("A", 1, "K", 100, ("VAN",), 600)], [van], 2))
    (route,) = sol.routes
    assert route.start_s >= 9 * H and route.end_s <= 16 * H


def test_packaged_data_is_a_closed_polygon_with_expected_rules() -> None:
    data = json.loads(traffic.DEFAULT_DATA.read_text(encoding="utf-8"))
    (zone,) = data["zones"]
    ring = zone["boundary"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) > 20
    trucks = {r["min_kg"]: r for r in zone["rules"] if r["vehicle_class"] == "TRUCK"}
    assert all(r["weight_basis"] == "PAYLOAD" for r in trucks.values())
    assert trucks[0]["max_kg"] == 2000 and trucks[2000]["max_kg"] == 10000
    assert trucks[2000]["windows"] == [["21:00", "06:00"]]
    (van,) = [r for r in zone["rules"] if r["vehicle_class"] == "VAN"]
    assert (van["weight_basis"], van["max_kg"], van["windows"]) == ("GROSS", 3500, None)


# --- Tích hợp: dữ liệu mẫu (Hà Nội), cả 2 kho mẫu đều nằm trong vùng -------------------------

SETTINGS = "/api/v1/company/settings"


@pytest.fixture
async def zones(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    async with SessionFactory() as session:
        assert await traffic.load_zones(session) == ["HN-NOI-DO"]
        await session.commit()
    yield
    async with owner_engine.begin() as conn:
        await conn.execute(text("TRUNCATE traffic_zones CASCADE"))


async def enable(client: AsyncClient, env: Env) -> None:
    resp = await client.put(SETTINGS, headers=auth(env.admin), json={"traffic_rules_enabled": True})
    assert resp.status_code == 200, resp.text


async def patch_vehicle(client: AsyncClient, env: Env, code: str, **values: Any) -> None:
    resp = await client.patch(
        f"/api/v1/vehicles/{env.vehicles[code]}", headers=auth(env.admin), json=values
    )
    assert resp.status_code == 200, resp.text


def dry_key(env: Env) -> tuple[str, str]:
    """Phần đơn hàng khô, nhẹ: xe nào trong dữ liệu mẫu cũng chở được."""
    return next(k for k, p in env.parts.items() if k[1] == "DRY" and float(p["weight_kg"]) <= 200)


async def plan(client: AsyncClient, env: Env) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/planning/runs", headers=auth(env.manager), json={"plan_date": PLAN_DATE}
    )
    assert resp.status_code == 202, resp.text
    run = resp.json()
    assert run["status"] == "SUCCEEDED", run
    detail: dict[str, Any] = (
        await client.get(f"/api/v1/planning/runs/{run['id']}", headers=auth(env.manager))
    ).json()
    return detail


async def check(client: AsyncClient, env: Env, trip_id: str) -> dict[str, Any]:
    resp = await client.get(f"/api/v1/trips/{trip_id}/traffic", headers=auth(env.manager))
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def add_permit(
    client: AsyncClient, env: Env, code: str, windows: list[list[str]], **extra: Any
) -> dict[str, Any]:
    (zone,) = (await client.get("/api/v1/traffic/zones", headers=auth(env.admin))).json()
    resp = await client.post(
        f"/api/v1/vehicles/{env.vehicles[code]}/permits",
        headers=auth(env.admin),
        json={
            "zone_id": zone["id"],
            "document_no": "CV-01",
            "issuer": "Công an TP",
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "windows": windows,
            **extra,
        },
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def test_rules_off_by_default_change_nothing(
    client: AsyncClient, env: Env, zones: None
) -> None:
    run = await plan(client, env)
    assert run["trips"]
    assert (await check(client, env, run["trips"][0]["id"]))["enabled"] is False


async def test_heavy_truck_never_planned_inside_zone(
    client: AsyncClient, env: Env, zones: None
) -> None:
    """Xe tải trên 2.000 kg hàng: chỉ 21:00-06:00; kho mẫu trong vùng nên không rời được trong ca"""
    await enable(client, env)
    await patch_vehicle(client, env, "XE01", capacity_kg=5000)
    await patch_vehicle(client, env, "XE02", regulatory_class="TRUCK", capacity_kg=5000)
    run = await plan(client, env)
    cars = {env.vehicles["XE01"], env.vehicles["XE02"]}
    assert not cars & {t["vehicle_id"] for t in run["trips"]}
    assert any("vùng hạn chế" in u["reason"] for u in run["unassigned"])
    for trip in run["trips"]:
        assert (await check(client, env, trip["id"]))["violations"] == []


async def test_truck_up_to_2000kg_only_between_peak_hours(
    client: AsyncClient, env: Env, zones: None
) -> None:
    await enable(client, env)
    await patch_vehicle(client, env, "XE02", is_active=False)
    run = await plan(client, env)
    trucks = [t for t in run["trips"] if t["vehicle_id"] == env.vehicles["XE01"]]
    assert trucks, run["unassigned"]
    for trip in trucks:
        result = await check(client, env, trip["id"])
        assert result["violations"] == []
        for stop_check in result["stops"]:
            if stop_check["allowed"] is not None:
                assert stop_check["ok"] and "09:00" <= stop_check["arrival"] <= "16:00"


async def test_van_under_3500kg_gross_runs_any_hour(
    client: AsyncClient, env: Env, zones: None
) -> None:
    """Dữ liệu mẫu: XE02 là xe Van, tổng trọng lượng 2.400 kg."""
    await enable(client, env)
    body = trip_body(env, "XE02", "KHO01", [stop(env, dry_key(env))])
    trip = await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    assert trip.status_code == 201, trip.text
    assert not [w for w in trip.json()["warnings"] if "giờ được hoạt động" in w]
    result = await check(client, env, trip.json()["id"])
    assert result["violations"] == [] and result["stops"][0]["allowed"] is None

    # Từ 3.500 kg không còn được miễn: tính như xe tải theo trọng tải (945 kg → ngoài giờ cao điểm).
    await patch_vehicle(client, env, "XE02", gross_weight_kg=3500)
    result = await check(client, env, trip.json()["id"])
    assert result["stops"][0]["allowed"] == "09:00-16:00, 19:30-06:00"
    assert result["violations"]


async def test_permit_opens_shift_for_heavy_truck(
    client: AsyncClient, env: Env, zones: None
) -> None:
    await enable(client, env)
    await patch_vehicle(client, env, "XE01", capacity_kg=5000)
    await patch_vehicle(client, env, "XE02", is_active=False)
    await add_permit(client, env, "XE01", [["07:00", "19:00"]])
    run = await plan(client, env)
    trucks = [t for t in run["trips"] if t["vehicle_id"] == env.vehicles["XE01"]]
    assert trucks, run["unassigned"]
    for trip in trucks:
        assert (await check(client, env, trip["id"]))["violations"] == []


async def test_expired_permit_has_no_effect(client: AsyncClient, env: Env, zones: None) -> None:
    await enable(client, env)
    await patch_vehicle(client, env, "XE01", capacity_kg=5000)
    await add_permit(
        client, env, "XE01", [["07:00", "19:00"]], valid_from="2025-01-01", valid_to="2025-12-31"
    )
    run = await plan(client, env)
    assert env.vehicles["XE01"] not in {t["vehicle_id"] for t in run["trips"]}


async def test_manual_trip_warns_and_approval_needs_reason(
    client: AsyncClient, env: Env, zones: None
) -> None:
    await enable(client, env)
    key = dry_key(env)
    resp = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json=trip_body(env, "XE01", "KHO01", [stop(env, key)], assistant_id=env.assistant_id),
    )
    assert resp.status_code == 201, resp.text
    trip = resp.json()
    assert any("ngoài giờ được hoạt động" in w for w in trip["warnings"])
    url = f"/api/v1/trips/{trip['id']}"

    denied = await client.post(f"{url}/approve", headers=auth(env.manager))
    assert denied.status_code == 400 and denied.json()["error"]["code"] == "traffic_violation"
    assert denied.json()["error"]["details"]

    ok = await client.post(
        f"{url}/approve",
        headers=auth(env.manager),
        json={"traffic_override_reason": "Có văn bản chấp thuận mới, chưa nhập"},
    )
    assert ok.status_code == 200, ok.text
    history = (await client.get(f"{url}/history", headers=auth(env.manager))).json()
    approved = next(h for h in history if h["action"] == "approved")
    assert approved["data"]["traffic_override_reason"].startswith("Có văn bản")
    assert approved["data"]["traffic_violations"]


async def test_planned_start_is_used_for_light_truck(
    client: AsyncClient, env: Env, zones: None
) -> None:
    await enable(client, env)
    key = dry_key(env)
    body = trip_body(env, "XE01", "KHO01", [stop(env, key)], assistant_id=env.assistant_id)

    late = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json={**body, "planned_start": "2026-11-02T17:00:00+07:00"},
    )
    assert late.status_code == 201, late.text
    assert any("rời kho" in w for w in late.json()["warnings"])

    ok = await client.put(
        f"/api/v1/trips/{late.json()['id']}",
        headers=auth(env.manager),
        json={**body, "planned_start": "2026-11-02T10:00:00+07:00"},
    )
    assert ok.status_code == 200, ok.text
    assert not [w for w in ok.json()["warnings"] if "giờ được hoạt động" in w]
    assert (await check(client, env, ok.json()["id"]))["departure"] == "10:00"


async def test_exempt_point_and_warehouse_are_not_limited(
    client: AsyncClient, env: Env, zones: None
) -> None:
    await enable(client, env)
    resp = await client.patch(
        f"/api/v1/warehouses/{env.warehouses['KHO01']}",
        headers=auth(env.admin),
        json={"traffic_zone_exempt": True},
    )
    assert resp.status_code == 200 and resp.json()["traffic_zone_exempt"] is True
    part = next(iter(env.parts.values()))
    customers = (await client.get("/api/v1/customers?limit=200", headers=auth(env.admin))).json()[
        "items"
    ]
    customer = next(
        c
        for c in customers
        if any(p["id"] == part["delivery_point_id"] for p in c["delivery_points"])
    )
    points = [
        {**p, "traffic_zone_exempt": p["id"] == part["delivery_point_id"]}
        for p in customer["delivery_points"]
    ]
    resp = await client.patch(
        f"/api/v1/customers/{customer['id']}",
        headers=auth(env.admin),
        json={"delivery_points": points},
    )
    assert resp.status_code == 200, resp.text
    key = dry_key(env)
    trip = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json=trip_body(env, "XE01", "KHO01", [stop(env, key)], assistant_id=env.assistant_id),
    )
    assert trip.status_code == 201, trip.text
    assert not [w for w in trip.json()["warnings"] if "giờ được hoạt động" in w]


async def test_import_vehicle_gross_weight_blank_keeps_value(client: AsyncClient, env: Env) -> None:
    head = "Mã xe,Tên xe,Biển số,Loại xe,Trọng tải (kg),Chi phí/km (đ),Kho lấy hàng"
    row = "XE01,Xe tải,29C-123.45,Ô tô,2000,9000,KHO01"

    async def send(csv: str) -> dict[str, Any]:
        resp = await client.post(
            "/api/v1/imports/vehicles",
            headers=auth(env.admin),
            files={"file": ("xe.csv", csv.encode())},
        )
        body: dict[str, Any] = resp.json()
        assert body["status"] == "SUCCEEDED", body["errors"]
        return body

    await send(f"{head},Khối lượng toàn bộ (kg),Phân loại lưu hành\n{row},2400,Xe Van\n")
    url = f"/api/v1/vehicles/{env.vehicles['XE01']}"
    vehicle = (await client.get(url, headers=auth(env.admin))).json()
    assert float(vehicle["gross_weight_kg"]) == 2400 and vehicle["regulatory_class"] == "VAN"
    await send(f"{head}\n{row}\n")
    vehicle = (await client.get(url, headers=auth(env.admin))).json()
    assert float(vehicle["gross_weight_kg"]) == 2400 and vehicle["regulatory_class"] == "VAN"


async def test_pickup_is_not_limited(client: AsyncClient, env: Env, zones: None) -> None:
    await enable(client, env)
    resp = await client.patch(
        f"/api/v1/vehicles/{env.vehicles['XE01']}",
        headers=auth(env.admin),
        json={"regulatory_class": "PICKUP"},
    )
    assert resp.status_code == 200, resp.text
    key = dry_key(env)
    trip = await client.post(
        "/api/v1/trips",
        headers=auth(env.manager),
        json=trip_body(env, "XE01", "KHO01", [stop(env, key)], assistant_id=env.assistant_id),
    )
    assert not [w for w in trip.json()["warnings"] if "giờ được hoạt động" in w]


async def test_permit_crud_and_rejects_bad_input(
    client: AsyncClient, env: Env, zones: None
) -> None:
    permit = await add_permit(client, env, "XE01", [["21:00", "06:00"]])
    url = f"/api/v1/vehicles/{env.vehicles['XE01']}/permits"
    listed = (await client.get(url, headers=auth(env.admin))).json()
    assert [p["id"] for p in listed] == [permit["id"]]

    bad = {**permit, "windows": [["25:00", "06:00"]]}
    resp = await client.put(f"{url}/{permit['id']}", headers=auth(env.admin), json=bad)
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"][0]["label"] == "Khung giờ"

    # Cùng xe khác đường dẫn: văn bản không thuộc xe này.
    other = f"/api/v1/vehicles/{env.vehicles['XE02']}/permits/{permit['id']}"
    assert (await client.delete(other, headers=auth(env.admin))).status_code == 404
    assert (
        await client.delete(f"{url}/{permit['id']}", headers=auth(env.admin))
    ).status_code == 204


async def test_driver_sees_notice_only_for_own_trip(
    client: AsyncClient, env: Env, zones: None
) -> None:
    await enable(client, env)
    key = dry_key(env)
    trip = (
        await client.post(
            "/api/v1/trips",
            headers=auth(env.manager),
            json=trip_body(env, "XE03", "KHO01", [stop(env, key)]),
        )
    ).json()
    url = f"/api/v1/driver/trips/{trip['id']}/traffic"
    # Xe máy: chưa có quy tắc nên không có khung giờ; lái xe vẫn đọc được.
    mine = await client.get(url, headers=auth(env.driver_token))
    assert mine.status_code == 200 and mine.json()["violations"] == []
    other = await create_user(client, env.admin, "laixe2", ["driver"])
    assert other
    token = await login(client, "laixe2", "password-123")
    assert (await client.get(url, headers=auth(token))).status_code == 403


def test_eta_waits_for_window() -> None:
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    early = datetime(2026, 11, 2, 7, 30, tzinfo=tz)
    windows = ((9 * H, 16 * H),)
    assert _not_before_window(early, windows, tz) == datetime(2026, 11, 2, 9, 0, tzinfo=tz)
    inside = datetime(2026, 11, 2, 10, 0, tzinfo=tz)
    assert _not_before_window(inside, windows, tz) == inside
    # Trễ khỏi khung: không có khung nào sau đó, giữ nguyên giờ tính được.
    late = datetime(2026, 11, 2, 17, 0, tzinfo=tz)
    assert _not_before_window(late, windows, tz) == late


async def test_restricted_matrix_avoids_zone_only_between_outside_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = Matrix([[0, 10, 20], [10, 0, 30], [20, 30, 0]], [[0, 1, 2], [1, 0, 3], [2, 3, 0]])
    avoid = Matrix([[0, 11, 90], [11, 0, 91], [90, 91, 0]], [[0, 5, 9], [5, 0, 8], [9, 8, 0]])

    async def fake(*_: Any, **__: Any) -> tuple[Matrix, str]:
        return avoid, "osrm"

    monkeypatch.setattr(planning.routing, "matrix", fake)
    # Điểm 1 trong vùng: chỉ đoạn 0-2 đi tuyến tránh vùng.
    got = await planning._restricted_matrix([(0, 0), (0, 1), (0, 2)], {1}, 1.0, plain)
    assert got is not None
    assert got.distance_m == [[0, 10, 90], [10, 0, 30], [90, 30, 0]]
    assert got.duration_s == [[0, 1, 9], [1, 0, 3], [9, 3, 0]]


async def test_restricted_matrix_none_when_osrm_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(*_: Any, **__: Any) -> tuple[Matrix, str]:
        return Matrix([[0]], [[0]]), "estimate"

    monkeypatch.setattr(planning.routing, "matrix", fake)
    assert await planning._restricted_matrix([(0, 0)], set(), 1.0, Matrix([[0]], [[0]])) is None


async def test_outside_depot_does_not_hide_stop_only_reachable_after_shift(
    client: AsyncClient, env: Env, zones: None
) -> None:
    """Kho ngoài vùng, xe tải trên 2.000 kg hàng: trong ca không được coi là "chờ đến 21:00"."""
    await enable(client, env)
    await patch_vehicle(client, env, "XE01", capacity_kg=5000)
    resp = await client.patch(
        f"/api/v1/warehouses/{env.warehouses['KHO01']}",
        headers=auth(env.admin),
        json={"traffic_zone_exempt": True},
    )
    assert resp.status_code == 200
    body = trip_body(env, "XE01", "KHO01", [stop(env, dry_key(env))], assistant_id=env.assistant_id)
    day = await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    assert day.status_code == 201, day.text
    assert any("ngoài giờ được hoạt động" in w for w in day.json()["warnings"])

    # Xuất phát đêm là hợp lệ theo quy định.
    night = await client.put(
        f"/api/v1/trips/{day.json()['id']}",
        headers=auth(env.manager),
        json={**body, "planned_start": "2026-11-02T22:00:00+07:00"},
    )
    assert night.status_code == 200, night.text
    assert not [w for w in night.json()["warnings"] if "giờ được hoạt động" in w]
