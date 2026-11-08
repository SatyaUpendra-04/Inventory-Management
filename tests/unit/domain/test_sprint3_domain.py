from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import LocationId, uuid7
from ims.domain.files import (
    DOCUMENT_KINDS,
    PICTURE_KINDS,
    FileKind,
    check_upload,
    detect_kind,
)
from ims.domain.identity.lockout import (
    FIRST_LOCK,
    LONGEST_LOCK,
    LockoutState,
    after_failure,
    after_success,
    describe_wait,
)
from ims.domain.identity.user import PilotLicence
from ims.domain.sites.site import Site, SiteKind, SiteStatus
from tests.fakes import START


def site(**overrides: object) -> Site:
    data: dict[str, object] = {
        "id": LocationId(uuid7()),
        "code": "main-store",
        "name": "Main store",
        "kind": SiteKind.STORE,
    }
    data.update(overrides)
    return Site.build(**data)


class TestSites:
    def test_code_normalised_and_label(self) -> None:
        s = site()
        assert s.code == "MAIN-STORE" and s.label == "MAIN-STORE · Main store"
        assert s.status is SiteStatus.ACTIVE and not s.is_deleted

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"code": "x"}, "site code must be"),
            ({"code": "bad code!"}, "site code must be"),
            ({"latitude": Decimal(10)}, "both latitude and longitude"),
            ({"latitude": Decimal(91), "longitude": Decimal(0)}, "latitude must be"),
            ({"latitude": Decimal(0), "longitude": Decimal(-181)}, "longitude must be"),
            ({"area_hectares": Decimal(-1)}, "area cannot be negative"),
            ({"name": ""}, "at least 1 character"),
        ],
    )
    def test_invalid_sites(self, overrides: dict[str, object], message: str) -> None:
        with pytest.raises(RuleViolation, match=message):
            site(**overrides)


class TestLockout:
    def test_free_attempts_then_escalating_locks(self) -> None:
        state = LockoutState()
        for _ in range(4):
            state = after_failure(state, START)
            assert not state.is_locked(START)
        state = after_failure(state, START)
        assert state.locked_until == START + FIRST_LOCK
        assert state.seconds_left(START) == 60
        later = START + FIRST_LOCK
        state = after_failure(state, later)
        assert state.locked_until == later + FIRST_LOCK * 2

    @given(st.integers(min_value=5, max_value=60))
    def test_lock_never_exceeds_the_longest(self, failures: int) -> None:
        state = LockoutState()
        for _ in range(failures):
            state = after_failure(state, START)
        assert state.locked_until is not None
        assert state.locked_until - START <= LONGEST_LOCK

    def test_success_clears_and_unlocked_reports_zero(self) -> None:
        assert after_success() == LockoutState()
        assert LockoutState().seconds_left(START) == 0
        expired = LockoutState(5, START - timedelta(seconds=1))
        assert not expired.is_locked(START) and expired.seconds_left(START) == 0

    def test_describe_wait(self) -> None:
        assert describe_wait(1) == "1 second"
        assert describe_wait(45) == "45 seconds"
        assert describe_wait(60) == "1 minute"
        assert describe_wait(61) == "2 minutes"


class TestFiles:
    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 10
    PDF = b"%PDF-1.7" + b"\x00" * 10

    def test_kind_comes_from_content(self) -> None:
        assert detect_kind(self.PNG) is FileKind.PNG
        assert detect_kind(self.JPEG) is FileKind.JPEG
        assert detect_kind(self.PDF) is FileKind.PDF
        assert detect_kind(b"MZ\x90\x00 an .exe renamed to .png") is None

    def test_upload_rules(self) -> None:
        assert check_upload(self.PNG, PICTURE_KINDS, 1024) is FileKind.PNG
        assert check_upload(self.PDF, DOCUMENT_KINDS, 1024) is FileKind.PDF
        with pytest.raises(RuleViolation, match="empty"):
            check_upload(b"", PICTURE_KINDS, 1024)
        with pytest.raises(RuleViolation, match="larger than"):
            check_upload(self.PNG + b"\x00" * 3 * 1024 * 1024, PICTURE_KINDS, 2 * 1024 * 1024)
        with pytest.raises(RuleViolation, match="Only JPEG, PNG"):
            check_upload(self.PDF, PICTURE_KINDS, 1024)


class TestLicenceStatus:
    def test_valid_expiring_expired(self) -> None:
        licence = PilotLicence(number="RPC-1", expires_on=date(2026, 12, 31))
        assert licence.status_on(date(2026, 1, 1)) == "valid"
        assert licence.status_on(date(2026, 11, 1)) == "expiring"
        assert licence.status_on(date(2027, 1, 1)) == "expired"
        assert PilotLicence(number="RPC-1", expires_on=date(2030, 1, 1), document="x.pdf").document
