from typing import Any

import httpx
import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient

from app.core.config import get_settings
from app.modules.routing import service as routing
from app.modules.routing.service import Profile
from optimization import Matrix
from tests.conftest import Env, auth, stop, trip_body

POINTS = [(21.0285, 105.8522), (21.0300, 105.7650)]


@pytest.fixture
def no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: Any, **__: Any) -> None:
        raise aioredis.ConnectionError("không có redis")

    monkeypatch.setattr(routing.aioredis, "from_url", fail)


@pytest.fixture
def osrm(monkeypatch: pytest.MonkeyPatch, no_redis: None) -> None:
    monkeypatch.setattr(get_settings(), "osrm_car_url", "http://osrm.test")


async def test_estimate_without_osrm() -> None:
    m, source = await routing.matrix(POINTS, Profile.CAR)
    assert source == "estimate"
    assert m.distance_m[0][1] == round(routing.haversine_m(*POINTS) * routing.DETOUR_FACTOR)


async def test_osrm_durations_scaled_for_traffic(
    osrm: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def table(_: str, points: list[Any]) -> Matrix:
        return Matrix(distance_m=[[0, 11400], [11400, 0]], duration_s=[[0, 930], [940, 0]])

    monkeypatch.setattr(routing, "_osrm_table", table)
    m, source = await routing.matrix(POINTS, Profile.CAR)
    factor = get_settings().osrm_duration_factor
    assert source == "osrm"
    assert m.distance_m[0][1] == 11400
    assert m.duration_s[0][1] == round(930 * factor)


def _mock_osrm(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    real = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(routing.httpx, "AsyncClient", client)


async def test_geometry_from_osrm(osrm: None, monkeypatch: pytest.MonkeyPatch) -> None:
    line = [[105.8522, 21.0285], [105.81, 21.03], [105.765, 21.03]]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/route/v1/driving/105.852200,21.028500;")
        return httpx.Response(
            200, json={"code": "Ok", "routes": [{"geometry": {"coordinates": line}}]}
        )

    _mock_osrm(monkeypatch, handler)
    assert await routing.geometry(POINTS, Profile.CAR) == [tuple(c) for c in line]


async def test_geometry_none_when_osrm_fails(osrm: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_osrm(monkeypatch, lambda _: httpx.Response(500))
    assert await routing.geometry(POINTS, Profile.CAR) is None
    assert await routing.geometry(POINTS, Profile.MOTORBIKE) is None  # chưa cấu hình


async def test_trip_route_falls_back_to_straight_lines(client: AsyncClient, env: Env) -> None:
    body = trip_body(env, "XE02", "KHO01", [stop(env, ("DH2610-007", "DRY"))])
    trip = (await client.post("/api/v1/trips", headers=auth(env.manager), json=body)).json()
    resp = await client.get(f"/api/v1/trips/{trip['id']}/route", headers=auth(env.manager))
    assert resp.status_code == 200, resp.text
    route = resp.json()
    assert route["road"] is False
    assert len(route["coordinates"]) == 3  # kho → điểm dừng → kho
    assert route["coordinates"][0] == route["coordinates"][-1]
