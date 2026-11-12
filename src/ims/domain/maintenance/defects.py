"""Defects: report, assess (ground now, or defer with a limitation), rectify.

Anyone can report a defect. A reporter who judges it unsafe grounds the item at once;
otherwise it waits for an administrator to assess it. A deferred defect leaves the item
usable *with a limitation* until a date. A defect is closed (rectified) only by a
completed work order, and the item returns to service only when an administrator
certifies that work order.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.common.errors import InvalidTransition
from ims.domain.common.ids import AssetId, DefectId, UserId, WorkOrderId
from ims.domain.common.model import UtcDateTime, VersionedRecord


class DefectState(StrEnum):
    REPORTED = "reported"  # waiting for assessment
    GROUNDED = "grounded"  # unsafe: the item is grounded until it is fixed
    DEFERRED = "deferred"  # usable with a limitation until a date
    RECTIFIED = "rectified"  # fixed by a work order
    CANCELLED = "cancelled"  # assessed as not a defect


DEFECT_TRANSITIONS = {
    DefectState.REPORTED: frozenset(
        {DefectState.GROUNDED, DefectState.DEFERRED, DefectState.CANCELLED}
    ),
    DefectState.DEFERRED: frozenset({DefectState.GROUNDED, DefectState.RECTIFIED}),
    DefectState.GROUNDED: frozenset({DefectState.RECTIFIED}),
    DefectState.RECTIFIED: frozenset(),
    DefectState.CANCELLED: frozenset(),
}

OPEN_STATES = frozenset({DefectState.REPORTED, DefectState.GROUNDED, DefectState.DEFERRED})


class Defect(VersionedRecord):
    id: DefectId
    number: str = Field(pattern=r"^DEF-\d{4,}$")
    asset_id: AssetId
    description: str = Field(min_length=3, max_length=2000)
    reported_by: UserId
    reported_at: UtcDateTime
    found_on: date
    state: DefectState = DefectState.REPORTED
    limitation: str = Field(default="", max_length=500)  # e.g. "Max wind 8 m/s"
    deferred_until: date | None = None
    assessed_by: UserId | None = None
    assessed_at: UtcDateTime | None = None
    assessment_note: str = Field(default="", max_length=1000)
    work_order_id: WorkOrderId | None = None

    @model_validator(mode="after")
    def _rules(self) -> Defect:
        problems: list[str] = []
        if self.state is DefectState.DEFERRED:
            if not self.limitation.strip():
                problems.append("a deferred defect needs the limitation the crew must respect")
            if self.deferred_until is None:
                problems.append("a deferred defect needs a date by which it is fixed")
        if self.state is DefectState.RECTIFIED and self.work_order_id is None:
            problems.append("a defect is rectified by a work order")
        if self.state is DefectState.CANCELLED and not self.assessment_note.strip():
            problems.append("say why this is not a defect")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_STATES

    def overdue_on(self, day: date) -> bool:
        """A deferral that has run out grounds the item like any overdue task."""
        return (
            self.state is DefectState.DEFERRED
            and self.deferred_until is not None
            and day > self.deferred_until
        )


def check_defect_transition(defect: Defect, new: DefectState) -> None:
    if new not in DEFECT_TRANSITIONS[defect.state]:
        raise InvalidTransition(f"A {defect.state.value} defect cannot become {new.value}.")


def next_number(prefix: str, existing: list[str]) -> str:
    """``DEF-0001``, ``WO-0001``: one more than the highest so far."""
    numbers = [int(n.split("-", 1)[1]) for n in existing if n.split("-", 1)[1].isdigit()]
    return f"{prefix}-{max(numbers, default=0) + 1:04d}"
