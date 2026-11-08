"""Projects, deployments, sorties and survey sessions.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ID = 36


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("site_id", sa.String(ID), nullable=False),
        sa.Column("client", sa.String(120), nullable=False),
        sa.Column("starts_on", sa.String(10), nullable=False),
        sa.Column("ends_on", sa.String(10), nullable=True),
        sa.Column("chief_pilot_id", sa.String(ID), nullable=True),
        sa.Column("surveyor_id", sa.String(ID), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.String(32), nullable=True),
        _fk("projects", "site_id", "sites"),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("code", name="uq_projects_code"),
    )

    op.create_table(
        "deployments",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(ID), nullable=False),
        sa.Column("asset_ids", sa.Text(), nullable=False),
        sa.Column("kit_ids", sa.Text(), nullable=False),
        sa.Column("crew_ids", sa.Text(), nullable=False),
        sa.Column("gcp_quantity", sa.Integer(), nullable=False),
        sa.Column("gcp_site_id", sa.String(ID), nullable=True),
        sa.Column("deployed_on", sa.String(10), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(ID), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("failure", sa.Text(), nullable=False),
        sa.Column("returned_on", sa.String(10), nullable=True),
        sa.Column("returned_by", sa.String(ID), nullable=True),
        sa.Column("returns", sa.Text(), nullable=False),
        sa.Column("gcp_returned", sa.Integer(), nullable=False),
        sa.Column("gcp_consumed", sa.Integer(), nullable=False),
        sa.Column("return_site_id", sa.String(ID), nullable=True),
        _fk("deployments", "project_id", "projects"),
        sa.PrimaryKeyConstraint("id", name="pk_deployments"),
    )
    op.create_index("ix_deployments_project_id", "deployments", ["project_id"])

    op.create_table(
        "sorties",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(ID), nullable=False),
        sa.Column("deployment_id", sa.String(ID), nullable=False),
        sa.Column("drone_id", sa.String(ID), nullable=False),
        sa.Column("pilot_id", sa.String(ID), nullable=False),
        sa.Column("flown_on", sa.String(10), nullable=False),
        sa.Column("hours", sa.String(16), nullable=False),
        sa.Column("landings", sa.Integer(), nullable=False),
        sa.Column("cycles", sa.Integer(), nullable=False),
        sa.Column("battery_ids", sa.Text(), nullable=False),
        sa.Column("ppk_base_id", sa.String(ID), nullable=True),
        sa.Column("media_ids", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("usage_entries", sa.Text(), nullable=False),
        sa.Column("voided_at", sa.String(32), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=False),
        _fk("sorties", "project_id", "projects"),
        _fk("sorties", "deployment_id", "deployments"),
        _fk("sorties", "drone_id", "assets"),
        sa.PrimaryKeyConstraint("id", name="pk_sorties"),
    )
    op.create_index("ix_sorties_project_id", "sorties", ["project_id"])

    op.create_table(
        "survey_sessions",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(ID), nullable=False),
        sa.Column("deployment_id", sa.String(ID), nullable=False),
        sa.Column("surveyor_id", sa.String(ID), nullable=False),
        sa.Column("surveyed_on", sa.String(10), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("base_id", sa.String(ID), nullable=True),
        sa.Column("rover_ids", sa.Text(), nullable=False),
        sa.Column("controller_id", sa.String(ID), nullable=True),
        sa.Column("hours", sa.String(16), nullable=False),
        sa.Column("area_ha", sa.String(16), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("fix_rate", sa.String(8), nullable=True),
        sa.Column("battery_ids", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(ID), nullable=False),
        sa.Column("usage_entries", sa.Text(), nullable=False),
        sa.Column("voided_at", sa.String(32), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=False),
        _fk("survey_sessions", "project_id", "projects"),
        _fk("survey_sessions", "deployment_id", "deployments"),
        sa.PrimaryKeyConstraint("id", name="pk_survey_sessions"),
    )
    op.create_index("ix_survey_sessions_project_id", "survey_sessions", ["project_id"])


def downgrade() -> None:
    for table in ("survey_sessions", "sorties", "deployments", "projects"):
        op.drop_table(table)
