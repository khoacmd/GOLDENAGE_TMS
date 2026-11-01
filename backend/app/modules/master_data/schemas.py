import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.parsing import Phone
from app.modules.master_data.models import (
    CargoClass,
    CostAllocationMethod,
    TempClass,
    VehicleRequirement,
    VehicleType,
)
from app.modules.zalo.schemas import ZaloLinkInfo

CodeStr = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._/-]+$")]
Latitude = Annotated[Decimal, Field(ge=-90, le=90, max_digits=9, decimal_places=6)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180, max_digits=9, decimal_places=6)]
Weekday = Annotated[int, Field(ge=1, le=7)]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Kho ---------------------------------------------------------------------------


class WarehouseCreate(BaseModel):
    code: CodeStr
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    latitude: Latitude
    longitude: Longitude
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    is_active: bool | None = None


class WarehouseOut(_Out):
    id: uuid.UUID
    code: str
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    is_active: bool


# --- Xe ------------------------------------------------------------------------------


class VehicleCreate(BaseModel):
    code: CodeStr
    name: str = Field(min_length=1, max_length=255)
    plate_no: str = Field(min_length=1, max_length=20)
    vehicle_type: VehicleType
    capacity_kg: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    cost_per_km: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    requires_assistant: bool = False
    cargo_class: CargoClass = CargoClass.ANY
    cost_allocation_method: CostAllocationMethod = CostAllocationMethod.WEIGHT
    warehouse_ids: list[uuid.UUID] = Field(min_length=1)
    is_active: bool = True


class VehicleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    plate_no: str | None = Field(default=None, min_length=1, max_length=20)
    vehicle_type: VehicleType | None = None
    capacity_kg: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    cost_per_km: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    requires_assistant: bool | None = None
    cargo_class: CargoClass | None = None
    cost_allocation_method: CostAllocationMethod | None = None
    warehouse_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class VehicleOut(_Out):
    id: uuid.UUID
    code: str
    name: str
    plate_no: str
    vehicle_type: VehicleType
    capacity_kg: Decimal
    cost_per_km: Decimal
    requires_assistant: bool
    cargo_class: CargoClass
    cost_allocation_method: CostAllocationMethod
    warehouse_ids: list[uuid.UUID]
    is_active: bool


# --- Khách hàng & điểm giao --------------------------------------------------------------


class DeliveryPointIn(BaseModel):
    code: CodeStr
    name: str | None = Field(default=None, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    latitude: Latitude
    longitude: Longitude
    is_default: bool = False
    is_active: bool = True


class DeliveryPointOut(_Out):
    id: uuid.UUID
    code: str
    name: str | None
    address: str
    latitude: Decimal
    longitude: Decimal
    is_default: bool
    is_active: bool


class _CustomerFields(BaseModel):
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    sales_rep: str | None = Field(default=None, max_length=255)


class CustomerCreate(_CustomerFields):
    code: CodeStr
    name: str = Field(min_length=1, max_length=255)
    required_vehicle_type: VehicleRequirement = VehicleRequirement.ANY
    delivery_weekdays: list[Weekday] = []
    deliveries_per_week: int | None = Field(default=None, ge=1, le=7)
    is_active: bool = True
    delivery_points: list[DeliveryPointIn] = Field(min_length=1)


class CustomerUpdate(_CustomerFields):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    required_vehicle_type: VehicleRequirement | None = None
    delivery_weekdays: list[Weekday] | None = None
    deliveries_per_week: int | None = Field(default=None, ge=1, le=7)
    is_active: bool | None = None
    # Danh sách đầy đủ: upsert theo mã, điểm không còn trong danh sách bị ngưng hoạt động.
    delivery_points: list[DeliveryPointIn] | None = Field(default=None, min_length=1)


class CustomerContactIn(BaseModel):
    # Trống = liên hệ chủ (xem mọi đơn + giá trị); có = liên hệ của điểm giao đó.
    delivery_point_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    phone: Phone
    note: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class CustomerContactOut(_Out):
    id: uuid.UUID
    customer_id: uuid.UUID
    delivery_point_id: uuid.UUID | None
    delivery_point_code: str | None
    name: str
    phone: str
    note: str | None
    is_active: bool
    zalo: ZaloLinkInfo = Field(default_factory=ZaloLinkInfo)


class CustomerOut(_Out):
    id: uuid.UUID
    code: str
    name: str
    address: str | None
    contact_name: str | None
    phone: str | None
    email: str | None
    required_vehicle_type: VehicleRequirement
    sales_rep: str | None
    delivery_weekdays: list[int]
    deliveries_per_week: int | None
    is_active: bool
    delivery_points: list[DeliveryPointOut]


# --- Mặt hàng ----------------------------------------------------------------------------


class ProductCreate(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=64)]
    name: str = Field(min_length=1, max_length=255)
    temp_class: TempClass
    uom: str = Field(min_length=1, max_length=32)
    weight_kg: Decimal = Field(ge=0, max_digits=10, decimal_places=3)
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    temp_class: TempClass | None = None
    uom: str | None = Field(default=None, min_length=1, max_length=32)
    weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=3)
    is_active: bool | None = None


class ProductOut(_Out):
    id: uuid.UUID
    code: str
    name: str
    temp_class: TempClass
    uom: str
    weight_kg: Decimal
    is_active: bool
