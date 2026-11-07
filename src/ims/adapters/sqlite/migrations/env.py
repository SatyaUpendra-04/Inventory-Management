"""Alembic environment: runs migrations on the connection handed over by ``engine.migrate``."""

from __future__ import annotations

from alembic import context

from ims.adapters.sqlite.schema import metadata

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=metadata,
    render_as_batch=True,  # SQLite needs table rebuilds for most ALTERs
    compare_type=True,
)
with context.begin_transaction():
    context.run_migrations()
