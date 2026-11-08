"""Authentication port (ADR-0002).

Passwords never live in the user records. The local adapter keeps Argon2 hashes in its
own table; Plan A (Microsoft sign-in) and Plan B (Supabase Auth) delegate to those
services. Lockout state is stored with the credential, so it survives restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from ims.domain.common.ids import UserId
from ims.domain.identity.lockout import LockoutState


class VerifyOutcome(StrEnum):
    OK = "ok"
    INVALID = "invalid"  # wrong password (or no password set)
    LOCKED = "locked"  # too many failures; try later


@dataclass(frozen=True, slots=True)
class Verification:
    outcome: VerifyOutcome
    seconds_locked: int = 0


class AuthProvider(Protocol):
    @property
    def supports_passwords(self) -> bool:
        """False for providers where the company directory handles passwords (Plan A)."""
        ...

    def verify(self, user_id: UserId, password: str, now: datetime) -> Verification:
        """Checks a password and updates the lockout state."""
        ...

    def verify_unknown(self, password: str) -> None:
        """Spends the same effort as ``verify`` for usernames that do not exist (no timing leak)."""
        ...

    def set_password(self, user_id: UserId, password: str) -> None:
        """Stores a new password hash and clears any lockout."""
        ...

    def has_password(self, user_id: UserId) -> bool: ...

    def lockout(self, user_id: UserId) -> LockoutState: ...

    def unlock(self, user_id: UserId) -> None: ...
