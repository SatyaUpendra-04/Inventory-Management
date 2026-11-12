"""Airworthiness questions every service asks: what is due on this item, does anything
ground it, and grounding it when the answer is yes.

Kept free of other services so check-out, field logs, returns, reservations and the
maintenance service can all use it without importing each other.
"""

from __future__ import annotations

from datetime import date, timedelta

from ims.application.context import Actor, CommandContext
from ims.application.ledgers import append_status
from ims.application.runner import add_once
from ims.domain.assets.status import USABLE, Serviceability, StatusChange, replay
from ims.domain.common.ids import AssetId, DefectId
from ims.domain.maintenance.defects import Defect, DefectState, next_number
from ims.domain.maintenance.programme import (
    DueState,
    TaskDue,
    due_status,
    last_completions,
)
from ims.domain.usage.ledger import totals
from ims.ports.clock import Clock
from ims.ports.repository import Storage


def task_states(storage: Storage, asset_id: AssetId, today: date) -> list[TaskDue]:
    """Every active programme task for this item, worst first."""
    asset = storage.assets.get(asset_id)
    if asset is None:
        return []
    tasks = [t for t in storage.maintenance_tasks.list() if t.item_type_id == asset.item_type_id]
    if not tasks:
        return []
    meters = totals(storage.usage.for_asset(asset_id))
    latest = last_completions(storage.completions.for_asset(asset_id))
    states = []
    for task in tasks:
        start = max(task.effective_from, asset.acquired_on or task.effective_from)
        states.append(
            due_status(task, meters=meters, today=today, last=latest.get(task.id), start=start)
        )
    return sorted(states, key=lambda d: (-d.state.rank, d.task.name))


def grounding_reasons(storage: Storage, asset_id: AssetId, today: date) -> list[str]:
    """Why this item must not fly or go out: overdue tasks, reached life limits, open
    grounding defects and deferrals that have run out."""
    reasons = [
        f"{d.task.name} {'life limit reached' if d.task.life_limit else 'overdue'} ({d.summary})"
        for d in task_states(storage, asset_id, today)
        if d.state is DueState.OVERDUE
    ]
    for defect in storage.defects.for_asset(asset_id):
        if defect.state is DefectState.GROUNDED:
            reasons.append(f"{defect.number} grounds it: {defect.description}")
        elif defect.overdue_on(today):
            reasons.append(
                f"{defect.number} was deferred until {defect.deferred_until:%d %b} and is not fixed"
            )
    return reasons


def planned_between(storage: Storage, asset_id: AssetId, start: date, end: date) -> list[str]:
    """Maintenance that falls due (by date) during a booking, or is already due."""
    planned = []
    for d in task_states(storage, asset_id, start):
        if d.state in {DueState.DUE, DueState.OVERDUE}:
            planned.append(
                f"{d.task.name} is {'overdue' if d.state is DueState.OVERDUE else 'due'}"
            )
        elif d.due_on is not None and start <= d.due_on <= end:
            planned.append(f"{d.task.name} due {d.due_on:%d %b}")
    for defect in storage.defects.for_asset(asset_id):
        if (
            defect.state is DefectState.DEFERRED
            and defect.deferred_until is not None
            and defect.deferred_until <= end
        ):
            planned.append(f"{defect.number} must be fixed by {defect.deferred_until:%d %b}")
    return planned


def ground_if_needed(
    storage: Storage, clock: Clock, ctx: CommandContext, actor: Actor, asset_id: AssetId,
    purpose: str,
) -> bool:  # fmt: skip
    """Grounds a usable item that something grounds (ARCHITECTURE §4.3). True if it did."""
    reasons = grounding_reasons(storage, asset_id, clock.today())
    if not reasons:
        return False
    status = replay(storage.status_events.for_asset(asset_id))
    if status.serviceability not in USABLE:
        return False
    append_status(
        storage, clock, ctx, actor, asset_id,
        StatusChange(serviceability=Serviceability.UNSERVICEABLE,
                     reason=f"Grounded automatically: {reasons[0]}"[:1000]),
        purpose=purpose,
    )  # fmt: skip
    return True


def add_defect(
    storage: Storage, clock: Clock, ctx: CommandContext, actor: Actor, asset_id: AssetId, *,
    description: str, found_on: date, state: DefectState = DefectState.REPORTED,
    purpose: str = "defect",
) -> Defect:  # fmt: skip
    """Records a defect with the next DEF number; idempotent within a command."""
    defect_id = DefectId(ctx.derive(purpose))
    existing = storage.defects.get(defect_id)
    if existing is not None:
        return existing
    number = next_number("DEF", [d.number for d in storage.defects.list()])
    defect = Defect.build(
        id=defect_id, number=number, asset_id=asset_id, description=description,
        reported_by=actor.user_id, reported_at=clock.now(), found_on=found_on, state=state,
        assessed_by=actor.user_id if state is DefectState.GROUNDED else None,
        assessed_at=clock.now() if state is DefectState.GROUNDED else None,
    )  # fmt: skip
    add_once(storage.defects.add, defect)
    return defect


DEFAULT_DEFERRAL = timedelta(days=14)
