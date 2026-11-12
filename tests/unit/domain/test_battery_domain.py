"""Rules added in Sprint 8: battery lifecycle and GNSS calibration records."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from ims.domain.assets.calibration import (
    CalibrationKind,
    CalibrationRecord,
    CalibrationResult,
    check_new_record,
    failed_reason,
)
from ims.domain.batteries import (
    BatteryCheck,
    BatteryCondition,
    ChargeState,
    battery_state,
    check_new_battery_check,
    default_policies,
    estimated_health,
)
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, CommandId, EntryId, UserId, uuid7

DAY = date(2026, 11, 12)
NOW = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
POLICY = default_policies()[0]  # drone flight: 200 cycles, 70%, 14 days


def check(seq: int = 1, on: date = DAY, **values: Any) -> BatteryCheck:
    data: dict[str, Any] = {
        "id": EntryId(uuid7()),
        "asset_id": AssetId(uuid7()),
        "sequence": seq,
        "checked_on": on,
        "recorded_at": NOW,
        "recorded_by": UserId(uuid7()),
        "command_id": CommandId(uuid7()),
    }
    data.update(values)
    return BatteryCheck(**data)


def state(
    cycles: int = 0,
    checks: tuple[BatteryCheck, ...] = (),
    used: date | None = DAY,
    today: date = DAY,
) -> Any:
    return battery_state(cycles=cycles, policy=POLICY, checks=checks, last_used=used, today=today)


class TestBatteries:
    def test_defaults(self) -> None:
        assert [(p.cycle_limit, p.health_floor, p.idle_days) for p in default_policies()] == [
            (200, 70, 14),
            (500, 70, 30),
            (500, 70, 30),
        ]

    def test_cycle_limits_and_estimates(self) -> None:
        assert estimated_health(100, 200) == Decimal("82.5")
        assert estimated_health(1000, 200) == 0
        fresh = state(10)
        assert fresh.condition is BatteryCondition.OK and fresh.health_text == "~98% (estimated)"
        assert state(180).condition is BatteryCondition.NEAR_LIMIT
        spent = state(200)
        assert spent.condition is BatteryCondition.RETIRE
        assert spent.reasons == ["cycle limit reached (200 of 200)"]

    def test_measured_health_and_safety(self) -> None:
        good = state(50, (check(health_pct=91),))
        assert good.health_text == "91%" and good.health_measured
        weak = state(50, (check(health_pct=91), check(2, health_pct=60)))
        assert (
            weak.condition is BatteryCondition.RETIRE and "below the 70% limit" in weak.reasons[0]
        )
        swollen = state(50, (check(swelling=True, notes="Puffed"),))
        assert swollen.condition is BatteryCondition.UNSAFE and "swelling" in swollen.reasons[0]
        damaged = state(50, (check(damage=True, notes="Split case"),))
        assert "damage found" in damaged.reasons[0]
        with pytest.raises(ValidationError, match="describe"):
            check(damage=True)
        no_policy = battery_state(cycles=5, policy=None, checks=(), last_used=None, today=DAY)
        assert no_policy.health_text == "—" and no_policy.idle_days is None

    def test_storage_reminder(self) -> None:
        later = DAY + timedelta(days=20)
        idle = state(10, used=DAY, today=later)
        assert idle.condition is BatteryCondition.STORAGE_DUE and idle.idle_days == 20
        stored = state(
            10, (check(on=DAY, charge_state=ChargeState.STORAGE),), used=DAY, today=later
        )
        assert stored.condition is BatteryCondition.OK
        used_after = state(
            10,
            (check(on=DAY, charge_state=ChargeState.STORAGE),),
            used=DAY + timedelta(days=2),
            today=later,
        )
        assert used_after.condition is BatteryCondition.STORAGE_DUE

    def test_check_sequence(self) -> None:
        first = check()
        check_new_battery_check([], first, DAY)
        with pytest.raises(RuleViolation) as caught:
            check_new_battery_check([first], check(5, on=DAY + timedelta(days=1)), DAY)
        assert "meanwhile" in str(caught.value) and "future" in str(caught.value)


def record(seq: int = 1, on: date = DAY, **values: Any) -> CalibrationRecord:
    data: dict[str, Any] = {
        "id": EntryId(uuid7()),
        "asset_id": AssetId(uuid7()),
        "sequence": seq,
        "kind": CalibrationKind.CALIBRATION,
        "done_on": on,
        "method": "Lab",
        "reference": "Service centre",
        "result": CalibrationResult.PASS,
        "valid_until": on + timedelta(days=365),
        "recorded_at": NOW,
        "recorded_by": UserId(uuid7()),
        "command_id": CommandId(uuid7()),
    }
    data.update(values)
    return CalibrationRecord(**data)


class TestCalibration:
    def test_rules(self) -> None:
        with pytest.raises(ValidationError, match="runs to"):
            record(valid_until=None)
        with pytest.raises(ValidationError, match="differences"):
            record(kind=CalibrationKind.VERIFICATION, valid_until=None)
        with pytest.raises(ValidationError, match="before the calibration"):
            record(valid_until=DAY - timedelta(days=1))
        with pytest.raises(ValidationError, match="what failed"):
            record(result=CalibrationResult.FAIL)
        record(result=CalibrationResult.FAIL, valid_until=None, notes="Drift")

    def test_latest_result_counts(self) -> None:
        assert failed_reason([]) is None
        failed = record(
            1,
            DAY - timedelta(days=5),
            kind=CalibrationKind.VERIFICATION,
            result=CalibrationResult.FAIL,
            valid_until=None,
            vertical_mm=Decimal(70),
            notes="Vertical out",
        )
        assert failed_reason([failed]) == "last verification on 07 Nov 2026 failed: Vertical out"
        fixed = record(2, DAY, result=CalibrationResult.ADJUSTED)
        assert failed_reason([failed, fixed]) is None
        check_new_record([failed], fixed, DAY)
        with pytest.raises(RuleViolation) as caught:
            check_new_record([failed], record(4, DAY + timedelta(days=1)), DAY)
        assert "meanwhile" in str(caught.value) and "future" in str(caught.value)
