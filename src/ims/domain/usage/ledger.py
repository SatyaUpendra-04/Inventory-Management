"""Append-only usage ledger (ARCHITECTURE.md §4.2, ADR-0003).

Totals are the sum of entries. Mistakes are corrected with a reversal entry that
cancels the original exactly; entries are never edited or deleted.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.catalogue import ItemType, Meter
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, CommandId, EntryId, ProjectId, UserId
from ims.domain.common.model import UtcDateTime, ValueModel

HOURS_PLACES = Decimal("0.01")
MAX_SINGLE_ENTRY = {
    Meter.HOURS: Decimal(24),
    Meter.CYCLES: Decimal(100),
    Meter.LANDINGS: Decimal(100),
}
"""Upper bound for one field entry, to catch typing mistakes (e.g. 150 h instead of 1.50 h)."""


class UsageSource(StrEnum):
    SORTIE = "sortie"  # one flight or survey session
    RETURN = "return"  # totals entered at post-project return
    OPENING_BALANCE = "opening_balance"  # meter reading when the asset was registered
    ADJUSTMENT = "adjustment"  # admin correction with a reason
    REVERSAL = "reversal"  # cancels one earlier entry
    CHARGE = "charge"  # charge cycles logged for a battery outside flights


class UsageEntry(ValueModel):
    id: EntryId
    asset_id: AssetId
    sequence: int = Field(ge=1)  # 1, 2, 3 ... per asset; storage rejects duplicates
    meter: Meter
    amount: Decimal
    occurred_on: date
    source: UsageSource
    recorded_at: UtcDateTime
    recorded_by: UserId
    command_id: CommandId
    project_id: ProjectId | None = None
    reverses: EntryId | None = None
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _rules(self) -> UsageEntry:
        problems: list[str] = []
        if self.meter is not Meter.HOURS and self.amount != self.amount.to_integral_value():
            problems.append(f"{self.meter.value} must be a whole number")
        if self.meter is Meter.HOURS and self.amount != self.amount.quantize(HOURS_PLACES):
            problems.append("hours can have at most two decimal places")
        if (self.source is UsageSource.REVERSAL) != (self.reverses is not None):
            problems.append(
                "a reversal must reference the entry it cancels, and only a reversal can"
            )
        if self.source in {
            UsageSource.SORTIE,
            UsageSource.RETURN,
            UsageSource.OPENING_BALANCE,
            UsageSource.CHARGE,
        }:
            if self.amount <= 0:
                problems.append("recorded usage must be greater than zero")
            if (
                self.source is not UsageSource.OPENING_BALANCE
                and self.amount > MAX_SINGLE_ENTRY[self.meter]
            ):
                problems.append(
                    f"{self.amount} {self.meter.value} in one entry is more than the allowed "
                    f"{MAX_SINGLE_ENTRY[self.meter]}; check the value"
                )
        if self.source is UsageSource.ADJUSTMENT and (self.amount == 0 or not self.note.strip()):
            problems.append("an adjustment needs a non-zero amount and a reason")
        if self.source is UsageSource.SORTIE and self.project_id is None:
            problems.append("a sortie must belong to a project")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def totals(entries: Iterable[UsageEntry]) -> dict[Meter, Decimal]:
    """Current meter readings per meter (meters with no entries are absent)."""
    result: dict[Meter, Decimal] = {}
    for entry in entries:
        result[entry.meter] = result.get(entry.meter, Decimal(0)) + entry.amount
    return result


def check_new_entry(existing: Sequence[UsageEntry], entry: UsageEntry, item_type: ItemType) -> None:
    """Validates ``entry`` against the asset's history and item type."""
    problems: list[str] = []
    if any(e.id == entry.id for e in existing):
        problems.append("this entry has already been recorded")
    if entry.sequence != len(existing) + 1:
        problems.append("usage was recorded by someone else meanwhile; reload and try again")
    if entry.meter not in item_type.meters:
        problems.append(f"{item_type.name} does not track {entry.meter.value}")
    if entry.source is UsageSource.OPENING_BALANCE and any(
        e.meter is entry.meter
        and e.source is UsageSource.OPENING_BALANCE
        and not _is_reversed(e, existing)
        for e in existing
    ):
        problems.append(f"an opening balance for {entry.meter.value} already exists")
    if entry.reverses is not None:
        target = next((e for e in existing if e.id == entry.reverses), None)
        if target is None or target.asset_id != entry.asset_id:
            problems.append("the entry being reversed does not exist for this asset")
        elif target.source is UsageSource.REVERSAL:
            problems.append("a reversal cannot itself be reversed; record a new entry instead")
        elif _is_reversed(target, existing):
            problems.append("this entry has already been reversed")
        elif entry.amount != -target.amount or entry.meter is not target.meter:
            problems.append("a reversal must cancel the original amount exactly")
    if not problems:
        new_total = totals([*existing, entry]).get(entry.meter, Decimal(0))
        if new_total < 0:
            problems.append(f"{entry.meter.value} total cannot go below zero")
    if problems:
        raise RuleViolation(problems)


def _is_reversed(entry: UsageEntry, existing: Sequence[UsageEntry]) -> bool:
    return any(e.reverses == entry.id for e in existing)
