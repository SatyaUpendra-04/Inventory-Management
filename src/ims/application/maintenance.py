"""Maintenance: the programme, what is due, defects, work orders and return to service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from ims.application.airworthiness import (
    add_defect,
    ground_if_needed,
    grounding_reasons,
    task_states,
)
from ims.application.context import Actor, CommandContext
from ims.application.ledgers import append_status
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import ItemType, Meter
from ims.domain.assets.status import (
    Custody,
    Serviceability,
    StatusChange,
    replay,
)
from ims.domain.common.errors import ConflictError, NotFound, RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DefectId,
    EntryId,
    MaintenanceTaskId,
    WorkOrderId,
)
from ims.domain.identity.roles import Permission
from ims.domain.maintenance.defects import (
    Defect,
    DefectState,
    check_defect_transition,
    next_number,
)
from ims.domain.maintenance.programme import (
    DEFAULT_PROGRAMME,
    DueState,
    MaintenanceTask,
    TaskCompletion,
    TaskDue,
    check_new_completion,
)
from ims.domain.maintenance.work_orders import (
    WorkOrder,
    WorkOrderState,
    check_work_order_transition,
)
from ims.domain.usage.ledger import totals
from ims.ports.clock import Clock
from ims.ports.repository import Storage

TASK_FIELDS = frozenset(
    {"name", "every_hours", "every_cycles", "every_landings", "every_days", "tolerance_hours",
     "tolerance_cycles", "tolerance_landings", "tolerance_days", "life_limit", "instructions",
     "is_active"}
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class DueItem:
    """One row of the fleet-wide due list."""

    asset: Asset
    item_type: ItemType
    due: TaskDue


class MaintenanceService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ queries

    def tasks(self, actor: Actor, *, include_inactive: bool = False) -> list[MaintenanceTask]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.maintenance_tasks.list(include_inactive=include_inactive)

    def asset_due(self, actor: Actor, asset_id: AssetId) -> list[TaskDue]:
        actor.require(Permission.ASSET_VIEW)
        return task_states(self._s, asset_id, self._clock.today())

    def grounding_reasons(self, actor: Actor, asset_id: AssetId) -> list[str]:
        actor.require(Permission.ASSET_VIEW)
        return grounding_reasons(self._s, asset_id, self._clock.today())

    def due_list(self, actor: Actor) -> list[DueItem]:
        """Every task that is due soon, due or overdue across the fleet, worst first."""
        actor.require(Permission.ASSET_VIEW)
        today = self._clock.today()
        types = {t.id: t for t in self._s.item_types.list(include_inactive=True)}
        programmed = {t.item_type_id for t in self._s.maintenance_tasks.list()}
        rows: list[DueItem] = []
        for asset in self._s.assets.list():
            if asset.item_type_id not in programmed:
                continue
            if (
                replay(self._s.status_events.for_asset(asset.id)).serviceability
                is Serviceability.RETIRED
            ):
                continue
            for due in task_states(self._s, asset.id, today):
                if due.state is not DueState.OK:
                    rows.append(DueItem(asset, types[asset.item_type_id], due))
        return sorted(
            rows, key=lambda r: (-r.due.state.rank, min(r.due.remaining.values(), default=0))
        )

    def completions(self, actor: Actor, asset_id: AssetId) -> list[TaskCompletion]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.completions.for_asset(asset_id)

    def defects(self, actor: Actor) -> list[Defect]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.defects.list()

    def work_orders(self, actor: Actor) -> list[WorkOrder]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.work_orders.list()

    def work_order(self, actor: Actor, work_order_id: WorkOrderId) -> WorkOrder:
        actor.require(Permission.ASSET_VIEW)
        return self._order(work_order_id)

    # ------------------------------------------------------------------ programme

    def install_default_programme(self, ctx: CommandContext) -> int:
        """Adds the starting programme (once); every task can then be edited."""
        ctx.require_actor().require(Permission.MAINTENANCE_MANAGE)
        added: list[str] = []

        def execute() -> Outcome:
            for default in DEFAULT_PROGRAMME:
                task = default.build(self._clock.today())
                if (
                    self._s.item_types.get(task.item_type_id) is not None
                    and self._s.maintenance_tasks.get(task.id) is None
                ):
                    add_once(self._s.maintenance_tasks.add, task)
                    added.append(default.code)
            return Outcome("maintenance_programme", "defaults", None, {"added": added})

        self._run.run(ctx, "maintenance.install_defaults", execute)
        return len(added)

    def add_task(
        self, ctx: CommandContext, *, item_type_id: Any, **fields: Any
    ) -> MaintenanceTaskId:
        ctx.require_actor().require(Permission.MAINTENANCE_MANAGE)
        self._check_fields(fields)
        task_id = MaintenanceTaskId(ctx.derive("maintenance-task"))

        def execute() -> Outcome:
            if self._s.item_types.get(item_type_id) is None:
                raise NotFound("Item type not found.")
            task = MaintenanceTask.build(
                id=task_id, item_type_id=item_type_id, effective_from=self._clock.today(), **fields
            )
            add_once(self._s.maintenance_tasks.add, task)
            return Outcome("maintenance_task", str(task_id), None, task.model_dump(mode="json"))

        self._run.run(ctx, "maintenance.add_task", execute)
        return task_id

    def update_task(
        self, ctx: CommandContext, task_id: MaintenanceTaskId, expected_version: int, **changes: Any
    ) -> None:
        ctx.require_actor().require(Permission.MAINTENANCE_MANAGE)
        self._check_fields(changes)

        def execute() -> Outcome:
            stored = self._s.maintenance_tasks.get(task_id)
            if stored is None:
                raise NotFound("Task not found.")
            candidate = stored.next_version(**changes)
            if stored.version == expected_version + 1 and _same(stored, candidate):
                return Outcome("maintenance_task", str(task_id), None, None)
            if stored.version != expected_version:
                raise ConflictError("This task was changed by someone else. Reload and try again.")
            update_once(self._s.maintenance_tasks.update,
                        lambda: self._s.maintenance_tasks.get(task_id), candidate)  # fmt: skip
            return Outcome(
                "maintenance_task", str(task_id), stored.model_dump(mode="json"),
                candidate.model_dump(mode="json"),
            )  # fmt: skip

        self._run.run(ctx, "maintenance.update_task", execute)

    def record_completion(
        self,
        ctx: CommandContext,
        asset_id: AssetId,
        task_id: MaintenanceTaskId,
        *,
        done_on: date | None = None,
        meters: Mapping[Meter, Decimal] | None = None,
        notes: str = "",
    ) -> EntryId:
        """Records maintenance done outside a work order, e.g. the last service before the
        item was registered here. ``meters`` default to the item's readings now."""
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)
        entry_id = EntryId(ctx.derive("completion"))

        def execute() -> Outcome:
            asset = self._asset(asset_id)
            task = self._task(task_id)
            if task.item_type_id != asset.item_type_id:
                raise RuleViolation("That task is not in this item's maintenance programme.")
            if task.life_limit:
                raise RuleViolation(
                    f"{task.name} is a life limit: replace the part instead of recording it "
                    "as done."
                )
            done = self._complete(ctx, actor, asset_id, task_id, done_on or self._clock.today(),
                                  meters, notes, None, "completion")  # fmt: skip
            return Outcome("task_completion", str(entry_id), None, done.model_dump(mode="json"))

        self._run.run(ctx, "maintenance.record", execute)
        return entry_id

    # ------------------------------------------------------------------ defects

    def report_defect(
        self, ctx: CommandContext, asset_id: AssetId, *, description: str,
        found_on: date | None = None, unsafe: bool = False,
    ) -> DefectId:  # fmt: skip
        """Anyone can report. An unsafe defect grounds the item at once."""
        actor = ctx.require_actor()
        actor.require(Permission.DEFECT_REPORT)
        defect_id = DefectId(ctx.derive("defect"))

        def execute() -> Outcome:
            self._asset(asset_id)
            day = found_on or self._clock.today()
            if day > self._clock.today():
                raise RuleViolation("A defect cannot be found in the future.")
            state = DefectState.GROUNDED if unsafe else DefectState.REPORTED
            defect = add_defect(self._s, self._clock, ctx, actor, asset_id,
                                description=description, found_on=day, state=state)  # fmt: skip
            if unsafe:
                self._ground(ctx, actor, asset_id, f"{defect.number}: {description}", "ground")
            return Outcome("defect", str(defect_id), None, defect.model_dump(mode="json"))

        self._run.run(ctx, "defect.report", execute)
        return defect_id

    def assess_defect(
        self, ctx: CommandContext, defect_id: DefectId, expected_version: int, *,
        decision: DefectState, limitation: str = "", deferred_until: date | None = None,
        note: str = "",
    ) -> None:  # fmt: skip
        """Ground it, defer it with a limitation until a date, or cancel it."""
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)
        if decision not in {DefectState.GROUNDED, DefectState.DEFERRED, DefectState.CANCELLED}:
            raise RuleViolation("Ground, defer or cancel the defect.")

        def execute() -> Outcome:
            stored = self._defect(defect_id)
            if stored.state is decision and stored.version == expected_version + 1:
                return Outcome("defect", str(defect_id), None, {"state": decision.value})
            if stored.version != expected_version:
                raise ConflictError(
                    "This defect was changed by someone else. Reload and try again."
                )
            check_defect_transition(stored, decision)
            if (
                decision is DefectState.DEFERRED
                and deferred_until is not None
                and (deferred_until < self._clock.today())
            ):
                raise RuleViolation("The deferral must run to today or later.")
            after = stored.next_version(
                state=decision, limitation=limitation.strip(), deferred_until=deferred_until,
                assessed_by=actor.user_id, assessed_at=self._clock.now(),
                assessment_note=note.strip(),
            )  # fmt: skip
            status = replay(self._s.status_events.for_asset(stored.asset_id))
            if decision is DefectState.GROUNDED:
                self._ground(ctx, actor, stored.asset_id,
                             f"{stored.number}: {stored.description}", "ground")  # fmt: skip
            elif (
                decision is DefectState.DEFERRED
                and status.serviceability is Serviceability.SERVICEABLE
            ):
                append_status(
                    self._s, self._clock, ctx, actor, stored.asset_id,
                    StatusChange(serviceability=Serviceability.LIMITED,
                                 reason=f"{stored.number} deferred: {limitation.strip()}"),
                    purpose="limit",
                )  # fmt: skip
            update_once(self._s.defects.update, lambda: self._s.defects.get(defect_id), after)
            return Outcome(
                "defect", str(defect_id), {"state": stored.state.value},
                {"state": decision.value, "limitation": limitation, "note": note},
            )  # fmt: skip

        self._run.run(ctx, f"defect.{decision.value}", execute)

    # ------------------------------------------------------------------ work orders

    def open_work_order(
        self, ctx: CommandContext, asset_id: AssetId, *, title: str,
        task_ids: Sequence[MaintenanceTaskId] = (), defect_ids: Sequence[DefectId] = (),
    ) -> WorkOrderId:  # fmt: skip
        """Opens a work order and takes the item into maintenance."""
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)
        order_id = WorkOrderId(ctx.derive("work-order"))

        def execute() -> Outcome:
            order = self._s.work_orders.get(order_id)
            if order is None:
                asset = self._asset(asset_id)
                problems: list[str] = []
                for task_id in task_ids:
                    if self._task(task_id).item_type_id != asset.item_type_id:
                        problems.append("A task is not in this item's maintenance programme.")
                for defect_id in defect_ids:
                    defect = self._defect(defect_id)
                    if defect.asset_id != asset_id or not defect.is_open:
                        problems.append(f"{defect.number} is not an open defect on this item.")
                    elif defect.work_order_id is not None:
                        problems.append(f"{defect.number} is already on a work order.")
                if any(w.is_open for w in self._s.work_orders.for_asset(asset_id)):
                    problems.append("This item already has an open work order; add to that one.")
                status = replay(self._s.status_events.for_asset(asset_id))
                if status.custody is Custody.DEPLOYED:
                    problems.append("The item is out on a project; return it first.")
                if problems:
                    raise RuleViolation(problems)
                number = next_number("WO", [w.number for w in self._s.work_orders.list()])
                order = WorkOrder.build(
                    id=order_id, number=number, asset_id=asset_id, title=title,
                    task_ids=tuple(task_ids), defect_ids=tuple(defect_ids),
                    opened_by=actor.user_id, opened_at=self._clock.now(),
                )  # fmt: skip
                add_once(self._s.work_orders.add, order)
            status = replay(self._s.status_events.for_asset(asset_id))
            if status.custody in {Custody.IN_STORE, Custody.RESERVED, Custody.IN_TRANSIT}:
                append_status(
                    self._s, self._clock, ctx, actor, asset_id,
                    StatusChange(custody=Custody.IN_MAINTENANCE, reason=f"{order.number}: {title}"),
                    purpose="into-maintenance",
                )  # fmt: skip
            for defect_id in order.defect_ids:
                defect = self._defect(defect_id)
                if defect.work_order_id is None:
                    linked = defect.next_version(work_order_id=order_id)
                    self._save_defect(linked)
            return Outcome("work_order", str(order_id), None, order.model_dump(mode="json"))

        self._run.run(ctx, "work_order.open", execute)
        return order_id

    def move_work_order(
        self, ctx: CommandContext, work_order_id: WorkOrderId, expected_version: int,
        state: WorkOrderState, note: str = "",
    ) -> None:  # fmt: skip
        """Start, wait for parts, resume, reopen after a refused sign-off, or cancel."""
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)
        if state in {WorkOrderState.COMPLETED, WorkOrderState.CERTIFIED}:
            raise RuleViolation("Use complete or certify for that step.")

        def execute() -> Outcome:
            stored = self._order(work_order_id)
            if stored.state is state and stored.version == expected_version + 1:
                return Outcome("work_order", str(work_order_id), None, {"state": state.value})
            self._expect(stored, expected_version)
            check_work_order_transition(stored, state)
            after = stored.next_version(state=state, note=note.strip() or stored.note)
            if state is WorkOrderState.CANCELLED:
                for defect_id in stored.defect_ids:  # the defects stay open, unassigned
                    defect = self._defect(defect_id)
                    if defect.work_order_id == work_order_id and defect.is_open:
                        self._save_defect(defect.next_version(work_order_id=None))
                status = replay(self._s.status_events.for_asset(stored.asset_id))
                if status.custody is Custody.IN_MAINTENANCE:
                    append_status(
                        self._s, self._clock, ctx, actor, stored.asset_id,
                        StatusChange(custody=Custody.IN_STORE,
                                     reason=f"{stored.number} cancelled"),
                        purpose="back-to-store",
                    )  # fmt: skip
            update_once(self._s.work_orders.update,
                        lambda: self._s.work_orders.get(work_order_id), after)  # fmt: skip
            return Outcome(
                "work_order", str(work_order_id), {"state": stored.state.value},
                {"state": state.value, "note": note},
            )  # fmt: skip

        self._run.run(ctx, f"work_order.{state.value}", execute)

    def complete_work_order(
        self, ctx: CommandContext, work_order_id: WorkOrderId, expected_version: int, *,
        work_done: str, parts: str = "",
    ) -> None:  # fmt: skip
        """Records the work: each task is done at today's readings; defects are fixed."""
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)

        def execute() -> Outcome:
            stored = self._order(work_order_id)
            if stored.state is WorkOrderState.COMPLETED and stored.version == expected_version + 1:
                return Outcome("work_order", str(work_order_id), None, {"state": "completed"})
            self._expect(stored, expected_version)
            check_work_order_transition(stored, WorkOrderState.COMPLETED)
            today = self._clock.today()
            for task_id in stored.task_ids:
                task = self._task(task_id)
                if task.life_limit:
                    raise RuleViolation(
                        f"{task.name} is a life limit: replace the part (remove it and fit a new "
                        "one) rather than completing it."
                    )
            for task_id in stored.task_ids:
                self._complete(ctx, actor, stored.asset_id, task_id, today, None,
                               f"{stored.number}: {work_done.strip()}"[:2000], work_order_id,
                               f"done:{task_id}")  # fmt: skip
            for defect_id in stored.defect_ids:
                defect = self._defect(defect_id)
                if defect.is_open:
                    fixed = defect.next_version(state=DefectState.RECTIFIED,
                                                work_order_id=work_order_id)  # fmt: skip
                    self._save_defect(fixed)
            after = stored.next_version(
                state=WorkOrderState.COMPLETED, work_done=work_done.strip(), parts=parts.strip(),
                completed_by=actor.user_id, completed_at=self._clock.now(),
            )  # fmt: skip
            update_once(self._s.work_orders.update,
                        lambda: self._s.work_orders.get(work_order_id), after)  # fmt: skip
            return Outcome("work_order", str(work_order_id), {"state": stored.state.value},
                           after.model_dump(mode="json"))  # fmt: skip

        self._run.run(ctx, "work_order.complete", execute)

    def certify(
        self, ctx: CommandContext, work_order_id: WorkOrderId, expected_version: int
    ) -> None:
        """Return to service: an administrator signs off the completed work."""
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_CERTIFY)

        def execute() -> Outcome:
            stored = self._order(work_order_id)
            if stored.state is WorkOrderState.CERTIFIED and stored.version == expected_version + 1:
                return Outcome("work_order", str(work_order_id), None, {"state": "certified"})
            self._expect(stored, expected_version)
            check_work_order_transition(stored, WorkOrderState.CERTIFIED)
            reasons = grounding_reasons(self._s, stored.asset_id, self._clock.today())
            if reasons:
                raise RuleViolation(["It cannot return to service yet:", *reasons])
            deferred = [
                d for d in self._s.defects.for_asset(stored.asset_id)
                if d.state is DefectState.DEFERRED
            ]  # fmt: skip
            target = Serviceability.LIMITED if deferred else Serviceability.SERVICEABLE
            status = replay(self._s.status_events.for_asset(stored.asset_id))
            change = StatusChange(
                serviceability=target if status.serviceability is not target else None,
                custody=Custody.IN_STORE if status.custody is Custody.IN_MAINTENANCE else None,
                reason=f"{stored.number} certified: returned to service",
            )
            if change.serviceability is not None or change.custody is not None:
                append_status(self._s, self._clock, ctx, actor, stored.asset_id, change,
                              purpose="return-to-service")  # fmt: skip
            after = stored.next_version(
                state=WorkOrderState.CERTIFIED, certified_by=actor.user_id,
                certified_at=self._clock.now(),
            )  # fmt: skip
            update_once(self._s.work_orders.update,
                        lambda: self._s.work_orders.get(work_order_id), after)  # fmt: skip
            return Outcome("work_order", str(work_order_id), {"state": "completed"},
                           {"state": "certified", "serviceability": target.value})  # fmt: skip

        self._run.run(ctx, "work_order.certify", execute)

    # ------------------------------------------------------------------ sweep

    def ground_overdue(self, ctx: CommandContext) -> int:
        """Grounds every usable item that something now grounds (as days pass, calendar
        tasks and deferrals run out). Safe to run at any time."""
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)
        grounded: list[str] = []

        def execute() -> Outcome:
            for asset in self._s.assets.list():
                if ground_if_needed(self._s, self._clock, ctx, actor, asset.id,
                                    f"sweep:{asset.id}"):  # fmt: skip
                    grounded.append(asset.asset_tag)
            return Outcome("maintenance_sweep", str(ctx.command_id), None, {"grounded": grounded})

        self._run.run(ctx, "maintenance.ground_overdue", execute)
        return len(grounded)

    # ------------------------------------------------------------------ helpers

    def _complete(
        self, ctx: CommandContext, actor: Actor, asset_id: AssetId, task_id: MaintenanceTaskId,
        done_on: date, meters: Mapping[Meter, Decimal] | None, notes: str,
        work_order_id: WorkOrderId | None, purpose: str,
    ) -> TaskCompletion:  # fmt: skip
        existing = self._s.completions.for_asset(asset_id)
        entry_id = EntryId(ctx.derive(purpose))
        done = next((c for c in existing if c.id == entry_id), None)
        if done is not None:
            return done
        readings = dict(meters) if meters is not None else totals(self._s.usage.for_asset(asset_id))
        completion = TaskCompletion.build(
            id=entry_id, asset_id=asset_id, sequence=len(existing) + 1, task_id=task_id,
            done_on=done_on, meters=readings, work_order_id=work_order_id, notes=notes,
            recorded_at=self._clock.now(), recorded_by=actor.user_id, command_id=ctx.command_id,
        )  # fmt: skip
        check_new_completion(existing, completion, self._clock.today())
        add_once(self._s.completions.append, completion)
        return completion

    def _ground(
        self, ctx: CommandContext, actor: Actor, asset_id: AssetId, reason: str, purpose: str
    ) -> None:
        status = replay(self._s.status_events.for_asset(asset_id))
        if status.serviceability in {Serviceability.SERVICEABLE, Serviceability.LIMITED}:
            append_status(
                self._s, self._clock, ctx, actor, asset_id,
                StatusChange(serviceability=Serviceability.UNSERVICEABLE, reason=reason[:1000]),
                purpose=purpose,
            )  # fmt: skip

    def _save_defect(self, defect: Defect) -> None:
        update_once(self._s.defects.update, lambda: self._s.defects.get(defect.id), defect)

    def _expect(self, order: WorkOrder, expected_version: int) -> None:
        if order.version != expected_version:
            raise ConflictError(
                "This work order was changed by someone else. Reload and try again."
            )

    def _asset(self, asset_id: AssetId) -> Asset:
        asset = self._s.assets.get(asset_id)
        if asset is None or asset.is_deleted:
            raise NotFound("Asset not found.")
        return asset

    def _task(self, task_id: MaintenanceTaskId) -> MaintenanceTask:
        task = self._s.maintenance_tasks.get(task_id)
        if task is None:
            raise NotFound("Maintenance task not found.")
        return task

    def _defect(self, defect_id: DefectId) -> Defect:
        defect = self._s.defects.get(defect_id)
        if defect is None:
            raise NotFound("Defect not found.")
        return defect

    def _order(self, work_order_id: WorkOrderId) -> WorkOrder:
        order = self._s.work_orders.get(work_order_id)
        if order is None:
            raise NotFound("Work order not found.")
        return order

    def _check_fields(self, fields: Mapping[str, Any]) -> None:
        unknown = set(fields) - TASK_FIELDS
        if unknown:
            raise RuleViolation(f"These fields cannot be set here: {', '.join(sorted(unknown))}.")


def _same(a: MaintenanceTask, b: MaintenanceTask) -> bool:
    return a.model_dump(exclude={"version"}) == b.model_dump(exclude={"version"})
