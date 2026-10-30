import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import CurrentUser, ManagerOrAdminDep, require_roles
from app.core.db import DbSession
from app.modules.dispatch import service as dispatch
from app.modules.dispatch.router import summary_out
from app.modules.identity.models import CompanyRole
from app.modules.planning import service
from app.modules.planning.models import RunTrigger
from app.modules.planning.schemas import (
    CurrentCost,
    MoveStopIn,
    MoveStopOut,
    RunCreate,
    RunDetailOut,
    RunOut,
)
from app.modules.planning.tasks import enqueue_run

router = APIRouter(prefix="/planning", tags=["planning"])

ManagerDep = Annotated[CurrentUser, Depends(require_roles(CompanyRole.MANAGER))]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_run(body: RunCreate, user: ManagerDep, session: DbSession) -> RunOut:
    """Lập kế hoạch tự động (chạy nền); theo dõi kết quả qua GET /planning/runs/{id}."""
    run = await service.create_run(
        session, user.cid, body.plan_date, RunTrigger.MANUAL, user.id, body.replace_drafts
    )
    await session.commit()
    await enqueue_run(run.id, user.cid)
    session.expunge_all()
    return RunOut.model_validate(await service.get_run(session, run.id))


@router.get("/runs")
async def list_runs(
    _: ManagerOrAdminDep,
    session: DbSession,
    plan_date: Annotated[date | None, Query()] = None,
) -> list[RunOut]:
    return [RunOut.model_validate(r) for r in await service.list_runs(session, plan_date)]


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, _: ManagerOrAdminDep, session: DbSession) -> RunDetailOut:
    run = await service.get_run(session, run_id)
    trips = await service.run_trips(session, run_id)
    km, cost = await service.current_cost(trips)
    return RunDetailOut.model_validate(
        {
            **RunOut.model_validate(run).model_dump(),
            "trips": [summary_out(t) for t in trips],
            "current": CurrentCost(trips=len(trips), distance_km=km, cost=cost),
        }
    )


@router.post("/move-stop")
async def move_stop(body: MoveStopIn, user: ManagerDep, session: DbSession) -> MoveStopOut:
    """Kéo thả: chuyển điểm dừng sang lệnh khác hoặc đổi thứ tự trong lệnh."""
    trips, warnings = await service.move_stop(
        session,
        user.cid,
        body.from_trip_id,
        body.stop_id,
        body.to_trip_id,
        body.position,
        user.id,
    )
    await session.commit()
    ids = [t.id for t in trips]
    session.expunge_all()
    return MoveStopOut(
        trips=[summary_out(await dispatch.get_trip(session, i)) for i in ids], warnings=warnings
    )
