"""Kiểm tra mỗi phút: công ty nào đến giờ lập kế hoạch tự động thì đưa vào hàng đợi."""

import asyncio
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core import observability
from app.core.db import engine
from app.modules.planning.service import create_due_runs
from worker.tasks import plan_run

log = logging.getLogger("worker.scheduler")


def check_due() -> None:
    async def main() -> list[tuple[object, object]]:
        try:
            return list(await create_due_runs())
        finally:
            await engine.dispose()

    for run_id, company_id in asyncio.run(main()):
        log.info("Lập kế hoạch tự động: run %s (công ty %s)", run_id, company_id)
        plan_run.send(str(run_id), str(company_id))


def main() -> None:
    observability.setup("scheduler")
    scheduler = BlockingScheduler()
    scheduler.add_job(check_due, "interval", minutes=1, max_instances=1, coalesce=True)
    log.info("Scheduler lập kế hoạch đã chạy")
    scheduler.start()


if __name__ == "__main__":
    main()
