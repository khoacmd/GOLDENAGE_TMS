import asyncio
import uuid
from collections.abc import Awaitable, Callable

import dramatiq

from app.core.db import engine
from app.modules.planning.service import process_run
from worker import broker as _broker  # noqa: F401 - cấu hình broker trước khi khai báo actor


def run_async(coro_fn: Callable[..., Awaitable[None]], *args: object) -> None:
    """Mỗi message chạy trong event loop riêng → giải phóng pool kết nối sau khi xong."""

    async def main() -> None:
        try:
            await coro_fn(*args)
        finally:
            await engine.dispose()

    asyncio.run(main())


# Bộ giải có thể chạy lâu; không tự thử lại (lần chạy lỗi được ghi FAILED để quản lý xem).
@dramatiq.actor(queue_name="planning", max_retries=0, time_limit=30 * 60 * 1000)
def plan_run(run_id: str, company_id: str) -> None:
    run_async(process_run, uuid.UUID(run_id), uuid.UUID(company_id))
