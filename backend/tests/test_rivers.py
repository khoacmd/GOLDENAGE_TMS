import pytest
from httpx import AsyncClient

from app.modules.planning import service as planning
from app.modules.rivers import geometry
from app.modules.rivers import service as rivers
from optimization import Problem, Solution, solve
from tests.conftest import PLAN_DATE, Env, auth

HOAN_KIEM, GIA_LAM, LONG_BIEN = (21.028, 105.852), (21.03, 105.93), (21.047, 105.888)
HA_DONG, DONG_ANH = (20.97, 105.77), (21.13, 105.85)


def hong() -> geometry.River:
    (river,) = rivers.rivers()
    bridges = [
        geometry.Bridge("Cầu Long Biên", (21.04613, 105.8657), 200_000),
        geometry.Bridge("Cầu Vĩnh Tuy", (21.00349, 105.8752), 1_000_000),
    ]
    return geometry.River(river.name, river.path, bridges)


def test_side_of_red_river() -> None:
    river = hong()
    left = {geometry.side(p, river.path) for p in (HOAN_KIEM, HA_DONG)}
    right = {geometry.side(p, river.path) for p in (GIA_LAM, LONG_BIEN, DONG_ANH)}
    assert len(left) == len(right) == 1 and left != right and None not in left | right
    # Ngoài 2 đầu đường tâm sông thì không xét bờ.
    assert geometry.side((23.0, 103.0), river.path) is None


def test_crossing_prefers_cheaper_bridge() -> None:
    river = hong()
    assert geometry.crossing(HOAN_KIEM, HA_DONG, river, 2000) is None
    found = geometry.crossing((21.0, 105.86), (21.0, 105.90), river, 2000)
    # Vĩnh Tuy gần hơn nhưng bị phạt nặng: chọn Long Biên, cộng chi phí đi vòng.
    assert found is not None and found.bridge == "Cầu Long Biên"
    assert 200_000 < found.cost < 1_000_000
    matrix = geometry.penalty_matrix([HOAN_KIEM, GIA_LAM, HA_DONG], [river], 2000)
    assert matrix[0][2] == matrix[2][0] == 0
    assert matrix[0][1] == matrix[1][0] >= 200_000


async def test_bridge_catalog_crud(client: AsyncClient, env: Env) -> None:
    resp = await client.get("/api/v1/rivers", headers=auth(env.manager))
    assert [r["code"] for r in resp.json()] == ["SONG_HONG"]

    resp = await client.post("/api/v1/river-bridges/load-defaults", headers=auth(env.manager))
    assert resp.status_code == 403
    resp = await client.post("/api/v1/river-bridges/load-defaults", headers=auth(env.admin))
    assert resp.json() == {"created": 6}
    resp = await client.post("/api/v1/river-bridges/load-defaults", headers=auth(env.admin))
    assert resp.json() == {"created": 0}

    bridges = (await client.get("/api/v1/river-bridges", headers=auth(env.manager))).json()
    vinh_tuy = next(b for b in bridges if b["code"] == "VINH_TUY")
    body = {**vinh_tuy, "motorbike_penalty": 5_000_000, "is_active": False}
    resp = await client.put(
        f"/api/v1/river-bridges/{vinh_tuy['id']}", headers=auth(env.admin), json=body
    )
    assert resp.status_code == 200 and resp.json()["motorbike_penalty"] == 5_000_000

    resp = await client.post(
        "/api/v1/river-bridges", headers=auth(env.admin), json={**body, "code": "vinh_tuy"}
    )
    assert resp.status_code == 409
    resp = await client.post(
        "/api/v1/river-bridges",
        headers=auth(env.admin),
        json={**body, "code": "X1", "river_code": "SONG_DA"},
    )
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_river"

    resp = await client.delete(f"/api/v1/river-bridges/{vinh_tuy['id']}", headers=auth(env.admin))
    assert resp.status_code == 204
    assert len((await client.get("/api/v1/river-bridges", headers=auth(env.admin))).json()) == 5


async def test_planning_penalizes_motorbike_crossings(
    client: AsyncClient, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems: list[Problem] = []

    def capture(problem: Problem) -> Solution:
        problems.append(problem)
        return solve(problem)

    monkeypatch.setattr(planning, "solve", capture)
    await client.post("/api/v1/river-bridges/load-defaults", headers=auth(env.admin))
    resp = await client.post(
        "/api/v1/planning/runs", headers=auth(env.manager), json={"plan_date": PLAN_DATE}
    )
    assert resp.json()["status"] == "SUCCEEDED", resp.text
    (problem,) = problems
    keys = {v.id: v.penalty for v in problem.vehicles}
    xe01, xe03, xe04 = (env.vehicles[c] for c in ("XE01", "XE03", "XE04"))
    assert keys[xe01] is None and keys[xe03] == keys[xe04] is not None
    matrix = problem.penalties[str(keys[xe03])]
    # Kho Hà Đông (vị trí 0) và kho Long Biên (vị trí 1) ở 2 bờ sông Hồng.
    depots = {d.id: d.location for d in problem.depots}
    hd, lb = depots[env.warehouses["KHO01"]], depots[env.warehouses["KHO02"]]
    assert matrix[hd][lb] == matrix[lb][hd] >= 200_000
    assert matrix[hd][hd] == 0
