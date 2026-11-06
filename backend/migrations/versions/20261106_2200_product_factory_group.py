"""Mặt hàng: nhà máy, nhóm sản phẩm

Revision ID: 3d8f2b6a1c47
Revises: 7a1c0e5d9b21
Create Date: 2026-11-06 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3d8f2b6a1c47"
down_revision: str | None = "7a1c0e5d9b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("factory", sa.String(length=128), nullable=True))
    op.add_column("products", sa.Column("product_group", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "product_group")
    op.drop_column("products", "factory")
