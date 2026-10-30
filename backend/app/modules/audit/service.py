import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


def record(
    session: AsyncSession,
    company_id: uuid.UUID,
    entity: str,
    entity_id: uuid.UUID,
    action: str,
    user_id: uuid.UUID | None,
    **data: Any,
) -> None:
    session.add(
        AuditLog(
            company_id=company_id,
            entity=entity,
            entity_id=entity_id,
            action=action,
            user_id=user_id,
            data={
                k: (str(v) if not isinstance(v, str | int | float | bool | None) else v)
                for k, v in data.items()
            },
        )
    )


async def history(session: AsyncSession, entity: str, entity_id: uuid.UUID) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity == entity, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at)
    )
    return list(await session.scalars(stmt))
