"""Local SQLite adapter, used for development and the admin backup snapshot."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

from ims.adapters.sqlite.engine import create_sqlite_engine, migrate
from ims.adapters.sqlite.repositories import sqlite_storage
from ims.ports.repository import Storage

DB_FILE_NAME = "ims.sqlite3"


def open_sqlite_storage(db_path: Path) -> tuple[Storage, Engine]:
    """Opens (and if needed creates or upgrades) the database at ``db_path``."""
    engine = create_sqlite_engine(db_path)
    migrate(engine, db_path)
    return sqlite_storage(engine), engine


__all__ = ["DB_FILE_NAME", "open_sqlite_storage"]
