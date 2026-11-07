import base64

import pytest
from httpx import AsyncClient

from tests.conftest import Env, auth, stop, trip_body

# PNG 1x1 hợp lệ.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


async def test_delivery_notes_one_per_order(client: AsyncClient, env: Env) -> None:
    first = stop(env, ("DH2610-001", "COLD"), ("DH2610-001", "DRY"))
    first["adhoc_items"] = [{"description": "Kệ trưng bày", "weight_kg": "5"}]
    body = trip_body(env, "XE02", "KHO01", [first, stop(env, ("DH2610-007", "DRY"))])
    trip = (await client.post("/api/v1/trips", headers=auth(env.manager), json=body)).json()

    resp = await client.get(f"/api/v1/trips/{trip['id']}/delivery-notes", headers=auth(env.keeper))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["trip"]["code"] == trip["code"] and data["vehicle_plate"]
    assert [(n["stop_seq"], n["order_ref"]) for n in data["notes"]] == [
        (1, "DH2610-001"),
        (1, None),
        (2, "DH2610-007"),
    ]
    order, adhoc, other = data["notes"]
    # Đơn có cả phần khô và lạnh: 1 phiếu, đủ dòng của 2 phần.
    assert {line["temp_group"] for line in order["lines"]} == {"DRY", "COLD"}
    assert float(order["total_weight_kg"]) == pytest.approx(111 + 184)
    assert order["customer_code"] == "KH001" and order["address"]
    assert adhoc["adhoc_items"] == ["Kệ trưng bày (5 kg)"] and adhoc["lines"] == []
    assert other["lines"] and other["customer_code"] != "KH001"


async def test_print_profile_and_logo(client: AsyncClient, env: Env) -> None:
    url = "/api/v1/company/print-profile"
    profile = (await client.get(url, headers=auth(env.keeper))).json()
    assert profile["logo"] is None and profile["delivery_header"] is None
    assert profile["company_name"]

    body = {
        "delivery_header": "CÔNG TY A\nĐịa chỉ: Hà Nội",
        "delivery_footer": "Hotline 1900",
        "picking_header": "  ",
    }
    assert (await client.put(url, headers=auth(env.manager), json=body)).status_code == 403
    resp = await client.put(url, headers=auth(env.admin), json=body)
    assert resp.status_code == 200, resp.text
    saved = resp.json()
    assert saved["delivery_header"] == "CÔNG TY A\nĐịa chỉ: Hà Nội"
    assert saved["picking_header"] is None  # chỉ có khoảng trắng = mặc định

    logo_url = "/api/v1/company/logo"
    resp = await client.put(
        logo_url, headers=auth(env.admin), files={"file": ("logo.png", PNG, "image/png")}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["logo"] == "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert (await client.get(url, headers=auth(env.manager))).json()["logo"].startswith("data:")

    for name, content, ctype in (
        ("logo.gif", b"GIF89a", "image/gif"),
        ("big.png", b"x" * (512 * 1024 + 1), "image/png"),
    ):
        resp = await client.put(
            logo_url, headers=auth(env.admin), files={"file": (name, content, ctype)}
        )
        assert resp.json()["error"]["code"] == "invalid_logo"

    resp = await client.delete(logo_url, headers=auth(env.admin))
    assert resp.status_code == 200 and resp.json()["logo"] is None
    assert resp.json()["delivery_footer"] == "Hotline 1900"
