import os

# Phải đặt trước khi import app (engine được tạo lúc import).
os.environ.setdefault("TMS_ENV", "test")
os.environ.setdefault("TMS_STORAGE_BACKEND", "memory")
os.environ.setdefault("TMS_TASKS_EAGER", "true")
os.environ.setdefault("TMS_PLANNING_TIME_CAP_S", "1")
os.environ.setdefault("TMS_ZALO_MOCK", "true")  # token Zalo giả "mock:<id>:<tên>"
os.environ.setdefault(
    "TMS_DATABASE_URL", "postgresql+asyncpg://tms_app:tms_app@localhost:55432/tms_test"
)
os.environ.setdefault(
    "TMS_MIGRATION_DATABASE_URL",
    "postgresql+asyncpg://tms_owner:tms_owner@localhost:55432/tms_test",
)

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core import revocation, throttle
from app.core.config import get_settings
from app.core.db import SessionFactory
from app.main import app
from app.modules.identity import service as identity_service

SYSADMIN = {"username": "sysadmin", "password": "sysadmin-pass"}


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> Iterator[None]:
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session")
async def owner_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().migration_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with owner_engine.begin() as conn:
        await conn.execute(text("TRUNCATE companies, users CASCADE"))


@pytest.fixture(autouse=True)
async def _reset_login_throttle() -> None:
    await throttle.clear()
    await revocation.clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def sysadmin_token(client: AsyncClient) -> str:
    async with SessionFactory() as session:
        await identity_service.create_user(
            session, full_name="System Admin", is_system_admin=True, **SYSADMIN
        )
        await session.commit()
    resp = await client.post("/api/v1/auth/login", json=SYSADMIN)
    assert resp.status_code == 200, resp.text
    token: str = resp.json()["access_token"]
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_company(
    client: AsyncClient, sysadmin_token: str, code: str, admin_username: str
) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/admin/companies",
        headers=auth(sysadmin_token),
        json={
            "code": code,
            "name": f"Công ty {code}",
            "admin": {
                "username": admin_username,
                "password": "admin-pass-123",
                "full_name": f"Admin {code}",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    company: dict[str, str] = resp.json()
    return company


async def login(client: AsyncClient, username: str, password: str, **extra: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password, **extra}
    )
    assert resp.status_code == 200, resp.text
    token: str = resp.json()["access_token"]
    return token


@pytest.fixture
async def admin_token(client: AsyncClient, sysadmin_token: str) -> str:
    """Token admin của công ty NPP01."""
    await create_company(client, sysadmin_token, "NPP01", "admin01")
    return await login(client, "admin01", "admin-pass-123")


WAREHOUSE = {
    "code": "KHO01",
    "name": "Kho Hà Đông",
    "address": "Hà Đông, Hà Nội",
    "latitude": "20.971000",
    "longitude": "105.776000",
}


async def create_warehouse(client: AsyncClient, token: str, **overrides: str) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/warehouses", headers=auth(token), json={**WAREHOUSE, **overrides}
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


# --- Môi trường điều phối: dữ liệu mẫu + quản lý, thủ kho, lái xe ---------------------------

PLAN_DATE = "2026-11-02"  # Thứ 2, ngày giao của đơn mẫu
SAMPLES = Path(__file__).parents[2] / "docs" / "samples"
KINDS = [
    "warehouses",
    "vehicles",
    "products",
    "customers",
    "inventory",
    "orders",
    "customer_contacts",
]


@dataclass
class Env:
    admin: str
    manager: str
    keeper: str
    driver_token: str
    driver_id: str
    assistant_id: str
    vehicles: dict[str, str]
    warehouses: dict[str, str]
    parts: dict[tuple[str, str], dict[str, Any]]  # (số đơn, DRY/COLD) → phần đơn


async def create_user(client: AsyncClient, admin: str, username: str, roles: list[str]) -> str:
    resp = await client.post(
        "/api/v1/users",
        headers=auth(admin),
        json={
            "username": username,
            "full_name": username,
            "password": "password-123",
            "roles": roles,
        },
    )
    assert resp.status_code == 201, resp.text
    user_id: str = resp.json()["id"]
    return user_id


@pytest.fixture
async def env(client: AsyncClient, admin_token: str) -> Env:
    for path, kind in zip(sorted(SAMPLES.glob("*.csv")), KINDS, strict=True):
        resp = await client.post(
            f"/api/v1/imports/{kind}",
            headers=auth(admin_token),
            files={"file": (path.name, path.read_bytes())},
        )
        assert resp.json()["status"] == "SUCCEEDED", resp.json()["errors"]
    await create_user(client, admin_token, "quanly", ["manager"])
    await create_user(client, admin_token, "thukho", ["warehouse_keeper"])
    driver_id = await create_user(client, admin_token, "laixe1", ["driver"])
    assistant_id = await create_user(client, admin_token, "phuxe1", ["driver"])
    manager = await login(client, "quanly", "password-123")
    vehicles = (await client.get("/api/v1/vehicles", headers=auth(manager))).json()["items"]
    warehouses = (await client.get("/api/v1/warehouses", headers=auth(manager))).json()["items"]
    parts = (
        await client.get(
            f"/api/v1/trips/available-parts?plan_date={PLAN_DATE}", headers=auth(manager)
        )
    ).json()
    return Env(
        admin=admin_token,
        manager=manager,
        keeper=await login(client, "thukho", "password-123"),
        driver_token=await login(client, "laixe1", "password-123"),
        driver_id=driver_id,
        assistant_id=assistant_id,
        vehicles={v["code"]: v["id"] for v in vehicles},
        warehouses={w["code"]: w["id"] for w in warehouses},
        parts={(p["external_ref"], p["temp_group"]): p for p in parts},
    )


def stop(env: Env, *keys: tuple[str, str]) -> dict[str, Any]:
    parts = [env.parts[k] for k in keys]
    return {
        "delivery_point_id": parts[0]["delivery_point_id"],
        "order_part_ids": [p["id"] for p in parts],
    }


def trip_body(
    env: Env, vehicle: str, warehouse: str, stops: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {
        "plan_date": PLAN_DATE,
        "vehicle_id": env.vehicles[vehicle],
        "warehouse_id": env.warehouses[warehouse],
        "driver_id": env.driver_id,
        "stops": stops,
        **extra,
    }


async def zalo_activate(
    client: AsyncClient, admin: str, issue_url: str, zalo_id: str, name: str = "Zalo"
) -> dict[str, Any]:
    """Admin cấp mã rồi Zalo (giả lập) nhập mã → kết quả đăng nhập."""
    code = (await client.post(issue_url, headers=auth(admin))).json()["code"]
    resp = await client.post(
        "/api/v1/auth/zalo/activate",
        json={"access_token": f"mock:{zalo_id}:{name}", "code": code},
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body
