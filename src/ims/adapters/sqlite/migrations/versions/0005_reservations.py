"""Reservations, the per-asset booking ledger, and the reservation a deployment fulfils.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ID = 36


def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(ID), nullable=False),
        sa.Column("asset_ids", sa.Text(), nullable=False),
        sa.Column("kit_ids", sa.Text(), nullable=False),
        sa.Column("starts_on", sa.String(10), nullable=False),
        sa.Column("ends_on", sa.String(10), nullable=False),
        sa.Column("gcp_quantity", sa.Integer(), nullable=False),
        sa.Column("gcp_site_id", sa.String(ID), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(ID), nullable=False),
        sa.Column("requested_at", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(ID), nullable=True),
        sa.Column("decided_at", sa.String(32), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=False),
        sa.Column("deployment_id", sa.String(ID), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_reservations_project_id_projects"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reservations"),
    )
    op.create_index("ix_reservations_project_id", "reservations", ["project_id"])

    op.create_table(
        "booking_events",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("asset_id", sa.String(ID), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("change", sa.String(16), nullable=False),
        sa.Column("reservation_id", sa.String(ID), nullable=False),
        sa.Column("project_id", sa.String(ID), nullable=False),
        sa.Column("starts_on", sa.String(10), nullable=False),
        sa.Column("ends_on", sa.String(10), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("command_id", sa.String(ID), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_booking_events_asset_id_assets"
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name="fk_booking_events_reservation_id_reservations",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_booking_events"),
        sa.UniqueConstraint("asset_id", "sequence", name="uq_booking_events_asset_id_sequence"),
    )

    with op.batch_alter_table("deployments") as batch:
        batch.add_column(sa.Column("reservation_id", sa.String(ID), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("deployments") as batch:
        batch.drop_column("reservation_id")
    op.drop_table("booking_events")
    op.drop_table("reservations")
