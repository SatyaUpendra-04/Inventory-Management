"""Battery lifecycle (ARCHITECTURE §4.4).

A battery keeps its own history whichever drone, receiver or kit it is used with:

* **Cycles** come from the usage ledger: a cycle per flight or survey session, plus
  charge cycles logged for receiver and controller batteries.
* **Checks** are an append-only record per battery: measured health, internal resistance,
  cell imbalance, swelling or damage, and whether it was left at storage charge.
* **Health** is the latest measured value; with none, an estimate from cycles (the V1.2.3
  formula, 100 - cycles / limit x 35) is shown and clearly labelled as an estimate.

Nothing resets cycles or health. Servicing a battery adds a check; it never edits history
(this fixes rule M4 of V1.2.3, where servicing reset both to new).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.catalogue import default_item_type_id
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    BatteryPolicyId,
    CommandId,
    EntryId,
    ItemTypeId,
    UserId,
)
from ims.domain.common.model import UtcDateTime, ValueModel, VersionedRecord

ESTIMATE_DROP = Decimal(35)  # V1.2.3: health falls by 35 points over the rated cycle life
NEAR_LIMIT_SHARE = Decimal("0.9")


class BatteryPolicy(VersionedRecord):
    """Limits for one kind of battery (editable; start from the manufacturer's figures)."""

    id: BatteryPolicyId
    item_type_id: ItemTypeId
    cycle_limit: int = Field(gt=0, le=100_000)
    health_floor: int = Field(default=70, ge=1, le=100)  # retire below this %
    idle_days: int = Field(default=14, ge=1, le=365)  # storage-charge reminder after
    notes: str = Field(default="", max_length=1000)


def policy_id(item_type_id: ItemTypeId) -> BatteryPolicyId:
    return BatteryPolicyId(uuid.uuid5(uuid.NAMESPACE_URL, f"ims:battery-policy:{item_type_id}"))


DEFAULT_POLICIES: tuple[tuple[str, int, int, int], ...] = (
    # (item code, cycle limit, health floor %, idle days before a storage-charge reminder)
    ("DRONE_BATTERY", 200, 70, 14),  # V1.2.3 default; LiPo packs like storage charge within days
    ("GNSS_BATTERY", 500, 70, 30),  # Li-ion receiver batteries
    ("CONTROLLER_BATTERY", 500, 70, 30),
)


def default_policies() -> list[BatteryPolicy]:
    return [
        BatteryPolicy(
            id=policy_id(default_item_type_id(code)),
            item_type_id=default_item_type_id(code),
            cycle_limit=limit,
            health_floor=floor,
            idle_days=idle,
        )
        for code, limit, floor, idle in DEFAULT_POLICIES
    ]


class ChargeState(StrEnum):
    STORAGE = "storage"  # left at storage voltage (about 3.8 V per LiPo cell)
    FULL = "full"
    LOW = "low"
    UNKNOWN = "unknown"


class BatteryCheck(ValueModel):
    """One inspection of a battery (append-only, sequenced per battery)."""

    id: EntryId
    asset_id: AssetId
    sequence: int = Field(ge=1)
    checked_on: date
    health_pct: int | None = Field(default=None, ge=0, le=100)
    internal_resistance_mohm: Decimal | None = Field(
        default=None, ge=0, le=10_000, decimal_places=1
    )
    cell_imbalance_mv: int | None = Field(default=None, ge=0, le=5_000)
    swelling: bool = False
    damage: bool = False
    charge_state: ChargeState = ChargeState.UNKNOWN
    notes: str = Field(default="", max_length=1000)
    recorded_at: UtcDateTime
    recorded_by: UserId
    command_id: CommandId

    @model_validator(mode="after")
    def _rules(self) -> BatteryCheck:
        if (self.swelling or self.damage) and not self.notes.strip():
            raise ValueError("describe the swelling or damage")
        return self


def check_new_battery_check(
    existing: Sequence[BatteryCheck], check: BatteryCheck, today: date
) -> None:
    problems: list[str] = []
    if check.sequence != len(existing) + 1:
        problems.append("a check was recorded by someone else meanwhile; reload and try again")
    if check.checked_on > today:
        problems.append("a check cannot be dated in the future")
    if problems:
        raise RuleViolation(problems)


class BatteryCondition(StrEnum):
    OK = "ok"
    STORAGE_DUE = "storage_due"  # idle too long without being left at storage charge
    NEAR_LIMIT = "near_limit"  # 90% of the cycle limit
    RETIRE = "retire"  # at the cycle limit or below the health floor
    UNSAFE = "unsafe"  # swelling or damage at the last check

    @property
    def rank(self) -> int:
        return list(BatteryCondition).index(self)


@dataclass(frozen=True, slots=True)
class BatteryState:
    cycles: int
    cycle_limit: int | None
    health: Decimal | None
    health_measured: bool
    last_check: BatteryCheck | None
    idle_days: int | None  # days since it was last used or checked
    condition: BatteryCondition
    reasons: list[str] = field(default_factory=list)  # why it must not be used
    warnings: list[str] = field(default_factory=list)

    @property
    def health_text(self) -> str:
        if self.health is None:
            return "—"
        text = f"{self.health.quantize(Decimal(1), ROUND_HALF_UP)}%"
        return text if self.health_measured else f"~{text} (estimated)"


def estimated_health(cycles: int, cycle_limit: int) -> Decimal:
    return max(Decimal(0), Decimal(100) - Decimal(cycles) / Decimal(cycle_limit) * ESTIMATE_DROP)


def battery_state(
    *,
    cycles: int,
    policy: BatteryPolicy | None,
    checks: Sequence[BatteryCheck],
    last_used: date | None,
    today: date,
) -> BatteryState:
    """Where one battery stands, and anything that grounds it or needs doing."""
    last = checks[-1] if checks else None
    measured = next((c for c in reversed(checks) if c.health_pct is not None), None)
    health: Decimal | None = None
    is_measured = False
    if measured is not None:
        health, is_measured = Decimal(measured.health_pct or 0), True
    elif policy is not None:
        health = estimated_health(cycles, policy.cycle_limit)
    reasons: list[str] = []
    warnings: list[str] = []
    condition = BatteryCondition.OK
    if last is not None and (last.swelling or last.damage):
        found = "swelling" if last.swelling else "damage"
        reasons.append(
            f"{found} found at the check on {last.checked_on:%d %b %Y}: retire it safely"
        )
        condition = BatteryCondition.UNSAFE
    if policy is not None:
        if cycles >= policy.cycle_limit:
            reasons.append(f"cycle limit reached ({cycles} of {policy.cycle_limit})")
        elif cycles >= policy.cycle_limit * NEAR_LIMIT_SHARE:
            warnings.append(f"{policy.cycle_limit - cycles} cycles left before retirement")
        if is_measured and health is not None and health < policy.health_floor:
            reasons.append(f"health {health}% is below the {policy.health_floor}% limit")
    if reasons and condition is not BatteryCondition.UNSAFE:
        condition = BatteryCondition.RETIRE
    elif warnings and condition is BatteryCondition.OK:
        condition = BatteryCondition.NEAR_LIMIT
    activity = [d for d in (last_used, last.checked_on if last else None) if d is not None]
    idle = (today - max(activity)).days if activity else None
    stored = (
        last is not None
        and last.charge_state is ChargeState.STORAGE
        and (last_used is None or last.checked_on >= last_used)
    )
    if policy is not None and idle is not None and idle >= policy.idle_days and not stored:
        warnings.append(f"idle {idle} days: put it at storage charge")
        if condition is BatteryCondition.OK:
            condition = BatteryCondition.STORAGE_DUE
    return BatteryState(
        cycles=cycles, cycle_limit=policy.cycle_limit if policy else None, health=health,
        health_measured=is_measured, last_check=last, idle_days=idle, condition=condition,
        reasons=reasons, warnings=warnings,
    )  # fmt: skip
