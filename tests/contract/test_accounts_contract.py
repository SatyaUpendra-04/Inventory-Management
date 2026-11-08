"""Contract for sites, credentials and file stores, on every adapter."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ims.adapters.files import LocalFileStore, MemoryFileStore
from ims.adapters.local_auth import (
    LocalAuthProvider,
    MemoryCredentialStore,
    default_hasher,
    fast_hasher,
)
from ims.adapters.sqlite import open_sqlite_storage
from ims.adapters.sqlite.repositories import SqliteCredentialStore
from ims.domain.common.errors import AlreadyExists, ConflictError, NotFound
from ims.domain.common.ids import LocationId, uuid7
from ims.domain.files import FileKind
from ims.domain.identity.roles import Role
from ims.domain.sites.site import Site, SiteKind, SiteStatus
from ims.ports.auth import VerifyOutcome
from ims.ports.files import FileStore
from ims.ports.repository import Storage
from tests.fakes import START, make_user

pytestmark = pytest.mark.contract


def _site(code: str = "MAIN-STORE", **extra: object) -> Site:
    return Site.build(
        id=LocationId(uuid7()), code=code, name="Main store", kind=SiteKind.STORE, **extra
    )


class TestSites:
    def test_round_trip_keeps_exact_decimals(self, storage: Storage) -> None:
        site = _site(latitude=Decimal("20.296100"), longitude=Decimal("85.824500"),
                     area_hectares=Decimal("1250.75"), region="Odisha", mineral="Iron ore",
                     status=SiteStatus.PLANNED, notes="Gate 3")  # fmt: skip
        storage.sites.add(site)
        assert storage.sites.get(site.id) == site
        assert storage.sites.find_by_code("main-store") == site

    def test_unique_code_versioning_and_soft_delete(self, storage: Storage) -> None:
        site = _site()
        storage.sites.add(site)
        with pytest.raises(AlreadyExists):
            storage.sites.add(site)
        with pytest.raises(ConflictError):
            storage.sites.add(_site())
        deleted = site.next_version(deleted_at=START)
        storage.sites.update(deleted)
        with pytest.raises(ConflictError):
            storage.sites.update(site.next_version(name="stale"))
        with pytest.raises(NotFound):
            storage.sites.update(_site("OTHER").next_version(name="x"))
        storage.sites.add(_site("B-STORE"))
        assert [s.code for s in storage.sites.list()] == ["B-STORE"]
        assert [s.code for s in storage.sites.list(include_deleted=True)] == [
            "B-STORE",
            "MAIN-STORE",
        ]


@pytest.fixture(params=["memory", "sqlite"])
def auth(
    request: pytest.FixtureRequest, storage: Storage, tmp_path: Path
) -> Iterator[tuple[LocalAuthProvider, Storage]]:
    if request.param == "memory":
        yield LocalAuthProvider(MemoryCredentialStore(), fast_hasher()), storage
        return
    sqlite_storage, engine = open_sqlite_storage(tmp_path / "auth.sqlite3")
    yield LocalAuthProvider(SqliteCredentialStore(engine), fast_hasher()), sqlite_storage
    engine.dispose()


class TestCredentials:
    def test_password_lifecycle_and_lockout(self, auth: tuple[LocalAuthProvider, Storage]) -> None:
        provider, storage = auth
        user = make_user(Role.SURVEYOR)
        storage.users.add(user)
        assert provider.supports_passwords and not provider.has_password(user.id)
        assert provider.verify(user.id, "anything", START).outcome is VerifyOutcome.INVALID

        provider.set_password(user.id, "Right-Password-26!")
        assert provider.has_password(user.id)
        assert provider.verify(user.id, "Right-Password-26!", START).outcome is VerifyOutcome.OK
        for _ in range(4):
            assert provider.verify(user.id, "wrong", START).outcome is VerifyOutcome.INVALID
        locked = provider.verify(user.id, "wrong", START)
        assert locked.outcome is VerifyOutcome.LOCKED and locked.seconds_locked == 60
        assert provider.lockout(user.id).is_locked(START)
        assert provider.verify(user.id, "Right-Password-26!", START).outcome is VerifyOutcome.LOCKED
        later = START + timedelta(minutes=1, seconds=1)
        assert provider.verify(user.id, "Right-Password-26!", later).outcome is VerifyOutcome.OK
        assert provider.lockout(user.id).failed_attempts == 0

        for _ in range(5):
            provider.verify(user.id, "wrong", later)
        provider.unlock(user.id)
        assert not provider.lockout(user.id).is_locked(later)
        provider.unlock(make_user().id)  # unknown: no error
        assert provider.lockout(make_user().id).failed_attempts == 0
        provider.verify_unknown("whatever")

    def test_stored_hash_is_argon2_not_the_password(
        self, auth: tuple[LocalAuthProvider, Storage]
    ) -> None:
        provider, storage = auth
        user = make_user(Role.ADMIN)
        storage.users.add(user)
        provider.set_password(user.id, "Right-Password-26!")
        stored = provider._store.get(user.id)
        assert stored is not None and stored.password_hash.startswith("$argon2id$")
        assert "Right-Password-26!" not in stored.password_hash


def test_weak_hash_settings_are_upgraded_on_sign_in() -> None:
    store = MemoryCredentialStore()
    weak = LocalAuthProvider(store, fast_hasher())
    user = make_user()
    weak.set_password(user.id, "Right-Password-26!")
    strong = LocalAuthProvider(store, default_hasher())
    assert strong.verify(user.id, "Right-Password-26!", START).outcome is VerifyOutcome.OK
    stored = store.get(user.id)
    assert stored is not None and "m=19456" in stored.password_hash


@pytest.fixture(params=["memory", "disk"])
def files(request: pytest.FixtureRequest, tmp_path: Path) -> FileStore:
    return MemoryFileStore() if request.param == "memory" else LocalFileStore(tmp_path / "files")


class TestFileStore:
    def test_store_and_read_back(self, files: FileStore) -> None:
        content = b"\x89PNG\r\n\x1a\n" + b"picture"
        ref = files.put(content, FileKind.PNG)
        assert ref.endswith(".png") and len(ref) == 68
        assert files.get(ref) == content
        assert files.put(content, FileKind.PNG) == ref  # same bytes, same reference

    def test_unknown_or_malformed_refs(self, files: FileStore) -> None:
        assert files.get("0" * 64 + ".png") is None
        assert files.get("../../windows/system32/config") is None
        assert files.get("abc.exe") is None
