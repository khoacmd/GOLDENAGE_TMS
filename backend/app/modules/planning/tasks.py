"""Đưa lần lập kế hoạch vào hàng đợi worker (Dramatiq), hoặc chạy ngay khi `tasks_eager`."""

import uuid

from app.core.config import get_settings
from app.modules.planning.service import process_run


async def enqueue_run(run_id: uuid.UUID, company_id: uuid.UUID) -> None:
    if get_settings().tasks_eager:
        await process_run(run_id, company_id)
        return
    from worker.tasks import plan_run

    plan_run.send(str(run_id), str(company_id))
