"""Local accounts: Argon2id password hashes with stored, escalating lockout.

Used for development and as the shape of Plan B (app-specific accounts). Credentials
live in their own store, never in the user records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from ims.domain.common.ids import UserId
from ims.domain.identity.lockout import LockoutState, after_failure, after_success
from ims.ports.auth import Verification, VerifyOutcome


@dataclass(frozen=True, slots=True)
class Credential:
    user_id: UserId
    password_hash: str
    failed_attempts: int = 0
    locked_until: datetime | None = None
    changed_at: datetime | None = None


class CredentialStore(Protocol):
    def get(self, user_id: UserId) -> Credential | None: ...
    def put(self, credential: Credential) -> None: ...


class MemoryCredentialStore:
    def __init__(self) -> None:
        self._rows: dict[UserId, Credential] = {}

    def get(self, user_id: UserId) -> Credential | None:
        return self._rows.get(user_id)

    def put(self, credential: Credential) -> None:
        self._rows[credential.user_id] = credential


def default_hasher() -> PasswordHasher:
    """OWASP-recommended Argon2id settings (19 MiB memory, 2 iterations)."""
    return PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)


def fast_hasher() -> PasswordHasher:
    """Cheap settings for tests only."""
    return PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


class LocalAuthProvider:
    def __init__(self, store: CredentialStore, hasher: PasswordHasher | None = None) -> None:
        self._store = store
        self._hasher = hasher or default_hasher()
        self._dummy_hash = self._hasher.hash("dummy-password-for-timing")

    @property
    def supports_passwords(self) -> bool:
        return True

    def verify(self, user_id: UserId, password: str, now: datetime) -> Verification:
        credential = self._store.get(user_id)
        if credential is None:
            self.verify_unknown(password)
            return Verification(VerifyOutcome.INVALID)
        state = LockoutState(credential.failed_attempts, credential.locked_until)
        if state.is_locked(now):
            return Verification(VerifyOutcome.LOCKED, state.seconds_left(now))
        if self._matches(credential.password_hash, password):
            fresh = after_success()
            self._store.put(_with_state(credential, fresh))
            if self._hasher.check_needs_rehash(credential.password_hash):
                self.set_password(user_id, password)
            return Verification(VerifyOutcome.OK)
        failed = after_failure(state, now)
        self._store.put(_with_state(credential, failed))
        if failed.is_locked(now):
            return Verification(VerifyOutcome.LOCKED, failed.seconds_left(now))
        return Verification(VerifyOutcome.INVALID)

    def verify_unknown(self, password: str) -> None:
        self._matches(self._dummy_hash, password)

    def set_password(self, user_id: UserId, password: str) -> None:
        self._store.put(
            Credential(
                user_id=user_id,
                password_hash=self._hasher.hash(password),
                changed_at=datetime.now(UTC),
            )
        )

    def has_password(self, user_id: UserId) -> bool:
        return self._store.get(user_id) is not None

    def lockout(self, user_id: UserId) -> LockoutState:
        credential = self._store.get(user_id)
        if credential is None:
            return LockoutState()
        return LockoutState(credential.failed_attempts, credential.locked_until)

    def unlock(self, user_id: UserId) -> None:
        credential = self._store.get(user_id)
        if credential is not None:
            self._store.put(_with_state(credential, after_success()))

    def _matches(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


def _with_state(credential: Credential, state: LockoutState) -> Credential:
    return Credential(
        user_id=credential.user_id,
        password_hash=credential.password_hash,
        failed_attempts=state.failed_attempts,
        locked_until=state.locked_until,
        changed_at=credential.changed_at,
    )
