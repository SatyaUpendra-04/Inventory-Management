"""Initial schema: users, catalogue, assets, ledgers, audit and command log.

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ID = 36


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("employee_id", sa.String(20), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("licence_number", sa.String(40), nullable=True),
        sa.Column("licence_expires_on", sa.String(10), nullable=True),
        sa.Column("profile_picture", sa.String(260), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("employee_id", name="uq_users_employee_id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "item_types",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("discipline", sa.String(16), nullable=False),
        sa.Column("tracking", sa.String(16), nullable=False),
        sa.Column("meters", sa.String(64), nullable=False),
        sa.Column("is_component", sa.Boolean(), nullable=False),
        sa.Column("tag_prefix", sa.String(4), nullable=True),
        sa.Column("tracks_warranty", sa.Boolean(), nullable=False),
        sa.Column("tracks_calibration", sa.Boolean(), nullable=False),
        sa.Column("battery_family", sa.String(40), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_item_types"),
        sa.UniqueConstraint("code", name="uq_item_types_code"),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("item_type_id", sa.String(ID), nullable=False),
        sa.Column("asset_tag", sa.String(17), nullable=False),
        sa.Column("serial_number", sa.String(64), nullable=True),
        sa.Column("make", sa.String(60), nullable=True),
        sa.Column("model", sa.String(60), nullable=True),
        sa.Column("acquired_on", sa.String(10), nullable=True),
        sa.Column("warranty_until", sa.String(10), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_type_id"], ["item_types.id"], name="fk_assets_item_type_id_item_types"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("asset_tag", name="uq_assets_asset_tag"),
        sa.UniqueConstraint(
            "item_type_id", "serial_number", name="uq_assets_item_type_id_serial_number"
        ),
    )
    op.create_table(
        "status_events",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("before_serviceability", sa.String(16), nullable=False),
        sa.Column("before_custody", sa.String(16), nullable=False),
        sa.Column("after_serviceability", sa.String(16), nullable=False),
        sa.Column("after_custody", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("project_id", sa.String(ID), nullable=True),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_status_events_asset_id_assets"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_status_events"),
        sa.UniqueConstraint("asset_id", "sequence", name="uq_status_events_asset_id_sequence"),
    )
    op.create_table(
        "usage_entries",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("meter", sa.String(16), nullable=False),
        sa.Column("amount", sa.String(32), nullable=False),
        sa.Column("occurred_on", sa.String(10), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.Column("project_id", sa.String(ID), nullable=True),
        sa.Column("reverses", sa.String(ID), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_usage_entries_asset_id_assets"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usage_entries"),
        sa.UniqueConstraint("asset_id", "sequence", name="uq_usage_entries_asset_id_sequence"),
        sa.UniqueConstraint("reverses", name="uq_usage_entries_reverses"),
    )
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("item_type_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.String(ID), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.Column("project_id", sa.String(ID), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_type_id"], ["item_types.id"], name="fk_stock_movements_item_type_id_item_types"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stock_movements"),
        sa.UniqueConstraint(
            "item_type_id", "sequence", name="uq_stock_movements_item_type_id_sequence"
        ),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.Column("at", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(ID), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_entity_entity_id", "audit_log", ["entity", "entity_id"])
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    op.create_table(
        "command_log",
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.String(ID), nullable=True),
        sa.Column("completed_at", sa.String(32), nullable=False),
        sa.Column("result_id", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("command_id", name="pk_command_log"),
    )


def downgrade() -> None:
    for table in (
        "command_log",
        "audit_log",
        "stock_movements",
        "usage_entries",
        "status_events",
        "assets",
        "item_types",
        "users",
    ):
        op.drop_table(table)
