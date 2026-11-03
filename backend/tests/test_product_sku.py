"""SKU là số gốc của đơn hàng và tồn kho; đơn vị tính (ĐVT) suy ra cho vận tải."""

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient

from app.modules.orders.models import pack_breakdown
from tests.conftest import Env, auth, stop, trip_body
from tests.test_customer_portal import customer_token, orders

ORDER_HEAD = "so_don,ngay_dat,ngay_giao_yc,ma_kh,gia_tri_don,ma_hang,so_luong,don_vi\n"
PRODUCT_HEAD = "ma_hang,ten_hang,loai_hang,don_vi_tinh,trong_luong_kg,don_vi_sku,sl_sku,sl_dvt\n"
OLD_PRODUCT_HEAD = "ma_hang,ten_hang,loai_hang,don_vi_tinh,trong_luong_kg\n"
SAMPLE_1L = "SUA-TT-1L"  # 12 Hộp = 1 Thùng, 12,8 kg/thùng; DH2610-004 đặt 360 Hộp


async def _import(client: AsyncClient, token: str, kind: str, content: str) -> dict[str, Any]:
    resp = await client.post(
        f"/api/v1/imports/{kind}",
        headers=auth(token),
        files={"file": ("f.csv", content.encode())},
    )
    body: dict[str, Any] = resp.json()
    return body


async def _product(client: AsyncClient, token: str, code: str) -> dict[str, Any]:
    items = (await client.get(f"/api/v1/products?q={code}", headers=auth(token))).json()["items"]
    product: dict[str, Any] = next(p for p in items if p["code"] == code)
    return product


async def _order(client: AsyncClient, token: str, ref: str) -> dict[str, Any]:
    items = (await client.get(f"/api/v1/orders?q={ref}", headers=auth(token))).json()["items"]
    order: dict[str, Any] = (
        await client.get(f"/api/v1/orders/{items[0]['id']}", headers=auth(token))
    ).json()
    return order


def _line(order: dict[str, Any], code: str) -> dict[str, Any]:
    line: dict[str, Any] = next(x for x in order["lines"] if x["product_code"] == code)
    return line


async def test_sample_order_converts_sku_to_uom(client: AsyncClient, env: Env) -> None:
    line = _line(await _order(client, env.manager, "DH2610-004"), SAMPLE_1L)
    assert (line["sku_uom"], Decimal(line["sku_qty"])) == ("Hộp", Decimal(360))
    assert (line["uom"], Decimal(line["uom_qty"])) == ("Thùng", Decimal(30))
    assert Decimal(line["weight_kg"]) == Decimal(384)


async def test_non_terminating_and_reverse_conversion(client: AsyncClient, env: Env) -> None:
    products = (
        PRODUCT_HEAD + "H1,Hàng hộp,Khô,Thùng,9.6,Hộp,48,1\nH2,Hàng lốc,Khô,Lốc,2,Thùng,1,12\n"
    )
    assert (await _import(client, env.manager, "products", products))["status"] == "SUCCEEDED"
    content = (
        ORDER_HEAD
        + "SKU-1,01/11/2026,02/11/2026,KH001,100,H1,5,\n"
        + "SKU-2,01/11/2026,02/11/2026,KH001,100,H2,3,thùng\n"
    )
    result = await _import(client, env.manager, "orders", content)
    assert result["status"] == "SUCCEEDED", result["errors"]

    # 5 Hộp = 5/48 Thùng: khối lượng tính từ số chưa làm tròn.
    box = (await _order(client, env.manager, "SKU-1"))["lines"][0]
    assert Decimal(box["sku_qty"]) == 5
    assert Decimal(box["uom_qty"]) == Decimal("0.104167")
    assert Decimal(box["weight_kg"]) == Decimal(1)

    # SKU lớn hơn ĐVT: 3 Thùng = 36 Lốc.
    pack = (await _order(client, env.manager, "SKU-2"))["lines"][0]
    assert Decimal(pack["uom_qty"]) == 36
    assert Decimal(pack["weight_kg"]) == 72


