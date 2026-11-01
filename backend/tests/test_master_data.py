from typing import Any

from httpx import AsyncClient

from tests.conftest import auth, create_company, create_warehouse, login


def _vehicle(warehouse_ids: list[str], **overrides: Any) -> dict[str, Any]:
    return {
        "code": "XE01",
        "name": "Xe tải 2 tấn",
        "plate_no": "29C-123.45",
        "vehicle_type": "CAR",
        "capacity_kg": "2000",
        "cost_per_km": "8000",
        "requires_assistant": True,
        "cargo_class": "ANY",
        "cost_allocation_method": "WEIGHT",
        "warehouse_ids": warehouse_ids,
        **overrides,
    }


def _customer(**overrides: Any) -> dict[str, Any]:
    return {
        "code": "KH001",
        "name": "Đại lý Minh Anh",
        "required_vehicle_type": "ANY",
        "delivery_weekdays": [1, 3, 5],
        "deliveries_per_week": 3,
        "delivery_points": [
            {
                "code": "DG1",
                "address": "12 Trần Phú, Hà Đông",
                "latitude": "20.97",
                "longitude": "105.78",
            },
            {
                "code": "DG2",
                "address": "5 Quang Trung, Hà Đông",
                "latitude": "20.96",
                "longitude": "105.77",
            },
        ],
        **overrides,
    }


async def test_warehouse_crud(client: AsyncClient, admin_token: str) -> None:
    created = await create_warehouse(client, admin_token)
    assert created["code"] == "KHO01"

    resp = await client.post(
        "/api/v1/warehouses",
        headers=auth(admin_token),
        json={**created, "code": "kho01", "name": "Trùng"},
    )
    assert resp.status_code == 409

    resp = await client.patch(
        f"/api/v1/warehouses/{created['id']}",
        headers=auth(admin_token),
        json={"name": "Kho Hà Đông mới", "is_active": False},
    )
    assert resp.json()["name"] == "Kho Hà Đông mới"

    page = (
        await client.get("/api/v1/warehouses?active=false&q=đông", headers=auth(admin_token))
    ).json()
    assert page["total"] == 1

    resp = await client.post(
        "/api/v1/warehouses",
        headers=auth(admin_token),
        json={**created, "code": "KHO02", "latitude": "95"},
    )
    assert resp.status_code == 422


async def test_location_generated_from_coordinates(
    client: AsyncClient, admin_token: str, owner_engine: Any
) -> None:
    from sqlalchemy import text

    await create_warehouse(client, admin_token)
    async with owner_engine.connect() as conn:
        # FORCE RLS áp dụng cả cho owner → phải đặt context công ty.
        await conn.execute(
            text(
                "SELECT set_config('app.company_id', "
                "(SELECT id::text FROM companies WHERE code = 'NPP01'), false)"
            )
        )
        lon, lat = (
            await conn.execute(
                text("SELECT ST_X(location::geometry), ST_Y(location::geometry) FROM warehouses")
            )
        ).one()
    assert (round(lon, 3), round(lat, 3)) == (105.776, 20.971)


async def test_vehicle_with_warehouses(client: AsyncClient, admin_token: str) -> None:
    w1 = await create_warehouse(client, admin_token)
    w2 = await create_warehouse(client, admin_token, code="KHO02", name="Kho Long Biên")

    resp = await client.post(
        "/api/v1/vehicles", headers=auth(admin_token), json=_vehicle([w1["id"]])
    )
    assert resp.status_code == 201, resp.text
    vehicle = resp.json()
    assert vehicle["warehouse_ids"] == [w1["id"]]

    resp = await client.patch(
        f"/api/v1/vehicles/{vehicle['id']}",
        headers=auth(admin_token),
        json={"warehouse_ids": [w2["id"], w1["id"]], "capacity_kg": "1900"},
    )
    assert sorted(resp.json()["warehouse_ids"]) == sorted([w1["id"], w2["id"]])
    assert float(resp.json()["capacity_kg"]) == 1900

    # Trùng biển số (không phân biệt hoa thường), kho không tồn tại, trọng tải <= 0.
    resp = await client.post(
        "/api/v1/vehicles",
        headers=auth(admin_token),
        json=_vehicle([w1["id"]], code="XE02", plate_no="29c-123.45"),
    )
    assert resp.status_code == 409
    resp = await client.post(
        "/api/v1/vehicles",
        headers=auth(admin_token),
        json=_vehicle(["00000000-0000-0000-0000-000000000000"], code="XE03", plate_no="X"),
    )
    assert resp.json()["error"]["code"] == "invalid_warehouse"
    resp = await client.post(
        "/api/v1/vehicles",
        headers=auth(admin_token),
        json=_vehicle([w1["id"]], code="XE04", plate_no="Y", capacity_kg="0"),
    )
    assert resp.status_code == 422


