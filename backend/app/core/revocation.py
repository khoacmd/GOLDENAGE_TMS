"""Thu hồi token khi đăng xuất: lưu `jti` vào danh sách chặn đến lúc token hết hạn.

Lưu ở Redis (dùng chung giữa các tiến trình API); Redis lỗi → lưu trong bộ nhớ tiến trình.
"""

import time
from datetime import UTC, datetime

import redis.asyncio as aioredis

from app.core.config import get_settings

PREFIX = "tms:revoked:"
_memory: dict[str, float] = {}  # jti → hết hạn lúc (epoch)


async def revoke(jti: str, expires_at: datetime) -> None:
    ttl = int(expires_at.timestamp() - datetime.now(UTC).timestamp()) + 1
    if ttl <= 0:
        return
    _memory[jti] = time.time() + ttl
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            await r.set(f"{PREFIX}{jti}", 1, ex=ttl)
    except aioredis.RedisError:
        pass


async def is_revoked(jti: str | None) -> bool:
    if jti is None:
        return False
    expires = _memory.get(jti)
    if expires is not None and expires > time.time():
        return True
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            return bool(await r.exists(f"{PREFIX}{jti}"))
    except aioredis.RedisError:
        return False


async def clear() -> None:
    """Xóa toàn bộ danh sách chặn (dùng cho test)."""
    _memory.clear()
    try:
        async with aioredis.from_url(get_settings().redis_url) as r:
            keys = [k async for k in r.scan_iter(f"{PREFIX}*")]
            if keys:
                await r.delete(*keys)
    except aioredis.RedisError:
        pass
