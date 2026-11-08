"""Sign-in lockout policy (rules catalogue P4, changed).

V1.2.3 locked an account for 20 seconds after 5 failures and forgot it on restart.
Here the state is stored with the account, and each further failure doubles the lock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

FREE_ATTEMPTS = 5
FIRST_LOCK = timedelta(minutes=1)
LONGEST_LOCK = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class LockoutState:
    failed_attempts: int = 0
    locked_until: datetime | None = None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    def seconds_left(self, now: datetime) -> int:
        if self.locked_until is None or now >= self.locked_until:
            return 0
        return max(1, math.ceil((self.locked_until - now).total_seconds()))


def after_failure(state: LockoutState, now: datetime) -> LockoutState:
    """State after a wrong password: free attempts first, then 1, 2, 4 ... 30 minute locks."""
    attempts = state.failed_attempts + 1
    if attempts < FREE_ATTEMPTS:
        return LockoutState(attempts, None)
    # Cap the exponent: 2**10 minutes is already past LONGEST_LOCK, and an uncapped
    # power overflows timedelta after ~45 failures (found by a property test).
    doublings = min(attempts - FREE_ATTEMPTS, 10)
    lock = min(LONGEST_LOCK, FIRST_LOCK * (2**doublings))
    return LockoutState(attempts, now + lock)


def after_success() -> LockoutState:
    return LockoutState()


def describe_wait(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = (seconds + 59) // 60
    return f"{minutes} minute{'s' if minutes != 1 else ''}"
