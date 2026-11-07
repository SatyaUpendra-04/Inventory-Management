"""Clock port: the only source of "now" (ADR-0003)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware, in UTC."""
        ...

    def today(self) -> date:
        """Current calendar date where the user works (the site's local date)."""
        ...
