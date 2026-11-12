"""Maintenance programme, maintenance records, defects and work orders.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ID = 36


def upgrade() -> None:
    op.create_table(
        "maintenance_tasks",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("item_type_id", sa.String(ID), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("every_hours", sa.String(16), nullable=True),
        sa.Column("every_cycles", sa.Integer(), nullable=True),
        sa.Column("every_landings", sa.Integer(), nullable=True),
        sa.Column("every_days", sa.Integer(), nullable=True),
        sa.Column("tolerance_hours", sa.String(16), nullable=False),
        sa.Column("tolerance_cycles", sa.Integer(), nullable=False),
        sa.Column("tolerance_landings", sa.Integer(), nullable=False),
        sa.Column("tolerance_days", sa.Integer(), nullable=False),
        sa.Column("life_limit", sa.Boolean(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_type_id"], ["item_types.id"], name="fk_maintenance_tasks_item_type_id_item_types"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_maintenance_tasks"),
    )

    op.create_table(
        "task_completions",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(ID), nullable=False),
        sa.Column("done_on", sa.String(10), nullable=False),
        sa.Column("meters", sa.Text(), nullable=False),
        sa.Column("work_order_id", sa.String(ID), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_task_completions_asset_id_assets"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["maintenance_tasks.id"],
            name="fk_task_completions_task_id_maintenance_tasks",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_task_completions"),
        sa.UniqueConstraint("asset_id", "sequence", name="uq_task_completions_asset_id_sequence"),
    )

    op.create_table(
        "defects",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(16), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reported_by", sa.String(ID), nullable=False),
        sa.Column("reported_at", sa.String(32), nullable=False),
        sa.Column("found_on", sa.String(10), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("limitation", sa.Text(), nullable=False),
        sa.Column("deferred_until", sa.String(10), nullable=True),
        sa.Column("assessed_by", sa.String(ID), nullable=True),
        sa.Column("assessed_at", sa.String(32), nullable=True),
        sa.Column("assessment_note", sa.Text(), nullable=False),
        sa.Column("work_order_id", sa.String(ID), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_defects_asset_id_assets"),
        sa.PrimaryKeyConstraint("id", name="pk_defects"),
        sa.UniqueConstraint("number", name="uq_defects_number"),
    )
    op.create_index("ix_defects_asset_id", "defects", ["asset_id"])

    op.create_table(
        "work_orders",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(16), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("task_ids", sa.Text(), nullable=False),
        sa.Column("defect_ids", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("opened_by", sa.String(ID), nullable=False),
        sa.Column("opened_at", sa.String(32), nullable=False),
        sa.Column("work_done", sa.Text(), nullable=False),
        sa.Column("parts", sa.Text(), nullable=False),
        sa.Column("completed_by", sa.String(ID), nullable=True),
        sa.Column("completed_at", sa.String(32), nullable=True),
        sa.Column("certified_by", sa.String(ID), nullable=True),
        sa.Column("certified_at", sa.String(32), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_work_orders_asset_id_assets"),
        sa.PrimaryKeyConstraint("id", name="pk_work_orders"),
        sa.UniqueConstraint("number", name="uq_work_orders_number"),
    )
    op.create_index("ix_work_orders_asset_id", "work_orders", ["asset_id"])


def downgrade() -> None:
    for table in ("work_orders", "defects", "task_completions", "maintenance_tasks"):
        op.drop_table(table)
