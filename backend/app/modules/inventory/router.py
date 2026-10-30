import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.core.auth import OfficeStaffDep
from app.core.db import DbSession
from app.core.schemas import Page, PageParams, count_rows, page_params
from app.modules.inventory.models import InventoryBalance
from app.modules.master_data.models import Product, Warehouse

router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryOut(BaseModel):
    warehouse_id: uuid.UUID
    warehouse_code: str
    product_id: uuid.UUID
    product_code: str
    product_name: str
    uom: str
    qty_on_hand: Decimal
    synced_at: datetime


@router.get("")
async def list_inventory(
    _: OfficeStaffDep,
    session: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[InventoryOut]:
    stmt = (
        select(InventoryBalance, Warehouse, Product)
        .join(Warehouse, Warehouse.id == InventoryBalance.warehouse_id)
        .join(Product, Product.id == InventoryBalance.product_id)
        .order_by(Warehouse.code, Product.code)
    )
    if warehouse_id:
        stmt = stmt.where(InventoryBalance.warehouse_id == warehouse_id)
    if params.q:
        pattern = f"%{params.q.strip()}%"
        stmt = stmt.where(or_(Product.code.ilike(pattern), Product.name.ilike(pattern)))
    total = await count_rows(session, stmt)
    rows = await session.execute(stmt.limit(params.limit).offset(params.offset))
    items = [
        InventoryOut(
            warehouse_id=w.id,
            warehouse_code=w.code,
            product_id=p.id,
            product_code=p.code,
            product_name=p.name,
            uom=p.uom,
            qty_on_hand=b.qty_on_hand,
            synced_at=b.synced_at,
        )
        for b, w, p in rows
    ]
    return Page(items=items, total=total)
