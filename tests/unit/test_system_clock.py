from datetime import UTC

from ims.adapters.system_clock import SystemClock


def test_system_clock_knows_india_time_on_every_platform() -> None:
    """Windows has no time-zone database; the tzdata package must provide it."""
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is UTC
    assert abs((clock.today() - now.date()).days) <= 1
