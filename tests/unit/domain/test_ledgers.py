from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ims.domain.assets.catalogue import DEFAULT_CATALOGUE, Meter
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    EntryId,
    LocationId,
    ProjectId,
    UserId,
    uuid7,
)
from ims.domain.stock.ledger import (
    MovementKind,
    StockMovement,
    check_new_movement,
    needs_reorder,
    position,
)
from ims.domain.usage.ledger import UsageEntry, UsageSource, check_new_entry, totals
from tests.fakes import START

TYPES = {t.code: t for t in DEFAULT_CATALOGUE}
DRONE, BATTERY, BANNER = TYPES["DRONE_AIRFRAME"], TYPES["DRONE_BATTERY"], TYPES["GCP_BANNER"]
ASSET = AssetId(uuid7())
PROJECT = ProjectId(uuid7())
STORE, SITE_STORE = LocationId(uuid7()), LocationId(uuid7())


def usage(seq: int, amount: str | Decimal = "1.00", **overrides: Any) -> UsageEntry:
    data: dict[str, Any] = {
        "id": EntryId(uuid7()), "asset_id": ASSET, "sequence": seq, "meter": Meter.HOURS,
        "amount": Decimal(str(amount)), "occurred_on": date(2026, 11, 8),
        "source": UsageSource.SORTIE,
        "recorded_at": START, "recorded_by": UserId(uuid7()), "command_id": CommandId(uuid7()),
        "project_id": PROJECT,
    }  # fmt: skip
    data.update(overrides)
    data["amount"] = Decimal(str(data["amount"]))
    return UsageEntry.build(**data)


class TestUsageEntry:
    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"meter": Meter.CYCLES, "amount": Decimal("1.5")}, "cycles must be a whole number"),
            ({"amount": Decimal("1.234")}, "at most two decimal places"),
            ({"amount": Decimal(0)}, "greater than zero"),
            ({"amount": Decimal(150)}, "check the value"),
            ({"reverses": EntryId(uuid7())}, "only a reversal can"),
            ({"source": UsageSource.REVERSAL}, "must reference the entry"),
            ({"source": UsageSource.ADJUSTMENT, "amount": Decimal(2)}, "needs a non-zero amount"),
            ({"project_id": None}, "sortie must belong to a project"),
        ],
    )
    def test_invalid_entries(self, overrides: dict[str, Any], message: str) -> None:
        with pytest.raises(RuleViolation, match=message):
            usage(1, **{"amount": "1.00", **overrides})

    def test_opening_balance_may_be_large(self) -> None:
        entry = usage(1, "412.50", source=UsageSource.OPENING_BALANCE, project_id=None)
        assert entry.amount == Decimal("412.50")


class TestUsageLedger:
    def test_totals_per_meter(self) -> None:
        entries = [
            usage(1, "1.25"),
            usage(2, "0.75"),
            usage(3, "3", meter=Meter.LANDINGS),
        ]
        assert totals(entries) == {Meter.HOURS: Decimal("2.00"), Meter.LANDINGS: Decimal(3)}

    def test_sequence_must_continue(self) -> None:
        with pytest.raises(RuleViolation, match="someone else meanwhile"):
            check_new_entry([usage(1, "1")], usage(3, "1"), DRONE)

    def test_meter_must_belong_to_item_type(self) -> None:
        with pytest.raises(RuleViolation, match="does not track hours"):
            check_new_entry([], usage(1, "1"), BATTERY)

    def test_duplicate_entry_is_rejected(self) -> None:
        first = usage(1, "1")
        with pytest.raises(RuleViolation, match="already been recorded"):
            check_new_entry([first], first.model_copy(update={"sequence": 2}), DRONE)

    def test_only_one_opening_balance_per_meter(self) -> None:
        opening = usage(1, "100", source=UsageSource.OPENING_BALANCE, project_id=None)
        second = usage(2, "5", source=UsageSource.OPENING_BALANCE, project_id=None)
        with pytest.raises(RuleViolation, match="opening balance"):
            check_new_entry([opening], second, DRONE)

    def test_reversal_cancels_exactly_once(self) -> None:
        original = usage(1, "2.50")
        reversal = usage(2, "-2.50", source=UsageSource.REVERSAL, reverses=original.id)
        check_new_entry([original], reversal, DRONE)
        assert totals([original, reversal]) == {Meter.HOURS: Decimal("0.00")}
        again = usage(3, "-2.50", source=UsageSource.REVERSAL, reverses=original.id)
        with pytest.raises(RuleViolation, match="already been reversed"):
            check_new_entry([original, reversal], again, DRONE)

    def test_reversal_rules(self) -> None:
        original = usage(1, "2.50")
        wrong_amount = usage(2, "-1.00", source=UsageSource.REVERSAL, reverses=original.id)
        with pytest.raises(RuleViolation, match="cancel the original amount exactly"):
            check_new_entry([original], wrong_amount, DRONE)
        missing = usage(2, "-2.50", source=UsageSource.REVERSAL, reverses=EntryId(uuid7()))
        with pytest.raises(RuleViolation, match="does not exist"):
            check_new_entry([original], missing, DRONE)
        reversal = usage(2, "-2.50", source=UsageSource.REVERSAL, reverses=original.id)
        of_reversal = usage(3, "2.50", source=UsageSource.REVERSAL, reverses=reversal.id)
        with pytest.raises(RuleViolation, match="cannot itself be reversed"):
            check_new_entry([original, reversal], of_reversal, DRONE)

    def test_adjustment_cannot_make_total_negative(self) -> None:
        adjust = usage(2, "-5", source=UsageSource.ADJUSTMENT, note="meter fix", project_id=None)
        with pytest.raises(RuleViolation, match="cannot go below zero"):
            check_new_entry([usage(1, "1")], adjust, DRONE)


