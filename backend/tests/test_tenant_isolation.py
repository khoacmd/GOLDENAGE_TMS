import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import SessionFactory, set_tenant_context
from app.modules.identity.models import UserRole
from app.modules.tenancy.models import CompanySettings
from tests.conftest import create_company


async def test_rls_filters_by_company(client: AsyncClient, sysadmin_token: str) -> None:
    a = await create_company(client, sysadmin_token, "NPPA", "admin_a")
    b = await create_company(client, sysadmin_token, "NPPB", "admin_b")

    async with SessionFactory() as session:
        # Không có context → không thấy gì.
        assert (await session.scalars(select(CompanySettings))).all() == []

        await set_tenant_context(session, company_id=uuid.UUID(a["id"]), user_id=None)
        settings = (await session.scalars(select(CompanySettings))).all()
        assert [str(s.company_id) for s in settings] == [a["id"]]
        roles = (await session.scalars(select(UserRole))).all()
        assert {str(r.company_id) for r in roles} == {a["id"]}

        # Context tồn tại qua commit (được áp lại ở transaction mới).
        await session.commit()
        settings = (await session.scalars(select(CompanySettings))).all()
        assert [str(s.company_id) for s in settings] == [a["id"]]

        # Ghi dữ liệu cho công ty khác bị chặn (WITH CHECK).
        session.add(CompanySettings(company_id=uuid.UUID(b["id"])))
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.flush()
        await session.rollback()


async def test_every_tenant_table_has_forced_rls(owner_engine: AsyncEngine) -> None:
    """Bảng nào có cột company_id đều phải bật và FORCE RLS."""
    async with owner_engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'company_id'
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                """
            )
        )
        tables = rows.all()
    assert tables, "Không tìm thấy bảng theo công ty nào"
    missing = [t.relname for t in tables if not (t.relrowsecurity and t.relforcerowsecurity)]
    assert missing == []
