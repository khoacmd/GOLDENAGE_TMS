from typing import Annotated

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class Page[T](BaseModel):
    items: list[T]
    total: int


class PageParams(BaseModel):
    q: str | None = None
    limit: int = 50
    offset: int = 0


def page_params(
    q: Annotated[str | None, Query(description="Tìm theo mã/tên")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageParams:
    return PageParams(q=q, limit=limit, offset=offset)


async def paginate[M](
    session: AsyncSession, stmt: Select[M], params: PageParams
) -> tuple[list[M], int]:
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = await session.scalars(stmt.limit(params.limit).offset(params.offset))
    return list(items), total or 0
