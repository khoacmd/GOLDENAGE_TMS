import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import AliasPath, BaseModel, ConfigDict, Field

from app.modules.orders.models import OrderPartStatus, OrderSource, OrderStatus, TempGroup


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OrderLineOut(_Out):
    line_no: int
    product_id: uuid.UUID
    product_code: str = Field(validation_alias=AliasPath("product", "code"))
    product_name: str = Field(validation_alias=AliasPath("product", "name"))
    uom: str = Field(validation_alias=AliasPath("product", "uom"))
    qty: Decimal
    weight_kg: Decimal
    amount: Decimal | None
    temp_group: TempGroup


class OrderPartOut(_Out):
    id: uuid.UUID
    temp_group: TempGroup
    weight_kg: Decimal
    value: Decimal
    status: OrderPartStatus
    attempt_count: int


class OrderOut(_Out):
    id: uuid.UUID
    external_ref: str
    customer_id: uuid.UUID
    customer_code: str = Field(validation_alias=AliasPath("customer", "code"))
    customer_name: str = Field(validation_alias=AliasPath("customer", "name"))
    delivery_point_id: uuid.UUID
    delivery_point_code: str = Field(validation_alias=AliasPath("delivery_point", "code"))
    delivery_address: str = Field(validation_alias=AliasPath("delivery_point", "address"))
    order_date: date
    requested_date: date
    order_value: Decimal
    note: str | None
    status: OrderStatus
    source: OrderSource
    created_at: datetime
    parts: list[OrderPartOut]


class OrderDetailOut(OrderOut):
    lines: list[OrderLineOut]
