import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AliasPath, BaseModel, ConfigDict, Field, model_validator

from app.modules.dispatch.models import ItemStatus, TripDeliveryStatus, TripOrderStatus, TripSource
from app.modules.master_data.models import VehicleRequirement
from app.modules.orders.models import OrderPartStatus, TempGroup

Lat = Annotated[Decimal, Field(ge=-90, le=90, max_digits=9, decimal_places=6)]
Lng = Annotated[Decimal, Field(ge=-180, le=180, max_digits=9, decimal_places=6)]


class AdhocItemIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    weight_kg: Decimal = Field(default=Decimal(0), ge=0)


class StopIn(BaseModel):
    """Điểm dừng: điểm giao của khách (kèm phần đơn) hoặc điểm tự do (nhập địa chỉ/tọa độ)."""

    delivery_point_id: uuid.UUID | None = None
    order_part_ids: list[uuid.UUID] = []
    name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    latitude: Lat | None = None
    longitude: Lng | None = None
    adhoc_items: list[AdhocItemIn] = []
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check(self) -> "StopIn":
        if self.delivery_point_id is None:
            if self.order_part_ids:
                raise ValueError("Điểm dừng có đơn hàng phải gắn điểm giao")
            if not (self.address and self.latitude is not None and self.longitude is not None):
                raise ValueError("Điểm tự do cần địa chỉ và tọa độ")
        if not self.order_part_ids and not self.adhoc_items:
            raise ValueError("Điểm dừng phải có ít nhất 1 đơn hoặc 1 mục hàng")
        return self


class TripIn(BaseModel):
    plan_date: date
    vehicle_id: uuid.UUID
    warehouse_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    assistant_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=1000)
    stops: list[StopIn] = Field(min_length=1)


class CancelIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ItemUpdateIn(BaseModel):
    status: ItemStatus
    reason: str | None = Field(default=None, max_length=500)
    delivered_at: datetime | None = None


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AvailablePartOut(_Out):
    """Phần đơn đang chờ xếp lệnh (PENDING hoặc giao thất bại trước đó)."""

    id: uuid.UUID
    temp_group: TempGroup
    weight_kg: Decimal
    value: Decimal
    status: OrderPartStatus
    attempt_count: int
    order_id: uuid.UUID
    external_ref: str = Field(validation_alias=AliasPath("order", "external_ref"))
    requested_date: date = Field(validation_alias=AliasPath("order", "requested_date"))
    customer_code: str = Field(validation_alias=AliasPath("order", "customer", "code"))
    customer_name: str = Field(validation_alias=AliasPath("order", "customer", "name"))
    required_vehicle_type: VehicleRequirement = Field(
        validation_alias=AliasPath("order", "customer", "required_vehicle_type")
    )
    delivery_point_id: uuid.UUID = Field(validation_alias=AliasPath("order", "delivery_point_id"))
    delivery_point_code: str = Field(validation_alias=AliasPath("order", "delivery_point", "code"))
    address: str = Field(validation_alias=AliasPath("order", "delivery_point", "address"))
    latitude: Decimal = Field(validation_alias=AliasPath("order", "delivery_point", "latitude"))
    longitude: Decimal = Field(validation_alias=AliasPath("order", "delivery_point", "longitude"))


class TripItemOut(_Out):
    id: uuid.UUID
    order_part_id: uuid.UUID | None
    description: str | None
    weight_kg: Decimal
    value: Decimal
    status: ItemStatus
    reason: str | None
    delivered_at: datetime | None
    is_manual_update: bool
    temp_group: TempGroup | None = Field(
        default=None, validation_alias=AliasPath("order_part", "temp_group")
    )
    external_ref: str | None = Field(
        default=None, validation_alias=AliasPath("order_part", "order", "external_ref")
    )


class TripStopOut(_Out):
    id: uuid.UUID
    seq: int
    delivery_point_id: uuid.UUID | None
    customer_code: str | None = None
    customer_name: str | None = None
    name: str | None
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    note: str | None
    items: list[TripItemOut]


class PersonOut(_Out):
    id: uuid.UUID
    full_name: str
    phone: str | None


class TripSummaryOut(_Out):
    id: uuid.UUID
    code: str
    plan_date: date
    trip_seq: int
    source: TripSource
    order_status: TripOrderStatus
    delivery_status: TripDeliveryStatus
    vehicle_id: uuid.UUID
    vehicle_code: str = Field(validation_alias=AliasPath("vehicle", "code"))
    vehicle_name: str = Field(validation_alias=AliasPath("vehicle", "name"))
    capacity_kg: Decimal = Field(validation_alias=AliasPath("vehicle", "capacity_kg"))
    warehouse_id: uuid.UUID
    warehouse_code: str = Field(validation_alias=AliasPath("warehouse", "code"))
    driver: PersonOut | None
    assistant: PersonOut | None
    total_weight_kg: Decimal
    total_value: Decimal
    stop_count: int = 0
    item_counts: dict[ItemStatus, int] = {}
    note: str | None


class TripOut(TripSummaryOut):
    warehouse_name: str = Field(validation_alias=AliasPath("warehouse", "name"))
    warehouse_latitude: Decimal = Field(validation_alias=AliasPath("warehouse", "latitude"))
    warehouse_longitude: Decimal = Field(validation_alias=AliasPath("warehouse", "longitude"))
    approved_at: datetime | None
    picked_at: datetime | None
    dispatched_at: datetime | None
    finished_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    stops: list[TripStopOut]
    warnings: list[str] = []


class PickingLineOut(BaseModel):
    product_code: str
    product_name: str
    uom: str
    temp_group: TempGroup
    qty: Decimal
    weight_kg: Decimal


class PickingListOut(BaseModel):
    trip: TripSummaryOut
    lines: list[PickingLineOut]
    adhoc_items: list[str]


class AuditOut(_Out):
    action: str
    data: dict[str, object]
    user_id: uuid.UUID | None
    created_at: datetime
