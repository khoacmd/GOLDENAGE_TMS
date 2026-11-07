"""Lỗi kiểm tra dữ liệu đầu vào (422): chỉ rõ trường nào sai và sai gì, bằng tiếng Việt.

Trả về `{"error": {"code": "validation_error", "message", "details": ["Nhãn: lý do"],
"fields": [{"path": [...], "label", "message"}]}}`; không trả lại giá trị đã nhập (có thể là mật
khẩu). `path` khớp tên trường trong form để web hiện lỗi ngay dưới ô nhập.
"""

import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic_core import ErrorDetails

log = logging.getLogger(__name__)

SUMMARY = "Dữ liệu chưa hợp lệ"

# Tên trường trong body / query → nhãn. Trường mới phải thêm vào đây
# (test_validation_errors.py kiểm tra đủ theo OpenAPI).
FIELD_LABELS = {
    "access_token": "Token truy cập",
    "accuracy_m": "Độ chính xác vị trí",
    "activation_code_ttl_days": "Hạn mã kích hoạt",
    "active": "Trạng thái hoạt động",
    "address": "Địa chỉ",
    "adhoc_items": "Mục hàng tự do",
    "admin": "Admin công ty",
    "app_version": "Phiên bản ứng dụng",
    "assistant_id": "Phụ xe",
    "auto_plan_enabled": "Tự động lập kế hoạch",
    "capacity_kg": "Trọng tải",
    "gross_weight_kg": "Khối lượng toàn bộ",
    "regulatory_class": "Phân loại lưu hành",
    "traffic_zone_exempt": "Miễn vùng hạn chế",
    "traffic_rules_enabled": "Áp dụng quy định lưu hành",
    "traffic_zone_buffer_minutes": "Thời gian chừa vào/ra vùng",
    "planned_start": "Giờ xuất phát dự kiến",
    "traffic_override_reason": "Lý do duyệt khi vi phạm giờ lưu hành",
    "zone_id": "Vùng hạn chế",
    "permit_id": "Văn bản chấp thuận",
    "day": "Ngày",
    "document_no": "Số văn bản",
    "issuer": "Cơ quan cấp",
    "valid_from": "Ngày hiệu lực",
    "valid_to": "Ngày hết hạn",
    "windows": "Khung giờ",
    "cargo_class": "Loại hàng ưu tiên",
    "client_id": "Mã thao tác",
    "bridge_id": "Cầu",
    "code": "Mã",
    "company_code": "Mã công ty",
    "company_id": "Công ty",
    "confirm_geofence": "Kiểm tra tọa độ",
    "confirm_grace_minutes": "Dung sai thời gian",
    "confirm_radius_m": "Bán kính dung sai",
    "confirm_time_rule": "Kiểm tra thời gian",
    "connection": "Kiểu kết nối",
    "contact_id": "Liên hệ",
    "contact_name": "Người liên hệ",
    "cost_allocation_method": "Phương pháp ghi nhận chi phí",
    "cost_per_km": "Chi phí mỗi km",
    "current_password": "Mật khẩu hiện tại",
    "customer_id": "Khách hàng",
    "cutover_time": "Giờ cut-over",
    "date": "Ngày",
    "date_from": "Từ ngày",
    "date_to": "Đến ngày",
    "delivered_at": "Thời gian giao",
    "deliveries_per_week": "Số lần giao/tuần",
    "delivery_date": "Ngày giao yêu cầu",
    "delivery_point_id": "Điểm giao",
    "delivery_points": "Điểm giao",
    "delivery_weekdays": "Ngày giao trong tuần",
    "description": "Mô tả",
    "device_id": "Thiết bị",
    "device_time": "Giờ thiết bị",
    "device_type": "Loại thiết bị",
    "distance_km": "Số km",
    "driver_id": "Lái xe",
    "dry_run": "Chạy thử",
    "email": "Email",
    "extra_cost": "Chi phí phát sinh",
    "factory": "Nhà máy",
    "file": "File",
    "from_trip_id": "Chuyến nguồn",
    "full_name": "Họ tên",
    "identifier": "Mã định danh",
    "is_active": "Hoạt động",
    "is_default": "Điểm giao mặc định",
    "is_mock_location": "Vị trí giả lập",
    "item_id": "Mục hàng",
    "key_id": "API key",
    "kind": "Loại",
    "latitude": "Vĩ độ",
    "limit": "Số bản ghi",
    "longitude": "Kinh độ",
    "max_trips_per_vehicle": "Số lượt tối đa mỗi xe",
    "model": "Model",
    "motorbike_penalty": "Phạt xe máy qua cầu",
    "name": "Tên",
    "new_password": "Mật khẩu mới",
    "note": "Ghi chú",
    "odometer_end": "Công-tơ-mét về",
    "odometer_start": "Công-tơ-mét đi",
    "offline_max_delay_minutes": "Độ trễ offline tối đa",
    "offset": "Vị trí bắt đầu",
    "order_id": "Đơn hàng",
    "order_part_ids": "Phần đơn",
    "order_status": "Trạng thái lệnh",
    "os_version": "Phiên bản hệ điều hành",
    "paper_size": "Khổ giấy",
    "password": "Mật khẩu",
    "phone": "Điện thoại",
    "photo_keys": "Ảnh chứng từ",
    "photo_required_failed": "Bắt buộc ảnh khi giao thất bại",
    "photo_required_success": "Bắt buộc ảnh khi giao thành công",
    "pin": "Mã PIN",
    "plan_date": "Ngày kế hoạch",
    "planning_time_limit_s": "Thời gian tối ưu tối đa",
    "plate_no": "Biển số xe",
    "product_code_length": "Độ dài mã hàng",
    "product_group": "Nhóm sản phẩm",
    "platform": "Nền tảng",
    "position": "Vị trí",
    "product_id": "Mặt hàng",
    "q": "Từ khóa",
    "reason": "Lý do",
    "refresh_token": "Token làm mới",
    "replace_drafts": "Thay lệnh nháp",
    "require_device_approval": "Bắt buộc duyệt thiết bị",
    "requested_from": "Ngày yêu cầu từ",
    "requested_to": "Ngày yêu cầu đến",
    "required_vehicle_type": "Yêu cầu xe",
    "requires_assistant": "Yêu cầu phụ xe",
    "river_code": "Sông",
    "role": "Vai trò",
    "roles": "Vai trò",
    "rows": "Dòng dữ liệu",
    "run_id": "Lần lập kế hoạch",
    "sales_rep": "NV sales",
    "service_minutes": "Thời gian giao mỗi điểm",
    "shift_end": "Giờ kết thúc ca",
    "shift_start": "Giờ bắt đầu ca",
    "sku_ratio": "Quy đổi - số lượng SKU",
    "sku_uom": "Đơn vị SKU",
    "status": "Trạng thái",
    "stop_id": "Điểm dừng",
    "stops": "Điểm dừng",
    "temp_class": "Loại hàng",
    "timezone": "Múi giờ",
    "to_trip_id": "Chuyến đích",
    "travel_time_factor": "Hệ số thời gian di chuyển",
    "motorbike_priority_radius_km": "Bán kính ưu tiên xe máy (km)",
    "motorbike_priority_cost": "Chi phí cộng thêm khi ô tô giao điểm gần",
    "picking_header": "Đầu trang phiếu soạn hàng",
    "picking_footer": "Chân trang phiếu soạn hàng",
    "delivery_header": "Đầu trang phiếu giao hàng",
    "delivery_footer": "Chân trang phiếu giao hàng",
    "trip_fixed_cost": "Chi phí cố định mỗi chuyến",
    "trip_id": "Chuyến",
    "turnaround_minutes": "Thời gian quay đầu tại kho",
    "uom": "Đơn vị tính",
    "uom_ratio": "Quy đổi - số lượng đơn vị tính",
    "user_id": "Người dùng",
    "username": "Tên đăng nhập",
    "vehicle_id": "Xe",
    "vehicle_type": "Loại xe",
    "warehouse_id": "Kho",
    "warehouse_ids": "Kho",
    "vehicle_ids": "Xe",
    "trip_ids": "Lệnh giao",
    "weight_kg": "Trọng lượng",
    "working_weekdays": "Ngày làm việc",
    "x-api-key": "API key",
    "zalo_access_token": "Token Zalo",
    "zalo_confirm_enabled": "Cho phép xác nhận giao qua Zalo",
    "zalo_location_token": "Token vị trí Zalo",
}

