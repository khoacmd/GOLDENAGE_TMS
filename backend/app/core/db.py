import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, SessionTransaction

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

_TENANT_KEY = "tenant_context"
_SET_CONTEXT_SQL = text(
    "SELECT set_config('app.company_id', :company_id, true), "
    "set_config('app.user_id', :user_id, true)"
)


def _context_params(session: Session) -> dict[str, str]:
    company_id, user_id = session.info.get(_TENANT_KEY, (None, None))
    return {"company_id": str(company_id or ""), "user_id": str(user_id or "")}


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(
    session: Session, _transaction: SessionTransaction, connection: Connection
) -> None:
    # set_config(..., true) chỉ sống trong transaction → áp lại mỗi khi transaction mới bắt đầu
    # (ví dụ sau commit), để RLS luôn nhận đúng công ty.
    if _TENANT_KEY in session.info:
        connection.execute(_SET_CONTEXT_SQL, _context_params(session))


async def set_tenant_context(
    session: AsyncSession, *, company_id: uuid.UUID | None, user_id: uuid.UUID | None
) -> None:
    session.info[_TENANT_KEY] = (company_id, user_id)
    if session.in_transaction():
        await session.execute(_SET_CONTEXT_SQL, _context_params(session.sync_session))


async def get_db() -> AsyncIterator[AsyncSession]:
    """Session theo request. Route ghi dữ liệu phải tự gọi `await session.commit()`."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]