@settings(max_examples=200)
@given(st.lists(st.tuples(st.decimals("0.01", "24", places=2), st.booleans()), max_size=25))
def test_usage_totals_equal_unreversed_entries(items: list[tuple[Decimal, bool]]) -> None:
    """Reversing any subset of entries leaves exactly the un-reversed hours."""
    ledger: list[UsageEntry] = []
    expected = Decimal(0)
    for amount, reverse in items:
        entry = usage(len(ledger) + 1, str(amount))
        check_new_entry(ledger, entry, DRONE)
        ledger.append(entry)
        if reverse:
            reversal = usage(
                len(ledger) + 1, str(-amount), source=UsageSource.REVERSAL, reverses=entry.id
            )
            check_new_entry(ledger, reversal, DRONE)
            ledger.append(reversal)
        else:
            expected += amount
    assert totals(ledger).get(Meter.HOURS, Decimal(0)) == expected


def move(seq: int, kind: MovementKind, quantity: int = 1, **overrides: Any) -> StockMovement:
    data: dict[str, Any] = {
        "id": EntryId(uuid7()), "item_type_id": BANNER.id, "sequence": seq,
        "location_id": STORE, "kind": kind, "quantity": quantity, "recorded_at": START,
        "recorded_by": UserId(uuid7()), "command_id": CommandId(uuid7()),
        "project_id": PROJECT if kind in {MovementKind.ISSUED, MovementKind.RETURNED,
                                          MovementKind.CONSUMED} else None,
        "reason": "count" if kind in {MovementKind.WRITTEN_OFF, MovementKind.ADJUSTED} else "",
    }  # fmt: skip
    data.update(overrides)
    return StockMovement.build(**data)


class TestStockLedger:
    def test_full_survey_cycle(self) -> None:
        ledger = [
            move(1, MovementKind.RECEIVED, 50),
            move(2, MovementKind.ISSUED, 12),
            move(3, MovementKind.RETURNED, 9),
            move(4, MovementKind.CONSUMED, 3),
        ]
        pos = position(ledger)
        assert pos.on_hand_at(STORE) == 47
        assert pos.outstanding_with(PROJECT) == 0
        assert pos.consumed == {PROJECT: 3}
        assert pos.total_on_hand == 47

    def test_cannot_issue_more_than_in_store(self) -> None:
        with pytest.raises(RuleViolation, match="only 5 GCP banner"):
            check_new_movement(
                [move(1, MovementKind.RECEIVED, 5)], move(2, MovementKind.ISSUED, 6), BANNER
            )

    def test_cannot_return_or_consume_more_than_issued(self) -> None:
        ledger = [move(1, MovementKind.RECEIVED, 20), move(2, MovementKind.ISSUED, 4)]
        with pytest.raises(RuleViolation, match="only has 4"):
            check_new_movement(ledger, move(3, MovementKind.CONSUMED, 5), BANNER)

    def test_stores_are_counted_separately(self) -> None:
        ledger = [move(1, MovementKind.RECEIVED, 20)]
        with pytest.raises(RuleViolation, match="only 0"):
            check_new_movement(
                ledger, move(2, MovementKind.WRITTEN_OFF, 1, location_id=SITE_STORE), BANNER
            )

    def test_adjustment_is_signed(self) -> None:
        ledger = [move(1, MovementKind.RECEIVED, 20), move(2, MovementKind.ADJUSTED, -2)]
        assert position(ledger).on_hand_at(STORE) == 18

    def test_sequence_and_duplicates(self) -> None:
        first = move(1, MovementKind.RECEIVED, 5)
        with pytest.raises(RuleViolation, match="someone else meanwhile"):
            check_new_movement([first], move(5, MovementKind.RECEIVED, 1), BANNER)
        with pytest.raises(RuleViolation, match="already been recorded"):
            check_new_movement([first], first.model_copy(update={"sequence": 2}), BANNER)

    def test_individually_tracked_items_are_not_stock(self) -> None:
        with pytest.raises(RuleViolation, match="tracked individually"):
            check_new_movement([], move(1, MovementKind.RECEIVED, 1, item_type_id=DRONE.id), DRONE)

    @pytest.mark.parametrize(
        ("kind", "overrides", "message"),
        [
            (MovementKind.RECEIVED, {"quantity": 0}, "greater than zero"),
            (MovementKind.ADJUSTED, {"quantity": 0}, "must change the quantity"),
            (MovementKind.ISSUED, {"project_id": None}, "must name a project"),
            (MovementKind.RECEIVED, {"project_id": PROJECT}, "must name a project"),
            (MovementKind.WRITTEN_OFF, {"reason": ""}, "need a reason"),
        ],
    )
    def test_invalid_movements(
        self, kind: MovementKind, overrides: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(RuleViolation, match=message):
            move(1, kind, **{"quantity": 3, **overrides})

    def test_reorder_level(self) -> None:
        assert needs_reorder(10, 10)
        assert not needs_reorder(11, 10)


kinds = st.sampled_from(list(MovementKind))


@settings(max_examples=300)
@given(st.lists(st.tuples(kinds, st.integers(-30, 30)), max_size=40))
def test_accepted_movements_never_make_balances_negative(
    requests: list[tuple[MovementKind, int]],
) -> None:
    """Random issue/return/consume/adjust requests: whatever is accepted keeps stock valid."""
    ledger: list[StockMovement] = []
    for kind, quantity in requests:
        try:
            movement = move(len(ledger) + 1, kind, quantity)
            check_new_movement(ledger, movement, BANNER)
        except RuleViolation:
            continue
        ledger.append(movement)
        pos = position(ledger)
        assert all(v >= 0 for v in pos.on_hand.values())
        assert all(v >= 0 for v in pos.outstanding.values())