@pytest.mark.parametrize(
    ("qty", "sku", "uom", "expected"),
    [
        ("100", "48", "1", (2, Decimal(4))),
        ("96", "48", "1", (2, Decimal(0))),
        ("5", "48", "1", (0, Decimal(5))),
        ("10", "7", "3", (4, Decimal("0.667"))),
        ("3", "1", "12", None),
        ("3", "1", "1", None),
    ],
)
def test_pack_breakdown(qty: str, sku: str, uom: str, expected: Any) -> None:
    assert pack_breakdown(Decimal(qty), Decimal(sku), Decimal(uom)) == expected


async def test_stock_warning_in_sku(client: AsyncClient, env: Env) -> None:
    # Tồn file là SKU: 300 Hộp < 360 Hộp cần, dù cùng con số 300 Thùng sẽ đủ nếu hiểu là ĐVT.
    stock = f"ma_kho,ma_hang,so_luong_ton,don_vi\nKHO01,{SAMPLE_1L},300,Hộp\n"
    assert (await _import(client, env.manager, "inventory", stock))["status"] == "SUCCEEDED"
    body = trip_body(env, "XE02", "KHO01", [stop(env, ("DH2610-004", "DRY"))])
    resp = await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    assert resp.status_code == 201, resp.text
    warning = next(w for w in resp.json()["warnings"] if SAMPLE_1L in w)
    assert "cần 360 Hộp (30 Thùng), còn 300 Hộp (25 Thùng)" in warning

    # Lệnh vừa tạo giữ chỗ 360 Hộp: nhập tồn 361, còn khả dụng 1 Hộp (1 Hộp = 0,083 Thùng).
    stock = f"ma_kho,ma_hang,so_luong_ton\nKHO01,{SAMPLE_1L},361\n"
    assert (await _import(client, env.manager, "inventory", stock))["status"] == "SUCCEEDED"
    listing = (await client.get("/api/v1/inventory?q=SUA-TT-1L", headers=auth(env.manager))).json()
    row = listing["items"][0]
    assert (row["sku_uom"], Decimal(row["qty_on_hand"])) == ("Hộp", Decimal(361))
    assert (row["uom"], round(Decimal(row["uom_qty"]), 3)) == ("Thùng", Decimal("30.083"))


async def test_unit_column_must_match_sku(client: AsyncClient, env: Env) -> None:
    stock = f"ma_kho,ma_hang,so_luong_ton,don_vi\nKHO01,{SAMPLE_1L},10,Thùng\n"
    result = await _import(client, env.manager, "inventory", stock)
    assert result["status"] != "SUCCEEDED"
    assert "khác đơn vị SKU 'Hộp'" in result["errors"][0]["message"]

    content = ORDER_HEAD + f"SKU-9,01/11/2026,02/11/2026,KH001,100,{SAMPLE_1L},2,Thùng\n"
    result = await _import(client, env.manager, "orders", content)
    assert result["status"] != "SUCCEEDED"
    assert result["errors"][0]["column"] == "Đơn vị"


async def test_conversion_recalculates_only_orders_without_trip(
    client: AsyncClient, env: Env
) -> None:
    # DH2610-004 vào lệnh; đơn mới cùng mặt hàng chưa vào lệnh.
    body = trip_body(env, "XE02", "KHO01", [stop(env, ("DH2610-004", "DRY"))])
    assert (
        await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    ).status_code == 201
    content = ORDER_HEAD + f"SKU-3,01/11/2026,02/11/2026,KH001,100,{SAMPLE_1L},24,\n"
    assert (await _import(client, env.manager, "orders", content))["status"] == "SUCCEEDED"
    assert Decimal(
        (await _order(client, env.manager, "SKU-3"))["parts"][0]["weight_kg"]
    ) == Decimal("25.6")

    product = await _product(client, env.manager, SAMPLE_1L)
    resp = await client.patch(
        f"/api/v1/products/{product['id']}",
        headers=auth(env.manager),
        json={"sku_ratio": "24", "uom_ratio": "1"},
    )
    assert resp.status_code == 200, resp.text

    open_order = await _order(client, env.manager, "SKU-3")
    assert Decimal(open_order["lines"][0]["uom_qty"]) == 1
    assert Decimal(open_order["lines"][0]["weight_kg"]) == Decimal("12.8")
    assert Decimal(open_order["parts"][0]["weight_kg"]) == Decimal("12.8")

    planned = _line(await _order(client, env.manager, "DH2610-004"), SAMPLE_1L)
    assert Decimal(planned["uom_qty"]) == 30
    assert Decimal(planned["weight_kg"]) == 384


