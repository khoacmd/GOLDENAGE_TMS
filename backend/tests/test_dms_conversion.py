import base64
import io
from datetime import datetime
from typing import Any

from httpx import AsyncClient
from openpyxl import load_workbook

from tests.conftest import auth, create_user, login
from tests.test_imports import upload, xlsx

DMS_HEADERS = [
    "OrderNbr",
    "OrderType",
    "OrderDate",
    "CreateShipDate",
    "CustomerCD",
    "InventoryCD",
    "OrderSalesQty",
    "OrderFreeQty",
    "SalesPrice",
    "IsReturned",
]
D3, D4 = datetime(2026, 11, 3), datetime(2026, 11, 4)


def dms_file(rows: list[list[Any]]) -> bytes:
    return xlsx(DMS_HEADERS, rows)


async def convert(
    client: AsyncClient, token: str, content: bytes, query: str = ""
) -> tuple[int, dict[str, Any]]:
    resp = await client.post(
        f"/api/v1/conversions/dms-orders{query}",
        headers=auth(token),
        files={"file": ("10004337_T11.xlsx", content)},
    )
    body: dict[str, Any] = resp.json()
    return resp.status_code, body


async def seed(client: AsyncClient, token: str) -> None:
    products = (
        "ma_hang,ten_hang,loai_hang,don_vi_tinh,trong_luong_kg,don_vi_sku,sl_sku,sl_dvt\n"
        "000000000472500001,Sữa tươi 180ml,Lạnh,Thùng,9,Hộp,48,1\n"
        "000000000472500002,Sữa tươi 1L,Lạnh,Thùng,12,Hộp,12,1\n"
    )
    customers = (
        "Mã KH,Tên KH,Mã điểm giao,Địa chỉ điểm giao,Vĩ độ,Kinh độ\n"
        "C001,Khách 1,DG1,Số 1,21.02,105.85\n"
        "C002,Khách 2,DG1,Số 2,21.03,105.80\n"
    )
    for kind, content in (("products", products), ("customers", customers)):
        result = await upload(client, token, kind, content.encode(), "x.csv")
        assert result["status"] == "SUCCEEDED", result


async def test_convert_dms_orders_then_import(client: AsyncClient, admin_token: str) -> None:
    await seed(client, admin_token)
    content = dms_file(
        [
            # Đơn 1: 2 dòng cùng mặt hàng (bán + tặng) được gộp; giao ngày hôm sau.
            ["DH-1", "SO", D3, D4, "C001", 472500001, 10, 0, 9000, False],
            ["DH-1", "SO", D3, D4, "C001", 472500001, 0, 2, 9000, False],
            ["DH-1", "SO", D3, D3, "C001", 472500002, 5, 0, 30000, False],
            # Số lượng 0 và hàng trả bị bỏ qua.
            ["DH-2", "SO", D3, D3, "C002", 472500002, 0, 0, 30000, False],
            ["DH-3", "SO", D3, D3, "C002", 472500002, 4, 0, 30000, False],
            ["DH-4", "SO", D3, D3, "C002", 472500002, 4, 0, 30000, True],
        ]
    )
    status, body = await convert(client, admin_token, content)
    assert status == 200, body
    assert body["filename"] == "DonHang_10004337_T11.xlsx"
    assert (body["lines"], body["orders"], body["customers"], body["products"]) == (3, 2, 2, 2)
    assert (body["skipped_zero_qty"], body["skipped_returns"]) == (1, 1)
    assert body["total_value"] == 10 * 9000 + 5 * 30000 + 4 * 30000
    assert (body["first_delivery_date"], body["last_delivery_date"]) == ("2026-11-03", "2026-11-04")

    result = await upload(
        client, admin_token, "orders", base64.b64decode(body["content_base64"]), body["filename"]
    )
    assert (result["status"], result["created"]) == ("SUCCEEDED", 2), result
    orders = (await client.get("/api/v1/orders", headers=auth(admin_token))).json()["items"]
    dh1 = next(o for o in orders if o["external_ref"] == "DH-1")
    # Ngày giao của đơn = ngày tạo phiếu giao muộn nhất; hàng tặng không tính tiền.
    assert (dh1["requested_date"], dh1["order_value"]) == ("2026-11-04", "240000.00")
    detail = (await client.get(f"/api/v1/orders/{dh1['id']}", headers=auth(admin_token))).json()
    qty = {line["product_code"]: line["sku_qty"] for line in detail["lines"]}
    assert qty == {"000000000472500001": "12.000", "000000000472500002": "5.000"}


