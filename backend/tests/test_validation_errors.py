from typing import Any

import pytest
from httpx import AsyncClient

from app.core.validation import FIELD_LABELS
from app.main import app
from tests.conftest import auth

POINT = {"code": "DG1", "address": "HN", "latitude": "21.0285", "longitude": "105.8542"}
CUSTOMER = {"code": "KH001", "name": "Đại lý", "delivery_points": [POINT]}


async def invalid(client: AsyncClient, token: str, **overrides: Any) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/customers", headers=auth(token), json={**CUSTOMER, **overrides}
    )
    assert resp.status_code == 422, resp.text
    error: dict[str, Any] = resp.json()["error"]
    assert error["code"] == "validation_error"
    return error


@pytest.mark.parametrize(
    ("overrides", "path", "label", "message"),
    [
        (
            {"code": "KH 001"},
            ["code"],
            "Mã",
            "Chỉ gồm chữ không dấu, số và các ký tự . _ / - (không có dấu cách)",
        ),
        ({"name": ""}, ["name"], "Tên", "Không được để trống"),
        ({"name": "x" * 256}, ["name"], "Tên", "Tối đa 255 ký tự"),
        ({"email": "abc"}, ["email"], "Email", "Email không đúng định dạng"),
        (
            {"deliveries_per_week": 9},
            ["deliveries_per_week"],
            "Số lần giao/tuần",
            "Không được lớn hơn 7",
        ),
        (
            {"required_vehicle_type": "XE"},
            ["required_vehicle_type"],
            "Yêu cầu xe",
            "Giá trị không hợp lệ (chấp nhận: CAR, MOTORBIKE, ANY)",
        ),
        ({"delivery_points": []}, ["delivery_points"], "Điểm giao", "Cần ít nhất 1 mục"),
        (
            {"delivery_points": [{**POINT, "latitude": "21.0285112"}]},
            ["delivery_points", 0, "latitude"],
            "Điểm giao 1 - Vĩ độ",
            "Tối đa 6 chữ số sau dấu phẩy",
        ),
        (
            {"delivery_points": [POINT, {**POINT, "code": "DG2", "longitude": "181"}]},
            ["delivery_points", 1, "longitude"],
            "Điểm giao 2 - Kinh độ",
            "Không được lớn hơn 180",
        ),
        (
            {"delivery_points": [{"code": "DG1", "latitude": "21", "longitude": "105"}]},
            ["delivery_points", 0, "address"],
            "Điểm giao 1 - Địa chỉ",
            "Thiếu dữ liệu bắt buộc",
        ),
    ],
)
async def test_each_field_error_is_explained_in_vietnamese(
    client: AsyncClient,
    admin_token: str,
    overrides: dict[str, Any],
    path: list[Any],
    label: str,
    message: str,
) -> None:
    error = await invalid(client, admin_token, **overrides)
    assert error["fields"] == [{"path": path, "label": label, "message": message}]
    assert error["details"] == [f"{label}: {message}"]


async def test_all_errors_are_reported_together(client: AsyncClient, admin_token: str) -> None:
    error = await invalid(client, admin_token, code="", email="abc")
    assert {f["label"] for f in error["fields"]} == {"Mã", "Email"}


async def test_custom_validator_message_and_no_input_echo(
    client: AsyncClient, admin_token: str
) -> None:
    resp = await client.post(
        "/api/v1/auth/change-password",
        headers=auth(admin_token),
        json={"current_password": "x", "new_password": "bi-mat"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["details"] == ["Mật khẩu mới: Tối thiểu 8 ký tự"]
    assert "bi-mat" not in resp.text


async def test_query_parameter_error(client: AsyncClient, admin_token: str) -> None:
    resp = await client.get("/api/v1/customers", headers=auth(admin_token), params={"limit": "abc"})
    assert resp.status_code == 422
    assert resp.json()["error"]["details"] == ["Số bản ghi: Phải là số nguyên"]


def test_every_api_field_has_a_vietnamese_label() -> None:
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    seen: set[str] = set()
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref and (name := ref.rsplit("/", 1)[-1]) not in seen:
                seen.add(name)
                names.update(schemas[name].get("properties", {}))
                walk(schemas[name])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for operations in spec["paths"].values():
        for operation in operations.values():
            names.update(p["name"] for p in operation.get("parameters", []))
            walk(operation.get("requestBody", {}))
    assert sorted(names - set(FIELD_LABELS)) == []
