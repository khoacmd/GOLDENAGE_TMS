import pytest
from httpx import AsyncClient

from app.modules.planning import service as planning
from optimization import Job, Problem, Solution, solve
from tests.conftest import PLAN_DATE, Env, auth

KHO, GAN, XA = (21.0, 105.8), (21.03, 105.8), (21.1, 105.8)  # ~3,3 km và ~11 km về phía bắc


def test_prefer_motorbikes_within_radius() -> None:
    jobs = [
        Job("gan", 1, "K1", 100, ("CAR", "BIKE")),
        Job("xa", 2, "K1", 100, ("CAR", "BIKE")),
        Job("chi-o-to", 1, "K1", 100, ("CAR",)),
    ]
    out = planning.prefer_motorbikes(jobs, [KHO, GAN, XA], {"K1": 0}, {"BIKE"}, 5, 100_000)
    assert [j.vehicle_costs for j in out] == [{"CAR": 100_000}, {}, {}]
    # Bán kính 0 = tắt.
    assert planning.prefer_motorbikes(jobs, [KHO, GAN, XA], {"K1": 0}, {"BIKE"}, 0, 1) == jobs


async def test_planning_applies_motorbike_radius(
    client: AsyncClient, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems: list[Problem] = []

    def capture(problem: Problem) -> Solution:
        problems.append(problem)
        return solve(problem)

    monkeypatch.setattr(planning, "solve", capture)

    async def plan() -> Problem:
        resp = await client.post(
            "/api/v1/planning/runs",
            headers=auth(env.manager),
            json={"plan_date": PLAN_DATE, "replace_drafts": True},
        )
        assert resp.json()["status"] == "SUCCEEDED", resp.text
        return problems[-1]

    problem = await plan()
    bikes = {env.vehicles["XE03"], env.vehicles["XE04"]}
    preferred = [j for j in problem.jobs if j.vehicle_costs]
    assert preferred, "dữ liệu mẫu phải có điểm trong 5 km quanh kho"
    for j in preferred:
        assert set(j.vehicle_costs) == set(j.vehicle_ids) - bikes
        assert set(j.vehicle_costs.values()) == {100_000}

    resp = await client.put(
        "/api/v1/company/settings",
        headers=auth(env.admin),
        json={"motorbike_priority_radius_km": 0},
    )
    assert resp.status_code == 200, resp.text
    assert not any(j.vehicle_costs for j in (await plan()).jobs)
