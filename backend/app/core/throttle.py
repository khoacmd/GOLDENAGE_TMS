"""Chống dò mật khẩu: đếm lần đăng nhập sai theo tài khoản và theo IP trong một cửa sổ thời gian.

Lưu ở Redis (dùng chung giữa các tiến trình API); Redis lỗi → đếm trong bộ nhớ tiến trình.
"""

import logging
import time

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.errors import AppError

log = logging.getLogger(__name__)
PREFIX = "tms:login:"
_memory: dict[str, tuple[int, float]] = {}  # key → (số lần sai, hết hạn lúc)


class TooManyAttemptsError(AppError):
    status_code = 429
    code = "too_many_attempts"


def _keys(username: str, ip: str | None) -> list[tuple[str, int]]:
    settings = get_settings()
    keys = [(f"{PREFIX}user:{username.strip().lower()}", settings.login_max_failures)]
    if ip:
        keys.append((f"{PREFIX}ip:{ip}", settings.login_ip_max_failures))
    return keys


async def _counts(keys: list[str]) -> list[int]:
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            return [int(v or 0) for v in await r.mget(keys)]
    except aioredis.RedisError:
        now = time.monotonic()
        entries = [_memory.get(k, (0, 0.0)) for k in keys]
        return [count if expires > now else 0 for count, expires in entries]


async def check(username: str, ip: str | None) -> None:
    keys = _keys(username, ip)
    counts = await _counts([k for k, _ in keys])
    if any(count >= limit for count, (_, limit) in zip(counts, keys, strict=True)):
        minutes = get_settings().login_window_s // 60
        raise TooManyAttemptsError(
            f"Đăng nhập sai quá nhiều lần, vui lòng thử lại sau {minutes} phút"
        )


async def failed(username: str, ip: str | None) -> None:
    window = get_settings().login_window_s
    keys = [k for k, _ in _keys(username, ip)]
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            pipe = r.pipeline(transaction=False)
            for k in keys:
                pipe.incr(k)
                pipe.expire(k, window, nx=True)
            await pipe.execute()
    except aioredis.RedisError:
        now = time.monotonic()
        for k in keys:
            count, expires = _memory.get(k, (0, 0.0))
            _memory[k] = (count + 1, expires) if expires > now else (1, now + window)
    log.warning("Đăng nhập sai: user=%s ip=%s", username, ip)


async def succeeded(username: str) -> None:
    key = _keys(username, None)[0][0]
    _memory.pop(key, None)
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            await r.delete(key)
    except aioredis.RedisError:
        pass


async def clear() -> None:
    """Xóa toàn bộ bộ đếm (dùng cho test)."""
    _memory.clear()
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            keys = [k async for k in r.scan_iter(f"{PREFIX}*")]
            if keys:
                await r.delete(*keys)
    except aioredis.RedisError:
        pass
