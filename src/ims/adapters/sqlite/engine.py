"""SQLite engine setup and migrations, with a verified backup before any upgrade."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
log = structlog.get_logger(__name__)


def create_sqlite_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.close()

    return engine


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("no migrations found")
    return head


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def migrate(engine: Engine, db_path: Path) -> Path | None:
    """Upgrades the database to the latest schema.

    If the database already has data and is behind, a backup is written and checked
    with ``PRAGMA integrity_check`` first. Returns the backup path, if one was made.
    """
    current = current_revision(engine)
    if current == head_revision():
        return None
    backup = _backup(db_path) if current is not None else None
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    log.info("database_migrated", from_revision=current, to_revision=head_revision())
    return backup


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    counter = 1
    while target.exists():
        target = db_path.with_name(f"{db_path.name}.bak-{stamp}-{counter}")
        counter += 1
    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
        problem = integrity_problem(dest)
        if problem is not None:
            raise sqlite3.DatabaseError(f"backup failed integrity check: {problem}")
    except Exception:
        dest.close()
        target.unlink(missing_ok=True)
        raise
    finally:
        source.close()
    dest.close()
    log.info("database_backed_up", path=str(target))
    return target


def integrity_problem(connection: sqlite3.Connection) -> str | None:
    """``None`` if SQLite's integrity check passes, otherwise its report."""
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    report = "; ".join(str(row[0]) for row in rows)
    return None if report == "ok" else report or "no result"