async def test_import_recalculates_open_orders(client: AsyncClient, env: Env) -> None:
    content = OLD_PRODUCT_HEAD + f"{SAMPLE_1L},Sữa,Khô,Thùng,10\n"
    assert (await _import(client, env.manager, "products", content))["status"] == "SUCCEEDED"
    line = _line(await _order(client, env.manager, "DH2610-004"), SAMPLE_1L)
    assert Decimal(line["weight_kg"]) == 300


async def test_sku_unit_locked_while_orders_open(client: AsyncClient, env: Env) -> None:
    product = await _product(client, env.manager, SAMPLE_1L)
    url = f"/api/v1/products/{product['id']}"
    resp = await client.patch(
        url,
        headers=auth(env.manager),
        json={"sku_uom": "Lốc", "sku_ratio": "2", "uom_ratio": "1"},
    )
    assert resp.status_code == 400
    assert "chưa đổi được đơn vị SKU" in resp.json()["error"]["message"]
    content = PRODUCT_HEAD + f"{SAMPLE_1L},Sữa,Khô,Thùng,12.8,Lốc,2,1\n"
    result = await _import(client, env.manager, "products", content)
    assert "chưa đổi được đơn vị SKU" in result["errors"][0]["message"]

    # Đổi chữ hoa/thường không phải đổi đơn vị.
    resp = await client.patch(url, headers=auth(env.manager), json={"sku_uom": "hộp"})
    assert resp.status_code == 200, resp.text


async def test_new_product_file_requires_all_api_requires_sku(
    client: AsyncClient, admin_token: str
) -> None:
    # File: thiếu cột/thiếu 1 trong 3 đều lỗi; SKU trùng ĐVT mà khác 1 = 1 cũng lỗi.
    content = OLD_PRODUCT_HEAD + "X0,X,Khô,Thùng,1\n"
    assert (await _import(client, admin_token, "products", content))["status"] != "SUCCEEDED"
    bad = (
        PRODUCT_HEAD
        + "X1,X,Khô,Thùng,1,Hộp,,\nX2,X,Khô,Thùng,1,Hộp,48,\nX3,X,Khô,Thùng,1,thùng,2,1\n"
    )
    result = await _import(client, admin_token, "products", bad)
    assert {e["row"] for e in result["errors"]} == {2, 3, 4}

    # API tích hợp: chỉ bắt buộc SKU, số quy đổi thiếu = 1.
    key = (
        await client.post("/api/v1/api-keys", headers=auth(admin_token), json={"name": "k"})
    ).json()["api_key"]
    base = {"ten_hang": "X", "loai_hang": "Khô", "don_vi_tinh": "Thùng", "trong_luong_kg": 1}
    url, head = "/api/v1/integration/products", {"X-API-Key": key}
    missing = await client.post(url, headers=head, json={"rows": [{**base, "ma_hang": "A1"}]})
    assert "Thiếu đơn vị SKU" in missing.json()["errors"][0]["message"]
    rows = [
        {**base, "ma_hang": "A2", "don_vi_sku": "Hộp"},
        {**base, "ma_hang": "A3", "don_vi_sku": "Hộp", "sl_sku": 48},
    ]
    created = await client.post(url, headers=head, json={"rows": rows})
    assert created.json()["status"] == "SUCCEEDED", created.text
    a2 = await _product(client, admin_token, "A2")
    a3 = await _product(client, admin_token, "A3")
    assert (Decimal(a2["sku_ratio"]), Decimal(a2["uom_ratio"])) == (1, 1)
    assert (Decimal(a3["sku_ratio"]), Decimal(a3["uom_ratio"])) == (48, 1)

    # API REST: cũng bắt buộc SKU.
    body = {"code": "R1", "name": "X", "temp_class": "DRY", "uom": "Thùng", "weight_kg": "1"}
    products, auth_head = "/api/v1/products", auth(admin_token)
    assert (await client.post(products, headers=auth_head, json=body)).status_code == 422
    resp = await client.post(products, headers=auth_head, json={**body, "sku_uom": "Hộp"})
    assert resp.status_code == 201, resp.text


