import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.dispatch.schemas import TripSummaryOut
from app.modules.orders.models import TempGroup
from app.modules.planning.models import RunStatus, RunTrigger


class RunCreate(BaseModel):
    plan_date: date
    replace_drafts: bool = Field(
        default=True, description="Hủy các lệnh nháp lập tự động trước đó của ngày rồi lập lại"
    )


class UnassignedPart(BaseModel):
    order_part_id: uuid.UUID
    order_id: uuid.UUID
    external_ref: str
    customer_code: str
    customer_name: str
    temp_group: TempGroup
    weight_kg: float
    requested_date: date
    reason: str


class RunSummary(BaseModel):
    parts_total: int = 0
    parts_assigned: int = 0
    trips: int = 0
    stops: int = 0
    weight_kg: float = 0
    utilization: float = 0
    distance_km: float = 0
    cost: float = 0
    solve_seconds: float = 0
    total_seconds: float = 0


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_date: date
    trigger: RunTrigger
    status: RunStatus
    replace_drafts: bool
    requested_by: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    distance_source: str | None
    summary: RunSummary
    unassigned: list[UnassignedPart]
    warnings: list[str]
    error: str | None


class CurrentCost(BaseModel):
    """Chi phí hiện tại của các lệnh do lần chạy sinh ra (sau khi quản lý chỉnh tay)."""

    trips: int
    distance_km: float
    cost: float


class RunDetailOut(RunOut):
    trips: list[TripSummaryOut]
    current: CurrentCost


class MoveStopIn(BaseModel):
    """Chuyển 1 điểm dừng (mọi phần đơn tại điểm giao đó) sang lệnh khác."""

    from_trip_id: uuid.UUID
    stop_id: uuid.UUID
    to_trip_id: uuid.UUID
    position: int | None = Field(default=None, ge=0, description="Vị trí mới (mặc định: cuối)")


class MoveStopOut(BaseModel):
    trips: list[TripSummaryOut]
    warnings: list[str]
