"""Import tồn kho dạng snapshot: mỗi kho có trong file được thay toàn bộ số tồn."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from pydantic import Field
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.importing import (
    ApplyResult,
    Column,
    ImportContext,
    ImportSpec,
    ParsedRow,
    RowError,
    RowModel,
    duplicate_errors,
    load_by_codes,
)
from app.core.parsing import Code, Num
from app.modules.identity.models import CompanyRole
from app.modules.inventory.models import InventoryBalance
from app.modules.master_data.models import Product, Warehouse


class InventoryRow(RowModel):
    ma_kho: Code
    ma_hang: Code
    so_luong_ton: Annotated[Num, Field(ge=0)]


async def apply_inventory(
    session: AsyncSession, ctx: ImportContext, rows: Sequence[ParsedRow[InventoryRow]]
) -> ApplyResult:
    result = ApplyResult(
        errors=duplicate_errors(rows, lambda r: (r.ma_kho.lower(), r.ma_hang.lower()), "Mã hàng")
    )
    warehouses = await load_by_codes(session, Warehouse, (r.data.ma_kho for r in rows))
    products = await load_by_codes(session, Product, (r.data.ma_hang for r in rows))
    for row in rows:
        if row.data.ma_kho.lower() not in warehouses:
            result.errors.append(
                RowError(row.row_no, "Mã kho", f"Kho '{row.data.ma_kho}' không tồn tại")
            )
        if row.data.ma_hang.lower() not in products:
            result.errors.append(
                RowError(row.row_no, "Mã hàng", f"Mặt hàng '{row.data.ma_hang}' không tồn tại")
            )
    if result.errors:
        return result

    synced_at = datetime.now(UTC)
    warehouse_ids = {warehouses[r.data.ma_kho.lower()].id for r in rows}
    await session.execute(
        delete(InventoryBalance).where(InventoryBalance.warehouse_id.in_(warehouse_ids))
    )
    session.add_all(
        InventoryBalance(
            company_id=ctx.company_id,
            warehouse_id=warehouses[r.data.ma_kho.lower()].id,
            product_id=products[r.data.ma_hang.lower()].id,
            qty_on_hand=r.data.so_luong_ton,
            synced_at=synced_at,
        )
        for r in rows
    )
    result.created = len(rows)
    return result


INVENTORY = ImportSpec(
    kind="inventory",
    title="Tồn kho",
    description=(
        "Snapshot tồn kho: với mỗi kho xuất hiện trong file, toàn bộ số tồn cũ của kho đó được "
        "thay bằng dữ liệu trong file (mặt hàng không có trong file coi như tồn 0)."
    ),
    columns=[
        Column("ma_kho", "Mã kho", True, "KHO01"),
        Column("ma_hang", "Mã hàng", True, "SUA-TT-180"),
        Column("so_luong_ton", "Số lượng tồn", True, 350, "Theo đơn vị tính của mặt hàng"),
    ],
    row_model=InventoryRow,
    apply=apply_inventory,
    allowed_roles=frozenset({CompanyRole.COMPANY_ADMIN, CompanyRole.MANAGER}),
)