PATTERN_MESSAGES = {
    "^[A-Za-z0-9._/-]+$": "Chỉ gồm chữ không dấu, số và các ký tự . _ / - (không có dấu cách)",
    "^[A-Za-z0-9_-]+$": "Chỉ gồm chữ không dấu, số và các ký tự _ - (không có dấu cách)",
    "^[A-Za-z0-9._-]+$": "Chỉ gồm chữ không dấu, số và các ký tự . _ - (không có dấu cách)",
    r"^\d{6}$": "Phải gồm đúng 6 chữ số",
}


def _not_empty_or_min(ctx: dict[str, Any]) -> str:
    minimum = ctx.get("min_length", 1)
    return "Không được để trống" if minimum <= 1 else f"Tối thiểu {minimum} ký tự"


def _value_error(error: ErrorDetails, ctx: dict[str, Any]) -> str:
    # Lỗi từ validator của mình (tiếng Việt) giữ nguyên; email-validator trả tiếng Anh kèm `reason`.
    if "reason" in ctx:
        return "Email không đúng định dạng"
    return error["msg"].removeprefix("Value error, ")


def _choices(ctx: dict[str, Any]) -> str:
    expected = str(ctx["expected"]).replace(" or ", ", ").replace("'", "")
    return f"Giá trị không hợp lệ (chấp nhận: {expected})"


