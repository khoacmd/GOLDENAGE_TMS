"""Ma trận khoảng cách/thời gian giữa các điểm: OSRM tự host (có cache Redis) hoặc ước lượng.

Ước lượng (khi chưa dựng OSRM hoặc OSRM lỗi): đường chim bay x hệ số đường vòng, tốc độ trung bình
nội đô theo loại xe.
"""

import logging
import math
from enum import StrEnum

import httpx
import redis.asyncio as aioredis

from app.core.config import get_settings
from optimization import Matrix

log = logging.getLogger(__name__)

type Point = tuple[float, float]  # (vĩ độ, kinh độ)

EARTH_RADIUS_M = 6_371_000
DETOUR_FACTOR = 1.35
SPEED_KMH = {"car": 22.0, "motorbike": 25.0}
CACHE_TTL_S = 30 * 24 * 3600
OSRM_TIMEOUT_S = 30


class Profile(StrEnum):
    CAR = "car"
    MOTORBIKE = "motorbike"


def haversine_m(a: Point, b: Point) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def estimate(points: list[Point], profile: Profile) -> Matrix:
    mps = SPEED_KMH[profile] * 1000 / 3600
    dist = [[round(haversine_m(a, b) * DETOUR_FACTOR) for b in points] for a in points]
    return Matrix(distance_m=dist, duration_s=[[round(d / mps) for d in row] for row in dist])


def _osrm_url(profile: Profile) -> str | None:
    settings = get_settings()
    return settings.osrm_car_url if profile == Profile.CAR else settings.osrm_motorbike_url


def _key(profile: Profile, a: Point, b: Point) -> str:
    return f"tms:dist:{profile}:{a[0]:.5f},{a[1]:.5f}:{b[0]:.5f},{b[1]:.5f}"


async def _cached(profile: Profile, points: list[Point]) -> Matrix | None:
    keys = [_key(profile, a, b) for a in points for b in points]
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            values = await r.mget(keys)
    except aioredis.RedisError:
        return None
    if any(v is None for v in values):
        return None
    n = len(points)
    pairs = [
        tuple(int(x) for x in str(v, "ascii").split(",")) for v in values if isinstance(v, bytes)
    ]
    return Matrix(
        distance_m=[[pairs[i * n + j][0] for j in range(n)] for i in range(n)],
        duration_s=[[pairs[i * n + j][1] for j in range(n)] for i in range(n)],
    )


async def _store(profile: Profile, points: list[Point], m: Matrix) -> None:
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            pipe = r.pipeline(transaction=False)
            for i, a in enumerate(points):
                for j, b in enumerate(points):
                    value = f"{m.distance_m[i][j]},{m.duration_s[i][j]}"
                    pipe.set(_key(profile, a, b), value, ex=CACHE_TTL_S)
            await pipe.execute()
    except aioredis.RedisError:
        log.warning("Không ghi được cache khoảng cách")


async def _osrm_table(url: str, points: list[Point]) -> Matrix:
    coords = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)
    async with httpx.AsyncClient(timeout=OSRM_TIMEOUT_S) as client:
        resp = await client.get(
            f"{url.rstrip('/')}/table/v1/driving/{coords}",
            params={"annotations": "distance,duration"},
        )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != "Ok":
        raise RuntimeError(f"OSRM: {body.get('code')} {body.get('message', '')}")
    # Cặp điểm không nối được đường (null) → coi như rất xa để bộ giải tránh.
    far = 10**7
    return Matrix(
        distance_m=[[round(d) if d is not None else far for d in row] for row in body["distances"]],
        duration_s=[[round(d) if d is not None else far for d in row] for row in body["durations"]],
    )


async def matrix(points: list[Point], profile: Profile) -> tuple[Matrix, str]:
    """Trả (ma trận, nguồn: "osrm" | "cache" | "estimate")."""
    url = _osrm_url(profile)
    if not url or len(points) < 2:
        return estimate(points, profile), "estimate"
    if (hit := await _cached(profile, points)) is not None:
        return hit, "cache"
    try:
        result = await _osrm_table(url, points)
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as e:
        log.warning("OSRM %s lỗi, dùng ước lượng: %s", profile, e)
        return estimate(points, profile), "estimate"
    await _store(profile, points, result)
    return result, "osrm"


async def route_distance_m(points: list[Point], profile: Profile) -> int:
    """Tổng quãng đường đi lần lượt qua `points` (dùng để tính lại chi phí sau khi chỉnh tay)."""
    if len(points) < 2:
        return 0
    m, _ = await matrix(points, profile)
    return sum(m.distance_m[i][i + 1] for i in range(len(points) - 1))
