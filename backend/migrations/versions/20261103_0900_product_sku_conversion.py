"""product sku conversion

Revision ID: 646b848ddd1e
Revises: eaf1ec75f6ca
Create Date: 2026-11-03 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "646b848ddd1e"
down_revision: Union[str, Sequence[str], None] = "eaf1ec75f6ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Dữ liệu cũ: SKU trùng đơn vị tính, quy đổi 1 = 1; tồn kho, số lượng, khối lượng giữ nguyên số."""
    op.add_column("products", sa.Column("sku_uom", sa.String(length=32), nullable=True))
    op.add_column(
        "products",
        sa.Column("sku_ratio", sa.Numeric(10, 3), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("uom_ratio", sa.Numeric(10, 3), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_products_sku_conversion_positive"),
        "products",
        "sku_ratio > 0 AND uom_ratio > 0",
    )
    op.add_column("sales_order_lines", sa.Column("sku_qty", sa.Numeric(14, 3), nullable=True))
    op.add_column("sales_order_lines", sa.Column("sku_uom", sa.String(length=32), nullable=True))
    op.add_column("sales_order_lines", sa.Column("uom", sa.String(length=32), nullable=True))
    op.add_column(
        "sales_order_lines",
        sa.Column("sku_ratio", sa.Numeric(10, 3), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("uom_ratio", sa.Numeric(10, 3), server_default=sa.text("1"), nullable=False),
    )

    # Cập nhật mọi công ty: FORCE RLS chặn cả owner khi chưa đặt context công ty, UPDATE sẽ không
    # đụng dòng nào. Tạm bỏ FORCE trong transaction của migration.
    for table in ("products", "sales_order_lines"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE products SET sku_uom = uom")
    op.execute(
        "UPDATE sales_order_lines l SET sku_qty = l.qty, sku_uom = p.uom, uom = p.uom "
        "FROM products p WHERE p.id = l.product_id"
    )
    for table in ("products", "sales_order_lines"):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.alter_column("products", "sku_uom", nullable=False)
    op.alter_column("sales_order_lines", "sku_qty", nullable=False)
    op.alter_column("sales_order_lines", "sku_uom", nullable=False)
    op.alter_column("sales_order_lines", "uom", nullable=False)
    op.alter_column("sales_order_lines", "sku_ratio", server_default=None)
    op.alter_column("sales_order_lines", "uom_ratio", server_default=None)
    op.alter_column(
        "sales_order_lines",
        "qty",
        new_column_name="uom_qty",
        existing_type=sa.Numeric(14, 3),
        type_=sa.Numeric(18, 6),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "sales_order_lines",
        "uom_qty",
        new_column_name="qty",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(14, 3),
        existing_nullable=False,
    )
    op.drop_column("sales_order_lines", "uom_ratio")
    op.drop_column("sales_order_lines", "sku_ratio")
    op.drop_column("sales_order_lines", "uom")
    op.drop_column("sales_order_lines", "sku_uom")
    op.drop_column("sales_order_lines", "sku_qty")
    op.drop_constraint(op.f("ck_products_sku_conversion_positive"), "products", type_="check")
    op.drop_column("products", "uom_ratio")
    op.drop_column("products", "sku_ratio")
    op.drop_column("products", "sku_uom")
