import uuid
from datetime import date

from pydantic import BaseModel


class Totals(BaseModel):
    trips: int = 0
    trips_closed: int = 0
    trips_without_cost: int = (
        0  # chuyến chưa ghi nhận chi phí (km tạm tính theo kế hoạch/ước lượng)
    )
    items_success: int = 0
    items_failed: int = 0
    items_cancelled: int = 0
    success_rate: float | None = None
    redeliveries: int = 0  # lượt giao lại phần đơn từng giao thất bại
    orders: int = 0  # đơn có hàng giao (thành công hoặc thất bại)
    delivered_kg: float = 0
    distance_km: float = 0
    cost: float = 0
    load_utilization: float | None = None  # khối lượng chở / trọng tải các chuyến
    # Tính trên các chuyến đã ghi nhận chi phí.
    cost_per_order: float | None = None
    cost_per_kg: float | None = None


class VehicleRow(Totals):
    vehicle_id: uuid.UUID
    vehicle_code: str
    vehicle_name: str


class DayRow(Totals):
    plan_date: date


class CustomerRow(BaseModel):
    customer_id: uuid.UUID
    customer_code: str
    customer_name: str
    orders: int
    items_success: int
    items_failed: int
    delivered_kg: float
    cost: float
    cost_per_kg: float | None


class ReasonRow(BaseModel):
    reason: str
    count: int


class ReportOut(BaseModel):
    date_from: date
    date_to: date
    totals: Totals
    by_vehicle: list[VehicleRow]
    by_day: list[DayRow]
    by_customer: list[CustomerRow]
    failure_reasons: list[ReasonRow]
