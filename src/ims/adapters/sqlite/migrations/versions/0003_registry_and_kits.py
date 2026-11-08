"""Configuration, asset documents, firmware, kit templates, kits, reorder levels,
and a home site on assets.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ID = 36


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch:
        batch.add_column(sa.Column("home_site_id", sa.String(ID), nullable=True))

    op.create_table(
        "configuration_events",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("component_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("change", sa.String(16), nullable=False),
        sa.Column("parent_id", sa.String(ID), nullable=False),
        sa.Column("position", sa.String(40), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["component_id"], ["assets.id"], name="fk_configuration_events_component_id_assets"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["assets.id"], name="fk_configuration_events_parent_id_assets"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_configuration_events"),
        sa.UniqueConstraint(
            "component_id", "sequence", name="uq_configuration_events_component_id_sequence"
        ),
    )
    op.create_index("ix_configuration_events_parent_id", "configuration_events", ["parent_id"])

    op.create_table(
        "asset_documents",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("reference", sa.String(80), nullable=False),
        sa.Column("issuer", sa.String(100), nullable=False),
        sa.Column("issued_on", sa.String(10), nullable=True),
        sa.Column("valid_until", sa.String(10), nullable=True),
        sa.Column("file", sa.String(80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_asset_documents_asset_id_assets"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_asset_documents"),
    )
    op.create_index("ix_asset_documents_asset_id", "asset_documents", ["asset_id"])

    op.create_table(
        "firmware_records",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("installed_on", sa.String(10), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_firmware_records_asset_id_assets"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_firmware_records"),
        sa.UniqueConstraint("asset_id", "sequence", name="uq_firmware_records_asset_id_sequence"),
    )

    op.create_table(
        "kit_templates",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("name_key", sa.String(60), nullable=False),
        sa.Column("discipline", sa.String(16), nullable=False),
        sa.Column("lines", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_kit_templates"),
        sa.UniqueConstraint("name_key", name="uq_kit_templates_name_key"),
    )

    op.create_table(
        "kits",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("template_id", sa.String(ID), nullable=True),
        sa.Column("members", sa.Text(), nullable=False),
        sa.Column("home_site_id", sa.String(ID), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_kits"),
        sa.UniqueConstraint("code", name="uq_kits_code"),
    )

    op.create_table(
        "reorder_levels",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("item_type_id", sa.String(ID), nullable=False),
        sa.Column("location_id", sa.String(ID), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_type_id"], ["item_types.id"], name="fk_reorder_levels_item_type_id_item_types"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reorder_levels"),
        sa.UniqueConstraint(
            "item_type_id", "location_id", name="uq_reorder_levels_item_type_id_location_id"
        ),
    )


def downgrade() -> None:
    for table in (
        "reorder_levels",
        "kits",
        "kit_templates",
        "firmware_records",
        "asset_documents",
        "configuration_events",
    ):
        op.drop_table(table)
    with op.batch_alter_table("assets") as batch:
        batch.drop_column("home_site_id")
