"""Quy định lưu hành theo vùng: vùng hạn chế, quy tắc, văn bản chấp thuận, thông tin xe

Revision ID: 7a1c0e5d9b21
Revises: 646b848ddd1e
Create Date: 2026-11-04 20:00:00.000000
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import enable_tenant_rls

revision: str = "7a1c0e5d9b21"
down_revision: str | None = "646b848ddd1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Như `enum_type`: VARCHAR + CHECK, không dùng enum native.
VEHICLE_CLASS = sa.Enum(
    "TRUCK",
    "VAN",
    "PICKUP",
    "MOTORBIKE",
    name="vehicleclass",
    native_enum=False,
    create_constraint=True,
    length=32,
)
WEIGHT_BASIS = sa.Enum(
    "PAYLOAD", "GROSS", name="weightbasis", native_enum=False, create_constraint=True, length=32
)
REGULATORY_CLASS = sa.Enum(
    "TRUCK",
    "VAN",
    "PICKUP",
    name="regulatoryclass",
    native_enum=False,
    create_constraint=True,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "traffic_zones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "boundary",
            geoalchemy2.Geography("POLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("legal_ref", sa.String(255)),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_traffic_zones_boundary", "traffic_zones", ["boundary"], postgresql_using="gist"
    )
    op.create_table(
        "traffic_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "zone_id",
            sa.Uuid(),
            sa.ForeignKey("traffic_zones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_class",
            VEHICLE_CLASS,
            nullable=False,
        ),
        sa.Column("weight_basis", WEIGHT_BASIS, nullable=False),
        sa.Column("min_kg", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_kg", sa.Numeric(10, 2)),
        sa.Column("max_inclusive", sa.Boolean(), nullable=False),
        sa.Column("windows", postgresql.JSONB()),
    )
    op.create_index("ix_traffic_rules_zone_id", "traffic_rules", ["zone_id"])

    op.create_table(
        "vehicle_permits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            sa.Uuid(),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "zone_id",
            sa.Uuid(),
            sa.ForeignKey("traffic_zones.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("document_no", sa.String(64), nullable=False),
        sa.Column("issuer", sa.String(255)),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("windows", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("company_id", "vehicle_id", "zone_id", "document_no"),
    )
    op.create_index("ix_vehicle_permits_company_id", "vehicle_permits", ["company_id"])
    op.create_index("ix_vehicle_permits_vehicle_id", "vehicle_permits", ["vehicle_id"])
    for stmt in enable_tenant_rls("vehicle_permits"):
        op.execute(stmt)

    op.add_column("vehicles", sa.Column("gross_weight_kg", sa.Numeric(10, 2)))
    op.add_column(
        "vehicles",
        sa.Column("regulatory_class", REGULATORY_CLASS),
    )
    for table in ("warehouses", "delivery_points"):
        op.add_column(
            table,
            sa.Column(
                "traffic_zone_exempt", sa.Boolean(), server_default=sa.text("false"), nullable=False
            ),
        )
    op.add_column(
        "company_settings",
        sa.Column(
            "traffic_rules_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "company_settings",
        sa.Column(
            "traffic_zone_buffer_minutes",
            sa.Integer(),
            server_default=sa.text("15"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("company_settings", "traffic_zone_buffer_minutes")
    op.drop_column("company_settings", "traffic_rules_enabled")
    op.drop_column("delivery_points", "traffic_zone_exempt")
    op.drop_column("warehouses", "traffic_zone_exempt")
    op.drop_column("vehicles", "regulatory_class")
    op.drop_column("vehicles", "gross_weight_kg")
    op.drop_table("vehicle_permits")
    op.drop_table("traffic_rules")
    op.drop_table("traffic_zones")