async def test_customer_delivery_points_default(client: AsyncClient, admin_token: str) -> None:
    resp = await client.post("/api/v1/customers", headers=auth(admin_token), json=_customer())
    assert resp.status_code == 201, resp.text
    customer = resp.json()
    defaults = [p["code"] for p in customer["delivery_points"] if p["is_default"]]
    assert defaults == ["DG1"]  # không chọn → điểm đầu tiên là mặc định

    points = _customer()["delivery_points"]
    points[1]["is_default"] = True
    resp = await client.patch(
        f"/api/v1/customers/{customer['id']}",
        headers=auth(admin_token),
        json={"delivery_points": points},
    )
    assert resp.status_code == 200, resp.text
    assert [p["code"] for p in resp.json()["delivery_points"] if p["is_default"]] == ["DG2"]

    # Bỏ DG2 khỏi danh sách → DG2 ngưng hoạt động, DG1 thành mặc định.
    resp = await client.patch(
        f"/api/v1/customers/{customer['id']}",
        headers=auth(admin_token),
        json={"delivery_points": [points[0]]},
    )
    by_code = {p["code"]: p for p in resp.json()["delivery_points"]}
    assert by_code["DG2"]["is_active"] is False
    assert by_code["DG1"]["is_default"] is True

    two_defaults = _customer(code="KH002")
    for p in two_defaults["delivery_points"]:
        p["is_default"] = True
    resp = await client.post("/api/v1/customers", headers=auth(admin_token), json=two_defaults)
    assert resp.json()["error"]["code"] == "multiple_default_points"


async def test_product_crud(client: AsyncClient, admin_token: str) -> None:
    body = {
        "code": "SUA-TT-180",
        "name": "Sữa tươi 180ml (thùng 48)",
        "temp_class": "CHILLED",
        "uom": "Thùng",
        "weight_kg": "9.2",
    }
    resp = await client.post("/api/v1/products", headers=auth(admin_token), json=body)
    assert resp.status_code == 201, resp.text
    product = resp.json()
    resp = await client.patch(
        f"/api/v1/products/{product['id']}",
        headers=auth(admin_token),
        json={"temp_class": "FROZEN"},
    )
    assert resp.json()["temp_class"] == "FROZEN"


async def test_master_data_isolated_between_companies(
    client: AsyncClient, sysadmin_token: str, admin_token: str
) -> None:
    warehouse = await create_warehouse(client, admin_token)
    await create_company(client, sysadmin_token, "NPP02", "admin02")
    other = await login(client, "admin02", "admin-pass-123")

    assert (await client.get("/api/v1/warehouses", headers=auth(other))).json()["total"] == 0
    resp = await client.get(f"/api/v1/warehouses/{warehouse['id']}", headers=auth(other))
    assert resp.status_code == 404
    # Mã kho trùng ở công ty khác vẫn hợp lệ.
    await create_warehouse(client, other)


async def test_system_admin_cannot_access_company_data(
    client: AsyncClient, sysadmin_token: str
) -> None:
    resp = await client.get("/api/v1/warehouses", headers=auth(sysadmin_token))
    assert resp.status_code == 403


async def test_customer_contacts(client: AsyncClient, admin_token: str) -> None:
    customer = (
        await client.post("/api/v1/customers", headers=auth(admin_token), json=_customer())
    ).json()
    dg2 = next(p for p in customer["delivery_points"] if p["code"] == "DG2")
    url = f"/api/v1/customers/{customer['id']}/contacts"

    owner = await client.post(
        url, headers=auth(admin_token), json={"name": "Chủ đại lý", "phone": "+84 912.000.001"}
    )
    assert owner.status_code == 201, owner.text
    assert owner.json()["phone"] == "0912000001"  # chuẩn hóa SĐT
    assert owner.json()["delivery_point_id"] is None
    point = await client.post(
        url,
        headers=auth(admin_token),
        json={"name": "Thủ kho", "phone": "0912000001", "delivery_point_id": dg2["id"]},
    )
    assert point.status_code == 201  # cùng SĐT nhưng khác phạm vi (chủ / điểm giao)
    assert point.json()["delivery_point_code"] == "DG2"

    # Trùng SĐT trong cùng phạm vi, SĐT sai, điểm giao của khách hàng khác → từ chối.
    dup = await client.post(
        url, headers=auth(admin_token), json={"name": "X", "phone": "0912000001"}
    )
    assert dup.status_code == 409
    bad = await client.post(url, headers=auth(admin_token), json={"name": "X", "phone": "12345"})
    assert bad.status_code == 422
    other = (
        await client.post(
            "/api/v1/customers", headers=auth(admin_token), json=_customer(code="KH002")
        )
    ).json()
    resp = await client.post(
        url,
        headers=auth(admin_token),
        json={
            "name": "X",
            "phone": "0912000009",
            "delivery_point_id": other["delivery_points"][0]["id"],
        },
    )
    assert resp.json()["error"]["code"] == "invalid_delivery_point"

    contact_url = f"{url}/{point.json()['id']}"
    resp = await client.put(
        contact_url,
        headers=auth(admin_token),
        json={"name": "Thủ kho mới", "phone": "0912000002", "delivery_point_id": dg2["id"]},
    )
    assert resp.json()["name"] == "Thủ kho mới"
    # Liên hệ của khách hàng khác không sửa được qua URL của khách hàng này.
    resp = await client.put(
        f"/api/v1/customers/{other['id']}/contacts/{point.json()['id']}",
        headers=auth(admin_token),
        json={"name": "X", "phone": "0912000003"},
    )
    assert resp.status_code == 404

    contacts = (await client.get(url, headers=auth(admin_token))).json()
    assert [c["name"] for c in contacts] == ["Chủ đại lý", "Thủ kho mới"]  # chủ trước
    assert (await client.delete(contact_url, headers=auth(admin_token))).status_code == 204
    assert len((await client.get(url, headers=auth(admin_token))).json()) == 1
