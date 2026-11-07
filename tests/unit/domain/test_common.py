import time
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ims.domain.common.errors import LastAdminError, RuleViolation
from ims.domain.common.ids import derive_id, new_command_id, uuid7, uuid7_timestamp_ms
from ims.domain.common.model import UtcDateTime, ValueModel, VersionedRecord


class TestUuid7:
    def test_has_version_7_and_rfc_variant(self) -> None:
        value = uuid7()
        assert value.version == 7
        assert value.variant == uuid.RFC_4122

    def test_embeds_the_current_millisecond(self) -> None:
        before = time.time_ns() // 1_000_000
        value = uuid7()
        after = time.time_ns() // 1_000_000
        assert before <= uuid7_timestamp_ms(value) <= after

    @given(st.integers(min_value=0, max_value=(1 << 48) - 2))
    def test_later_timestamps_sort_later(self, ms: int) -> None:
        assert uuid7(ms) < uuid7(ms + 1)

    def test_rejects_out_of_range_timestamp(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            uuid7(1 << 48)

    def test_timestamp_needs_a_v7(self) -> None:
        with pytest.raises(ValueError, match="version-7"):
            uuid7_timestamp_ms(uuid.uuid4())

    def test_command_ids_are_v7(self) -> None:
        assert new_command_id().version == 7


class TestDeriveId:
    def test_same_command_and_purpose_give_same_id(self) -> None:
        command = uuid7()
        assert derive_id(command, "asset") == derive_id(command, "asset")

    def test_different_purposes_or_commands_differ(self) -> None:
        a, b = uuid7(), uuid7()
        assert derive_id(a, "asset") != derive_id(a, "audit")
        assert derive_id(a, "asset") != derive_id(b, "asset")

    def test_purpose_required(self) -> None:
        with pytest.raises(ValueError, match="purpose"):
            derive_id(uuid7(), "")


class _Stamp(ValueModel):
    at: UtcDateTime


class _Counter(VersionedRecord):
    name: str
    count: int


class TestModels:
    def test_timestamps_are_converted_to_utc(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        stamp = _Stamp(at=datetime(2026, 11, 8, 12, 0, tzinfo=ist))
        assert stamp.at == datetime(2026, 11, 8, 6, 30, tzinfo=UTC)
        assert stamp.at.tzinfo is UTC

    def test_naive_timestamps_are_rejected(self) -> None:
        with pytest.raises(RuleViolation, match="timezone-aware"):
            _Stamp.build(at=datetime(2026, 11, 8, 12, 0))  # noqa: DTZ001

    def test_build_reports_every_problem_readably(self) -> None:
        with pytest.raises(RuleViolation) as caught:
            _Counter.build(name="x", count="many", version=0)
        problems = caught.value.problems
        assert len(problems) == 2
        assert any(p.startswith("count:") for p in problems)
        assert any(p.startswith("version:") for p in problems)

    def test_next_version_advances_and_revalidates(self) -> None:
        record = _Counter(name="a", count=1)
        updated = record.next_version(count=2)
        assert (updated.version, updated.count, record.count) == (2, 2, 1)
        with pytest.raises(RuleViolation):
            record.next_version(count="bad")

    def test_version_cannot_be_set_by_hand(self) -> None:
        with pytest.raises(ValueError, match="managed automatically"):
            _Counter(name="a", count=1).next_version(version=9)

    def test_records_are_immutable(self) -> None:
        record = _Counter(name="a", count=1)
        with pytest.raises(ValueError, match="frozen"):
            record.count = 5  # type: ignore[misc]


class TestErrors:
    def test_rule_violation_keeps_each_problem(self) -> None:
        error = RuleViolation(["first.", "second."])
        assert error.problems == ("first.", "second.")
        assert str(error) == "first. second."

    def test_rule_violation_needs_a_problem(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            RuleViolation([])

    def test_last_admin_message(self) -> None:
        assert "active administrator" in str(LastAdminError())
