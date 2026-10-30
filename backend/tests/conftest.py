import os

# Phải đặt trước khi import app (engine được tạo lúc import).
os.environ.setdefault("TMS_ENV", "test")
os.environ.setdefault(
    "TMS_DATABASE_URL", "postgresql+asyncpg://tms_app:tms_app@localhost:55432/tms_test"
)
os.environ.setdefault(
    "TMS_MIGRATION_DATABASE_URL",
    "postgresql+asyncpg://tms_owner:tms_owner@localhost:55432/tms_test",
)

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

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
