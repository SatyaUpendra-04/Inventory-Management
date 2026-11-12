"""Battery limits, battery checks and GNSS calibration records.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

ID = 36


def upgrade() -> None:
    op.create_table(
        "battery_policies",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("item_type_id", sa.String(ID), nullable=False),
        sa.Column("cycle_limit", sa.Integer(), nullable=False),
        sa.Column("health_floor", sa.Integer(), nullable=False),
        sa.Column("idle_days", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_type_id"], ["item_types.id"], name="fk_battery_policies_item_type_id_item_types"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_battery_policies"),
        sa.UniqueConstraint("item_type_id", name="uq_battery_policies_item_type_id"),
    )

    op.create_table(
        "battery_checks",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("checked_on", sa.String(10), nullable=False),
        sa.Column("health_pct", sa.Integer(), nullable=True),
        sa.Column("internal_resistance_mohm", sa.String(16), nullable=True),
        sa.Column("cell_imbalance_mv", sa.Integer(), nullable=True),
        sa.Column("swelling", sa.Boolean(), nullable=False),
        sa.Column("damage", sa.Boolean(), nullable=False),
        sa.Column("charge_state", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_battery_checks_asset_id_assets"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_battery_checks"),
        sa.UniqueConstraint("asset_id", "sequence", name="uq_battery_checks_asset_id_sequence"),
    )

    op.create_table(
        "calibration_records",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("done_on", sa.String(10), nullable=False),
        sa.Column("method", sa.String(200), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("horizontal_mm", sa.String(16), nullable=True),
        sa.Column("vertical_mm", sa.String(16), nullable=True),
        sa.Column("valid_until", sa.String(10), nullable=True),
        sa.Column("document_id", sa.String(ID), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_calibration_records_asset_id_assets"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calibration_records"),
        sa.UniqueConstraint(
            "asset_id", "sequence", name="uq_calibration_records_asset_id_sequence"
        ),
    )


def downgrade() -> None:
    for table in ("calibration_records", "battery_checks", "battery_policies"):
        op.drop_table(table)
