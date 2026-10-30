import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.costing.models import DistanceSource
from app.modules.master_data.models import CostAllocationMethod


class TripCostIn(BaseModel):
    """Km thực tế: số công-tơ-mét (ưu tiên) hoặc số km; để trống → km kế hoạch / ước lượng."""

    odometer_start: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=1)
    odometer_end: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=1)
    distance_km: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    extra_cost: Decimal = Field(
        default=Decimal(0), ge=0, max_digits=14, decimal_places=0, description="Cầu đường, bến bãi…"
    )
    note: str | None = Field(default=None, max_length=500)


class AllocationOut(BaseModel):
    trip_item_id: uuid.UUID
    order_id: uuid.UUID
    external_ref: str
    customer_code: str
    customer_name: str
    weight_kg: Decimal
    value: Decimal
    basis: Decimal
    amount: Decimal


class TripCostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trip_id: uuid.UUID
    odometer_start: Decimal | None
    odometer_end: Decimal | None
    distance_km: Decimal
    distance_source: DistanceSource
    cost_per_km: Decimal
    distance_cost: Decimal
    extra_cost: Decimal
    total_cost: Decimal
    allocation_method: CostAllocationMethod
    note: str | None
    recorded_by: uuid.UUID | None
    recorded_at: datetime
    allocations: list[AllocationOut] = []