_MESSAGES: dict[str, Callable[[dict[str, Any]], str]] = {
    "missing": lambda c: "Thiếu dữ liệu bắt buộc",
    "string_type": lambda c: "Phải là chuỗi ký tự",
    "string_too_short": _not_empty_or_min,
    "string_too_long": lambda c: f"Tối đa {c['max_length']} ký tự",
    "string_pattern_mismatch": lambda c: PATTERN_MESSAGES.get(c["pattern"], "Sai định dạng"),
    "int_parsing": lambda c: "Phải là số nguyên",
    "int_type": lambda c: "Phải là số nguyên",
    "int_from_float": lambda c: "Phải là số nguyên",
    "float_parsing": lambda c: "Phải là số",
    "float_type": lambda c: "Phải là số",
    "decimal_parsing": lambda c: "Phải là số",
    "decimal_type": lambda c: "Phải là số",
    "decimal_max_digits": lambda c: f"Tối đa {c['max_digits']} chữ số",
    "decimal_max_places": lambda c: f"Tối đa {c['decimal_places']} chữ số sau dấu phẩy",
    "decimal_whole_digits": lambda c: f"Tối đa {c['whole_digits']} chữ số phần nguyên",
    "greater_than": lambda c: f"Phải lớn hơn {c['gt']}",
    "greater_than_equal": lambda c: f"Không được nhỏ hơn {c['ge']}",
    "less_than": lambda c: f"Phải nhỏ hơn {c['lt']}",
    "less_than_equal": lambda c: f"Không được lớn hơn {c['le']}",
    "too_short": lambda c: f"Cần ít nhất {c['min_length']} mục",
    "too_long": lambda c: f"Tối đa {c['max_length']} mục",
    "enum": _choices,
    "literal_error": _choices,
    "bool_parsing": lambda c: "Phải là đúng/sai",
    "bool_type": lambda c: "Phải là đúng/sai",
    "uuid_parsing": lambda c: "Mã tham chiếu không hợp lệ",
    "uuid_type": lambda c: "Mã tham chiếu không hợp lệ",
    "date_parsing": lambda c: "Ngày không đúng định dạng (YYYY-MM-DD)",
    "date_type": lambda c: "Ngày không đúng định dạng (YYYY-MM-DD)",
    "date_from_datetime_parsing": lambda c: "Ngày không đúng định dạng (YYYY-MM-DD)",
    "date_from_datetime_inexact": lambda c: "Ngày không được kèm giờ",
    "datetime_parsing": lambda c: "Thời gian không đúng định dạng",
    "datetime_type": lambda c: "Thời gian không đúng định dạng",
    "datetime_from_date_parsing": lambda c: "Thời gian không đúng định dạng",
    "time_parsing": lambda c: "Giờ không đúng định dạng (HH:MM)",
    "time_type": lambda c: "Giờ không đúng định dạng (HH:MM)",
    "list_type": lambda c: "Phải là danh sách",
    "dict_type": lambda c: "Sai cấu trúc dữ liệu",
    "model_attributes_type": lambda c: "Sai cấu trúc dữ liệu",
    "json_invalid": lambda c: "Dữ liệu gửi lên không phải JSON hợp lệ",
    "extra_forbidden": lambda c: "Trường không được hỗ trợ",
}


def field_message(error: ErrorDetails) -> str:
    ctx = error.get("ctx", {})
    if error["type"] == "value_error":
        return _value_error(error, ctx)
    render = _MESSAGES.get(error["type"])
    if render is None:
        log.warning("Chưa có thông báo tiếng Việt cho lỗi kiểu %s", error["type"])
        return "Giá trị không hợp lệ"
    return render(ctx)


def field_label(path: list[str | int]) -> str:
    """["delivery_points", 0, "latitude"] → "Điểm giao 1 - Vĩ độ"."""
    parts: list[str] = []
    for part in path:
        if isinstance(part, int):
            if parts:
                parts[-1] = f"{parts[-1]} {part + 1}"
            else:
                parts.append(f"Mục {part + 1}")
        else:
            parts.append(FIELD_LABELS.get(part, part))
    return " - ".join(parts)


def describe(errors: list[ErrorDetails]) -> dict[str, Any]:
    fields = []
    for error in errors:
        # Bỏ vị trí ("body"/"query"/"path"/"header") và nhánh union kiểu "function-after[...]".
        path = [p for p in error["loc"][1:] if isinstance(p, int) or "[" not in p]
        fields.append({"path": path, "label": field_label(path), "message": field_message(error)})
    details = [f"{f['label']}: {f['message']}" if f["label"] else f["message"] for f in fields]
    return {"code": "validation_error", "message": SUMMARY, "details": details, "fields": fields}


def register_validation_handler(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _handle(_: Request, exc: RequestValidationError) -> JSONResponse:
        body = describe(list(exc.errors()))
        return JSONResponse(status_code=422, content={"error": jsonable_encoder(body)})
