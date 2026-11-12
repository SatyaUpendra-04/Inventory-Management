"""Work orders: open → in progress ⇄ awaiting parts → completed → certified.

A work order covers one item: scheduled tasks from the programme and/or defects to fix.
Opening it takes the item into maintenance. Completing it records each task as done (at
the item's current meter readings) and closes its defects. Only certification by an
administrator returns the item to service, and only when nothing else still grounds it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.common.errors import InvalidTransition
from ims.domain.common.ids import AssetId, DefectId, MaintenanceTaskId, UserId, WorkOrderId
from ims.domain.common.model import UtcDateTime, VersionedRecord


class WorkOrderState(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    AWAITING_PARTS = "awaiting_parts"
    COMPLETED = "completed"  # work done, waiting for sign-off
    CERTIFIED = "certified"  # returned to service by an administrator
    CANCELLED = "cancelled"


WORK_ORDER_TRANSITIONS = {
    WorkOrderState.OPEN: frozenset({WorkOrderState.IN_PROGRESS, WorkOrderState.CANCELLED}),
    WorkOrderState.IN_PROGRESS: frozenset(
        {WorkOrderState.AWAITING_PARTS, WorkOrderState.COMPLETED, WorkOrderState.CANCELLED}
    ),
    WorkOrderState.AWAITING_PARTS: frozenset(
        {WorkOrderState.IN_PROGRESS, WorkOrderState.CANCELLED}
    ),
    WorkOrderState.COMPLETED: frozenset({WorkOrderState.CERTIFIED, WorkOrderState.IN_PROGRESS}),
    WorkOrderState.CERTIFIED: frozenset(),
    WorkOrderState.CANCELLED: frozenset(),
}

OPEN_WORK = frozenset(
    {
        WorkOrderState.OPEN,
        WorkOrderState.IN_PROGRESS,
        WorkOrderState.AWAITING_PARTS,
        WorkOrderState.COMPLETED,
    }
)


class WorkOrder(VersionedRecord):
    id: WorkOrderId
    number: str = Field(pattern=r"^WO-\d{4,}$")
    asset_id: AssetId
    title: str = Field(min_length=1, max_length=120)
    task_ids: tuple[MaintenanceTaskId, ...] = ()
    defect_ids: tuple[DefectId, ...] = ()
    state: WorkOrderState = WorkOrderState.OPEN
    opened_by: UserId
    opened_at: UtcDateTime
    work_done: str = Field(default="", max_length=4000)
    parts: str = Field(default="", max_length=2000)
    completed_by: UserId | None = None
    completed_at: UtcDateTime | None = None
    certified_by: UserId | None = None
    certified_at: UtcDateTime | None = None
    note: str = Field(default="", max_length=1000)  # e.g. why it was cancelled or reopened

    @model_validator(mode="after")
    def _rules(self) -> WorkOrder:
        problems: list[str] = []
        if len(set(self.task_ids)) != len(self.task_ids):
            problems.append("each task once")
        if len(set(self.defect_ids)) != len(self.defect_ids):
            problems.append("each defect once")
        if self.state in {WorkOrderState.COMPLETED, WorkOrderState.CERTIFIED}:
            if not self.work_done.strip():
                problems.append("describe the work done")
            if self.completed_by is None:
                problems.append("a completed work order names who did it")
        if self.state is WorkOrderState.CERTIFIED and self.certified_by is None:
            problems.append("a certified work order names who signed it off")
        if self.state is WorkOrderState.CANCELLED and not self.note.strip():
            problems.append("say why the work order is cancelled")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_WORK


def check_work_order_transition(order: WorkOrder, new: WorkOrderState) -> None:
    if new not in WORK_ORDER_TRANSITIONS[order.state]:
        raise InvalidTransition(
            f"A work order that is {order.state.value.replace('_', ' ')} cannot become "
            f"{new.value.replace('_', ' ')}."
        )
