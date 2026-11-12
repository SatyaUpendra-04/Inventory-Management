"""The maintenance programme and the due calculation (ARCHITECTURE §4.3).

A task belongs to an item type and repeats every so many hours, cycles, landings and/or
days, whichever comes first. A *tolerance* allows a small overrun before the task counts
as overdue (it is shown as due, not yet blocking). A *life limit* is different: it never
repeats; when the part reaches it, the part must be replaced, so nothing can reset it.

Due status is never stored. It is calculated from the usage ledger and the most recent
completion of the task on that asset.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.catalogue import Meter, default_item_type_id
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    EntryId,
    ItemTypeId,
    MaintenanceTaskId,
    UserId,
    WorkOrderId,
)
from ims.domain.common.model import UtcDateTime, ValueModel, VersionedRecord

DUE_SOON_SHARE = Decimal("0.1")  # the last 10% of an interval counts as "due soon"
DUE_SOON_MIN_DAYS = 7


class MaintenanceTask(VersionedRecord):
    id: MaintenanceTaskId
    item_type_id: ItemTypeId
    name: str = Field(min_length=1, max_length=80)
    every_hours: Decimal | None = Field(default=None, gt=0, le=100_000, decimal_places=2)
    every_cycles: int | None = Field(default=None, gt=0, le=1_000_000)
    every_landings: int | None = Field(default=None, gt=0, le=1_000_000)
    every_days: int | None = Field(default=None, gt=0, le=3650)
    tolerance_hours: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    tolerance_cycles: int = Field(default=0, ge=0)
    tolerance_landings: int = Field(default=0, ge=0)
    tolerance_days: int = Field(default=0, ge=0)
    life_limit: bool = False  # replace the part at the limit; never reset
    instructions: str = Field(default="", max_length=2000)
    effective_from: date  # assets with no completion count from here (or acquisition)
    is_active: bool = True

    @model_validator(mode="after")
    def _rules(self) -> MaintenanceTask:
        problems: list[str] = []
        if self.limits() == {} and self.every_days is None:
            problems.append("give at least one interval: hours, cycles, landings or days")
        if self.life_limit and self.every_days is not None:
            problems.append("a life limit is counted in hours, cycles or landings, not days")
        if self.life_limit and (
            self.tolerance_hours or self.tolerance_cycles or self.tolerance_landings
        ):
            problems.append("a life limit has no tolerance")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def limits(self) -> dict[Meter, Decimal]:
        """Meter intervals this task uses."""
        result: dict[Meter, Decimal] = {}
        if self.every_hours is not None:
            result[Meter.HOURS] = self.every_hours
        if self.every_cycles is not None:
            result[Meter.CYCLES] = Decimal(self.every_cycles)
        if self.every_landings is not None:
            result[Meter.LANDINGS] = Decimal(self.every_landings)
        return result

    def tolerance(self, meter: Meter) -> Decimal:
        return {
            Meter.HOURS: self.tolerance_hours,
            Meter.CYCLES: Decimal(self.tolerance_cycles),
            Meter.LANDINGS: Decimal(self.tolerance_landings),
        }[meter]


class TaskCompletion(ValueModel):
    """A task done on one asset (append-only ledger, sequenced per asset)."""

    id: EntryId
    asset_id: AssetId
    sequence: int = Field(ge=1)
    task_id: MaintenanceTaskId
    done_on: date
    meters: dict[Meter, Decimal]  # readings when it was done
    work_order_id: WorkOrderId | None = None
    notes: str = Field(default="", max_length=2000)
    recorded_at: UtcDateTime
    recorded_by: UserId
    command_id: CommandId


def check_new_completion(
    existing: Sequence[TaskCompletion], completion: TaskCompletion, today: date
) -> None:
    problems: list[str] = []
    if completion.sequence != len(existing) + 1:
        problems.append("maintenance was recorded by someone else meanwhile; reload and try again")
    if completion.done_on > today:
        problems.append("maintenance cannot be recorded with a date in the future")
    same_task = [c for c in existing if c.task_id == completion.task_id]
    if same_task and completion.done_on < same_task[-1].done_on:
        problems.append("this task was already recorded on a later date")
    if problems:
        raise RuleViolation(problems)


# ---------------------------------------------------------------------- due calculation


class DueState(StrEnum):
    OK = "ok"
    DUE_SOON = "due_soon"
    DUE = "due"  # past the interval, inside the tolerance: still usable
    OVERDUE = "overdue"  # past interval + tolerance (or at a life limit): grounds the asset

    @property
    def rank(self) -> int:
        return [DueState.OK, DueState.DUE_SOON, DueState.DUE, DueState.OVERDUE].index(self)


@dataclass(frozen=True, slots=True)
class TaskDue:
    task: MaintenanceTask
    state: DueState
    remaining: dict[str, Decimal]  # per measure still to go (negative when past it)
    due_on: date | None  # calendar due date, when the task has one
    last_done: date | None

    @property
    def summary(self) -> str:
        """e.g. ``12.5 h or 20 days left`` / ``3 days over`` / ``due now``."""
        units = {"hours": "h", "cycles": "cycles", "landings": "landings", "days": "days"}

        def amount(unit: str, value: Decimal) -> str:
            return f"{abs(value).normalize():f} {units[unit]}"

        past = [(u, v) for u, v in self.remaining.items() if v <= 0]
        if past and self.task.life_limit:
            over = [amount(u, v) for u, v in past if v < 0]
            return f"limit reached ({' and '.join(over)} over)" if over else "limit reached"
        if past:
            over = [amount(u, v) for u, v in past if v < 0]
            return f"{' and '.join(over)} over" if over else "due now"
        return " or ".join(amount(u, v) for u, v in self.remaining.items()) + " left"


def due_status(
    task: MaintenanceTask,
    *,
    meters: Mapping[Meter, Decimal],
    today: date,
    last: TaskCompletion | None,
    start: date,
) -> TaskDue:
    """Where one task stands on one asset.

    ``meters`` are the asset's current totals; ``start`` is when counting began if the
    task has never been done (the later of acquisition and the task coming into force).
    """
    remaining: dict[str, Decimal] = {}
    states: list[DueState] = []
    for meter, interval in task.limits().items():
        now = meters.get(meter, Decimal(0))
        since = (
            now if (task.life_limit or last is None) else now - last.meters.get(meter, Decimal(0))
        )
        left = interval - since
        remaining[meter.value] = left
        tolerance = task.tolerance(meter)
        if left <= 0:
            states.append(
                DueState.OVERDUE if task.life_limit or -left > tolerance else DueState.DUE
            )
        elif left <= interval * DUE_SOON_SHARE:
            states.append(DueState.DUE_SOON)
        else:
            states.append(DueState.OK)
    due_on: date | None = None
    if task.every_days is not None:
        base = last.done_on if last is not None else start
        due_on = base + timedelta(days=task.every_days)
        left_days = (due_on - today).days
        remaining["days"] = Decimal(left_days)
        soon = max(DUE_SOON_MIN_DAYS, task.every_days // 10)
        if left_days < 0:
            states.append(DueState.OVERDUE if -left_days > task.tolerance_days else DueState.DUE)
        elif left_days == 0:
            states.append(DueState.DUE)
        elif left_days <= soon:
            states.append(DueState.DUE_SOON)
        else:
            states.append(DueState.OK)
    state = max(states, key=lambda s: s.rank) if states else DueState.OK
    return TaskDue(task, state, remaining, due_on, last.done_on if last else None)


def last_completions(
    completions: Iterable[TaskCompletion],
) -> dict[MaintenanceTaskId, TaskCompletion]:
    latest: dict[MaintenanceTaskId, TaskCompletion] = {}
    for c in completions:
        current = latest.get(c.task_id)
        if current is None or (c.done_on, c.sequence) >= (current.done_on, current.sequence):
            latest[c.task_id] = c
    return latest


# ---------------------------------------------------------------------- default programme


def _task_id(code: str) -> MaintenanceTaskId:
    return MaintenanceTaskId(uuid.uuid5(uuid.NAMESPACE_URL, f"ims:maintenance-task:{code}"))


@dataclass(frozen=True, slots=True)
class DefaultTask:
    code: str
    item_code: str
    name: str
    every_hours: str | None = None
    every_cycles: int | None = None
    every_landings: int | None = None
    every_days: int | None = None
    tolerance_hours: str = "0"
    tolerance_days: int = 0
    life_limit: bool = False
    instructions: str = ""

    def build(self, effective_from: date) -> MaintenanceTask:
        return MaintenanceTask(
            id=_task_id(self.code), item_type_id=default_item_type_id(self.item_code),
            name=self.name,
            every_hours=Decimal(self.every_hours) if self.every_hours else None,
            every_cycles=self.every_cycles, every_landings=self.every_landings,
            every_days=self.every_days, tolerance_hours=Decimal(self.tolerance_hours),
            tolerance_days=self.tolerance_days, life_limit=self.life_limit,
            instructions=self.instructions, effective_from=effective_from,
        )  # fmt: skip


DEFAULT_PROGRAMME: tuple[DefaultTask, ...] = (
    # Starting values to adjust to the manufacturers' manuals; every one can be edited.
    DefaultTask("drone-50h", "DRONE_AIRFRAME", "Routine inspection", every_hours="50",
                every_days=90, tolerance_hours="5", tolerance_days=7,
                instructions="Frame, arms and fasteners; motor mounts; wiring; IMU and compass "
                             "calibration; test flight."),
    DefaultTask("drone-annual", "DRONE_AIRFRAME", "Annual service", every_days=365,
                tolerance_days=14),
    DefaultTask("motor-bearing", "MOTOR", "Bearing and winding check", every_hours="100",
                tolerance_hours="10"),
    DefaultTask("motor-life", "MOTOR", "Motor life limit", every_hours="600", life_limit=True),
    DefaultTask("props-life", "PROPELLER_SET", "Propeller replacement", every_hours="100",
                life_limit=True, instructions="Replace the set; check for chips and cracks "
                                              "before every flight."),
    DefaultTask("gear-inspection", "LANDING_GEAR", "Landing gear inspection",
                every_landings=300),
    DefaultTask("gnss-check", "GNSS_RECEIVER", "Function check and firmware review",
                every_days=180, tolerance_days=14),
    DefaultTask("ppk-check", "PPK_BASE", "Function check and firmware review",
                every_days=180, tolerance_days=14),
)  # fmt: skip