async def test_existing_product_keeps_conversion_when_blank(client: AsyncClient, env: Env) -> None:
    content = OLD_PRODUCT_HEAD + f"{SAMPLE_1L},Sữa,Khô,Thùng,13\n"
    assert (await _import(client, env.manager, "products", content))["status"] == "SUCCEEDED"
    product = await _product(client, env.manager, SAMPLE_1L)
    assert (product["sku_uom"], Decimal(product["sku_ratio"])) == ("Hộp", Decimal(12))
    assert Decimal(product["weight_kg"]) == 13


async def test_picking_and_delivery_show_both_units_and_pack(client: AsyncClient, env: Env) -> None:
    content = PRODUCT_HEAD + "H1,Hàng hộp,Khô,Thùng,9.6,Hộp,48,1\n"
    assert (await _import(client, env.manager, "products", content))["status"] == "SUCCEEDED"
    orders_csv = ORDER_HEAD + "SKU-1,01/11/2026,02/11/2026,KH001,100,H1,100,\n"
    assert (await _import(client, env.manager, "orders", orders_csv))["status"] == "SUCCEEDED"
    parts = (
        await client.get(
            "/api/v1/trips/available-parts?plan_date=2026-11-02", headers=auth(env.manager)
        )
    ).json()
    part = next(p for p in parts if p["external_ref"] == "SKU-1")
    body = trip_body(env, "XE02", "KHO01", [])
    body["stops"] = [
        {"delivery_point_id": part["delivery_point_id"], "order_part_ids": [part["id"]]}
    ]
    resp = await client.post("/api/v1/trips", headers=auth(env.manager), json=body)
    assert resp.status_code == 201, resp.text
    trip = resp.json()

    line = trip["stops"][0]["items"][0]["lines"][0]
    assert (line["sku_uom"], Decimal(line["sku_qty"])) == ("Hộp", Decimal(100))
    assert (line["uom"], line["whole_uom"], Decimal(line["rest_sku"])) == ("Thùng", 2, Decimal(4))

    picking = (
        await client.get(f"/api/v1/trips/{trip['id']}/picking-list", headers=auth(env.manager))
    ).json()
    row = picking["lines"][0]
    assert (row["sku_uom"], Decimal(row["sku_qty"]), row["whole_uom"]) == ("Hộp", Decimal(100), 2)
    assert Decimal(row["rest_sku"]) == 4


async def test_customer_sees_ordered_sku(client: AsyncClient, env: Env) -> None:
    products = PRODUCT_HEAD + "H1,Hàng hộp,Khô,Thùng,9.6,Hộp,48,1\n"
    assert (await _import(client, env.manager, "products", products))["status"] == "SUCCEEDED"
    content = ORDER_HEAD + "SKU-1,01/11/2026,02/11/2026,KH001,100,H1,96,\n"
    assert (await _import(client, env.manager, "orders", content))["status"] == "SUCCEEDED"

    token = await customer_token(client, env, "0912000001", "zalo-owner")
    order = next(o for o in (await orders(client, token))["items"] if o["external_ref"] == "SKU-1")
    url = f"/api/v1/customer/orders/{order['id']}"
    line = (await client.get(url, headers=auth(token))).json()["lines"][0]
    assert (line["uom"], Decimal(line["qty"])) == ("Hộp", Decimal(96))