async def test_convert_options_and_errors(client: AsyncClient, admin_token: str) -> None:
    content = dms_file([["DH-1", "SO", D3, D4, "C001", 472500001, 10, 0, 9000, False]])
    status, body = await convert(
        client, admin_token, content, "?delivery_date=2026-11-09&product_code_length=0"
    )
    assert status == 200, body
    assert body["first_delivery_date"] == body["last_delivery_date"] == "2026-11-09"

    status, body = await convert(client, admin_token, xlsx(["Mã hàng"], [["A"]]))
    assert status == 400
    assert "OrderNbr" in body["error"]["details"][0]

    bad = dms_file(
        [
            ["DH-1", "SO", D3, D3, "C001", 1, 1, 0, 1, False],
            ["DH-1", "SO", D3, D3, "C002", 2, 1, 0, 1, False],
            ["DH-2", "SO", "abc", D3, "C002", 2, 1, 0, 1, False],
        ]
    )
    status, body = await convert(client, admin_token, bad)
    assert status == 400
    assert body["error"]["details"] == ["Dòng 4: ngày không hợp lệ: abc"]


async def test_convert_requires_manager(client: AsyncClient, admin_token: str) -> None:
    await create_user(client, admin_token, "keeper1", ["warehouse_keeper"])
    keeper = await login(client, "keeper1", "password-123")
    content = dms_file([["DH-1", "SO", D3, D4, "C001", 1, 1, 0, 1, False]])
    status, _ = await convert(client, keeper, content)
    assert status == 403


MASTER_HEADERS = [
    "OrderNbr",
    "CustomerCD",
    "CustomerName",
    "AddressLine1",
    "EmployeeName",
    "InventoryCD",
    "InventoryName",
    "INAttribute1Descr",
    "INAttribute2Descr",
    "INAttribute3Descr",
    "UnitRate",
]
MASTER_ROWS = [
    ["DH-1", "C001", "Khách 1", "Số 1", "NV A", 472500001, "Sữa 180ml", "DLM", "Sữa DL", "Lạnh", 1],
    [
        "DH-2",
        "C009",
        "Khách 9",
        "Số 9",
        "NV B",
        410055531,
        "Trà ô long",
        "NÚI TIÊN",
        "Đồ Uống",
        "Khô",
        24,
    ],
    ["DH-3", "C009", "Khách 9", "Số 9", "NV B", 472500099, "Sữa mới", "DLM", "Sữa DL", "Lạnh", 1],
]


async def post_master(client: AsyncClient, token: str, kind: str) -> dict[str, Any]:
    resp = await client.post(
        f"/api/v1/conversions/dms-{kind}",
        headers=auth(token),
        files={"file": ("dms.xlsx", xlsx(MASTER_HEADERS, MASTER_ROWS))},
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def data_rows(body: dict[str, Any]) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    wb = load_workbook(io.BytesIO(base64.b64decode(body["content_base64"])))
    rows = list(wb["Dữ liệu"].iter_rows(min_row=2, values_only=True))
    todo = list(wb["Cần bổ sung"].iter_rows(min_row=2, values_only=True))
    return rows, todo


async def test_convert_dms_customers_only_new(client: AsyncClient, admin_token: str) -> None:
    await seed(client, admin_token)
    body = await post_master(client, admin_token, "customers")
    assert body["filename"] == "KhachHang_dms.xlsx"
    assert (body["total"], body["new"], body["existing"], body["incomplete"]) == (2, 1, 1, 1)
    rows, todo = data_rows(body)
    # Mã KH, tên, địa chỉ, ..., NV sales, ..., điểm giao DG1, tọa độ trống, mặc định.
    assert [(r[0], r[1], r[2], r[7], r[10], r[12], r[13], r[15]) for r in rows] == [
        ("C009", "Khách 9", "Số 9", "NV B", "DG1", "Số 9", None, "C")
    ]
    assert todo == [(2, "C009", "Khách 9", "Vĩ độ, Kinh độ")]

    # Điền tọa độ là import được.
    content = xlsx(
        ["Mã KH", "Tên KH", "Mã điểm giao", "Địa chỉ điểm giao", "Vĩ độ", "Kinh độ"],
        [["C009", "Khách 9", "DG1", "Số 9", 21.0, 105.8]],
    )
    assert (await upload(client, admin_token, "customers", content, "kh.xlsx"))["created"] == 1


async def test_convert_dms_products_only_new(client: AsyncClient, admin_token: str) -> None:
    await seed(client, admin_token)
    body = await post_master(client, admin_token, "products")
    assert body["filename"] == "MatHang_dms.xlsx"
    assert (body["total"], body["new"], body["existing"], body["incomplete"]) == (3, 2, 1, 2)
    rows, todo = data_rows(body)
    assert [r[:10] for r in rows] == [
        (
            "000000000410055531",
            "Trà ô long",
            "Khô",
            "Thùng",
            None,
            None,
            24,
            1,
            "NÚI TIÊN",
            "Đồ Uống",
        ),
        ("000000000472500099", "Sữa mới", "Lạnh", "Thùng", None, None, None, 1, "DLM", "Sữa DL"),
    ]
    assert [t[3] for t in todo] == [
        "Trọng lượng (kg), Đơn vị SKU",
        "Trọng lượng (kg), Đơn vị SKU, SL SKU quy đổi",
    ]
