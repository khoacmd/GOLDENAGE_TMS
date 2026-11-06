import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.parsing import Phone
from app.modules.master_data.models import (
    CargoClass,
    CostAllocationMethod,
    RegulatoryClass,
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
    traffic_zone_exempt: bool = False


class WarehouseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    is_active: bool | None = None
    traffic_zone_exempt: bool | None = None


class WarehouseOut(_Out):
    id: uuid.UUID
    code: str
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    is_active: bool
    traffic_zone_exempt: bool


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
    gross_weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    regulatory_class: RegulatoryClass | None = None


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
    gross_weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    regulatory_class: RegulatoryClass | None = None


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
    gross_weight_kg: Decimal | None
    regulatory_class: RegulatoryClass | None


# --- Khách hàng & điểm giao --------------------------------------------------------------


class DeliveryPointIn(BaseModel):
    code: CodeStr
    name: str | None = Field(default=None, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    latitude: Latitude
    longitude: Longitude
    is_default: bool = False
    is_active: bool = True
    # None = giữ nguyên (mới tạo: không miễn), để lần import sau không xóa dấu quản lý đã đặt.
    traffic_zone_exempt: bool | None = None


class DeliveryPointOut(_Out):
    id: uuid.UUID
    code: str
    name: str | None
    address: str
    latitude: Decimal
    longitude: Decimal
    is_default: bool
    is_active: bool
    traffic_zone_exempt: bool


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


class CustomerLocation(BaseModel):
    """1 điểm giao trên bản đồ khách hàng."""

    customer_id: uuid.UUID
    customer_code: str
    customer_name: str
    customer_active: bool
    point_id: uuid.UUID
    point_code: str
    point_name: str | None
    address: str
    latitude: Decimal
    longitude: Decimal
    is_default: bool


class CustomerLocations(BaseModel):
    items: list[CustomerLocation]
    # Quá giới hạn số điểm: chỉ trả phần đầu, web báo người dùng lọc bớt.
    truncated: bool


# --- Mặt hàng ----------------------------------------------------------------------------


SkuRatio = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)]


def sku_conversion_error(
    uom: str, sku_uom: str, sku_ratio: Decimal, uom_ratio: Decimal
) -> str | None:
    if sku_uom.casefold() == uom.casefold() and sku_ratio != uom_ratio:
        return f"SKU trùng đơn vị tính '{uom}' thì quy đổi phải là 1 = 1"
    return None


class ProductCreate(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=64)]
    name: str = Field(min_length=1, max_length=255)
    temp_class: TempClass
    uom: str = Field(min_length=1, max_length=32)
    weight_kg: Decimal = Field(ge=0, max_digits=10, decimal_places=3)
    sku_uom: str = Field(min_length=1, max_length=32)
    sku_ratio: SkuRatio = Decimal(1)
    uom_ratio: SkuRatio = Decimal(1)
    factory: str | None = Field(default=None, max_length=128)
    product_group: str | None = Field(default=None, max_length=128)
    is_active: bool = True

    @model_validator(mode="after")
    def _sku_conversion(self) -> "ProductCreate":
        error = sku_conversion_error(self.uom, self.sku_uom, self.sku_ratio, self.uom_ratio)
        if error:
            raise ValueError(error)
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    temp_class: TempClass | None = None
    uom: str | None = Field(default=None, min_length=1, max_length=32)
    weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=3)
    sku_uom: str | None = Field(default=None, min_length=1, max_length=32)
    sku_ratio: SkuRatio | None = None
    uom_ratio: SkuRatio | None = None
    factory: str | None = Field(default=None, max_length=128)
    product_group: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None

    @model_validator(mode="after")
    def _sku_not_null(self) -> "ProductUpdate":
        for field in ("sku_uom", "sku_ratio", "uom_ratio"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("Đơn vị SKU và quy đổi không được để trống")
        return self


class ProductAttributes(BaseModel):
    factories: list[str]
    product_groups: list[str]


class ProductOut(_Out):
    id: uuid.UUID
    code: str
    name: str
    temp_class: TempClass
    uom: str
    weight_kg: Decimal
    sku_uom: str
    sku_ratio: Decimal
    uom_ratio: Decimal
    factory: str | None
    product_group: str | None
    is_active: bool
