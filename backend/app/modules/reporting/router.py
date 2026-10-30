import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.core.auth import ManagerOrAdminDep
from app.core.db import DbSession
from app.modules.reporting import service
from app.modules.reporting.schemas import ReportOut

router = APIRouter(prefix="/reports", tags=["reports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DateFrom = Annotated[date, Query(description="Từ ngày giao (gồm)")]
DateTo = Annotated[date, Query(description="Đến ngày giao (gồm)")]
OptionalId = Annotated[uuid.UUID | None, Query()]


@router.get("/summary")
async def summary(
    _: ManagerOrAdminDep,
    session: DbSession,
    date_from: DateFrom,
    date_to: DateTo,
    vehicle_id: OptionalId = None,
    warehouse_id: OptionalId = None,
) -> ReportOut:
    data = await service.build(session, date_from, date_to, vehicle_id, warehouse_id)
    return data.report


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}, "description": "File Excel báo cáo"}},
)
async def export(
    _: ManagerOrAdminDep,
    session: DbSession,
    date_from: DateFrom,
    date_to: DateTo,
    vehicle_id: OptionalId = None,
    warehouse_id: OptionalId = None,
) -> Response:
    data = await service.build(session, date_from, date_to, vehicle_id, warehouse_id)
    name = f"bao-cao-giao-hang_{date_from:%Y%m%d}-{date_to:%Y%m%d}.xlsx"
    return Response(
        service.to_excel(data),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
