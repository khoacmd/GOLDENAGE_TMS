"""Lập kế hoạch: xe được chọn cho lần chạy

Revision ID: 5b2e9c4d7f10
Revises: 3d8f2b6a1c47
Create Date: 2026-11-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5b2e9c4d7f10"
down_revision: str | None = "3d8f2b6a1c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "planning_runs",
        sa.Column("vehicle_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("planning_runs", "vehicle_ids")
