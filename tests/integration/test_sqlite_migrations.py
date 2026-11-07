import contextlib
import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from ims.adapters.sqlite import engine as engine_module
from ims.adapters.sqlite import open_sqlite_storage
from ims.adapters.sqlite.engine import current_revision, head_revision, migrate
from ims.adapters.sqlite.schema import metadata
from ims.domain.identity.roles import Role
from tests.fakes import make_user

pytestmark = pytest.mark.integration


def _count_users(db: Path) -> int:
    with contextlib.closing(sqlite3.connect(db)) as connection:
        return int(connection.execute("SELECT count(*) FROM users").fetchone()[0])


def test_migrated_schema_matches_table_definitions(tmp_path: Path) -> None:
    _, engine = open_sqlite_storage(tmp_path / "ims.sqlite3")
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []
    assert current_revision(engine) == head_revision()
    engine.dispose()


def test_data_survives_reopening_and_up_to_date_db_is_not_backed_up(tmp_path: Path) -> None:
    db = tmp_path / "ims.sqlite3"
    storage, engine = open_sqlite_storage(db)
    admin = make_user(Role.ADMIN)
    storage.users.add(admin)
    engine.dispose()

    reopened, engine = open_sqlite_storage(db)
    assert reopened.users.get(admin.id) == admin
    assert migrate(engine, db) is None
    assert list(tmp_path.glob("*.bak-*")) == []
    engine.dispose()


def test_upgrading_an_existing_database_backs_it_up_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "ims.sqlite3"
    storage, engine = open_sqlite_storage(db)
    storage.users.add(make_user(Role.ADMIN))

    upgrades: list[str] = []
    monkeypatch.setattr(engine_module, "current_revision", lambda _engine: "previous")
    monkeypatch.setattr(
        engine_module.command, "upgrade", lambda _config, target: upgrades.append(target)
    )

    backup = migrate(engine, db)
    engine.dispose()

    assert upgrades == ["head"]
    assert backup is not None and backup.name.startswith("ims.sqlite3.bak-")
    assert _count_users(backup) == 1


def test_backups_never_overwrite_each_other(tmp_path: Path) -> None:
    db = tmp_path / "ims.sqlite3"
    _, engine = open_sqlite_storage(db)
    engine.dispose()
    first = engine_module._backup(db)
    second = engine_module._backup(db)
    assert first != second
    assert first.exists() and second.exists()


def test_failed_integrity_check_removes_the_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "ims.sqlite3"
    _, engine = open_sqlite_storage(db)
    engine.dispose()
    assert _count_users(db) == 0
    monkeypatch.setattr(engine_module, "integrity_problem", lambda _connection: "page 4 corrupt")
    with pytest.raises(sqlite3.DatabaseError, match="page 4 corrupt"):
        engine_module._backup(db)
    assert list(tmp_path.glob("*.bak-*")) == []


def test_integrity_check_passes_on_a_healthy_database(tmp_path: Path) -> None:
    db = tmp_path / "ims.sqlite3"
    _, engine = open_sqlite_storage(db)
    engine.dispose()
    with contextlib.closing(sqlite3.connect(db)) as connection:
        assert engine_module.integrity_problem(connection) is None
