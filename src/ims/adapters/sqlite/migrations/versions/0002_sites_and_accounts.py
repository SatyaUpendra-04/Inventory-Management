"""Sites, local credentials, and a licence document reference on users.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ID = 36


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("licence_document", sa.String(80), nullable=True))

    op.create_table(
        "sites",
        sa.Column("id", sa.String(ID), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("latitude", sa.String(24), nullable=True),
        sa.Column("longitude", sa.String(24), nullable=True),
        sa.Column("area_hectares", sa.String(24), nullable=True),
        sa.Column("mineral", sa.String(60), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sites"),
        sa.UniqueConstraint("code", name="uq_sites_code"),
    )
    op.create_table(
        "local_credentials",
        sa.Column("user_id", sa.String(ID), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.String(32), nullable=True),
        sa.Column("changed_at", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_local_credentials_user_id_users"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_local_credentials"),
    )


def downgrade() -> None:
    op.drop_table("local_credentials")
    op.drop_table("sites")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("licence_document")
