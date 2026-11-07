"""Test helpers: a controllable clock and builders for valid domain objects."""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ims.domain.common.ids import UserId, uuid7
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence, User

START = datetime(2026, 11, 8, 6, 30, tzinfo=UTC)


class FixedClock:
    """Starts at ``START`` and only moves when told to."""

    def __init__(self, now: datetime = START) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._now.date()

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)


_counter = itertools.count(1)


def make_user(role: Role = Role.PILOT, **overrides: Any) -> User:
    n = next(_counter)
    data: dict[str, Any] = {
        "id": UserId(uuid7()),
        "username": f"user{n}",
        "full_name": f"Test User {n}",
        "role": role,
        "employee_id": f"EMP-{n:04d}",
        "email": f"user{n}@example.com",
        "phone": "+91 98765 43210",
        "licence": PilotLicence(number=f"RPC-{n:05d}", expires_on=date(2030, 1, 1))
        if role is Role.PILOT
        else None,
    }
    data.update(overrides)
    return User.build(**data)
