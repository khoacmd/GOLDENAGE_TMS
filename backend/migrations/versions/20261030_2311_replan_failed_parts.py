"""replan failed parts

Revision ID: afa59144d769
Revises: 185122ec0e21
Create Date: 2026-10-30 23:11:57.679224

"""

from typing import Sequence, Union

from alembic import op
import geoalchemy2  # noqa: F401  (cột geography do autogenerate sinh ra)
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "afa59144d769"
down_revision: Union[str, Sequence[str], None] = "185122ec0e21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _recreate(where: str) -> None:
    op.drop_index("uq_trip_items_active_part", table_name="trip_items")
    op.create_index(
        "uq_trip_items_active_part",
        "trip_items",
        ["order_part_id"],
        unique=True,
        postgresql_where=sa.text(where),
    )


def upgrade() -> None:
    """Item giao thất bại không còn giữ phần đơn → xếp lại được."""
    _recreate("order_part_id IS NOT NULL AND status IN ('PENDING', 'SUCCESS')")


def downgrade() -> None:
    _recreate("order_part_id IS NOT NULL AND status <> 'CANCELLED'")
