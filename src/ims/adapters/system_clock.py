"""Real clock: UTC for timestamps, the configured site time zone for calendar dates."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

DEFAULT_SITE_ZONE = "Asia/Kolkata"


class SystemClock:
    def __init__(self, site_zone: str = DEFAULT_SITE_ZONE) -> None:
        self._zone = ZoneInfo(site_zone)

    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return datetime.now(self._zone).date()
