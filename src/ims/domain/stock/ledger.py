"""Stock ledger for consumables (ARCHITECTURE.md §4.5a).

Two balances are derived from the movements:

* **On hand** at each store location.
* **Outstanding** with each project: issued, not yet returned or consumed.

Neither balance may go below zero, and neither is ever typed in directly.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.catalogue import ItemType, TrackingMode
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import CommandId, EntryId, ItemTypeId, LocationId, ProjectId, UserId
from ims.domain.common.model import UtcDateTime, ValueModel


class MovementKind(StrEnum):
    RECEIVED = "received"  # purchase / delivery into a store            store +
    ISSUED = "issued"  # handed to a project at deployment                store -, project +
    RETURNED = "returned"  # brought back after the project               store +, project -
    CONSUMED = "consumed"  # used up or left on site during the project   project -
    WRITTEN_OFF = "written_off"  # lost or damaged while in store         store -
    ADJUSTED = "adjusted"  # stock-count correction (signed)              store ±


_NEEDS_PROJECT = frozenset({MovementKind.ISSUED, MovementKind.RETURNED, MovementKind.CONSUMED})
_NEEDS_REASON = frozenset({MovementKind.WRITTEN_OFF, MovementKind.ADJUSTED})


class StockMovement(ValueModel):
    id: EntryId
    item_type_id: ItemTypeId
    sequence: int = Field(ge=1)  # 1, 2, 3 ... per item type; storage rejects duplicates
    location_id: LocationId
    kind: MovementKind
    quantity: int  # positive, except ADJUSTED which is signed
    recorded_at: UtcDateTime
    recorded_by: UserId
    command_id: CommandId
    project_id: ProjectId | None = None
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _rules(self) -> StockMovement:
        problems: list[str] = []
        if self.kind is MovementKind.ADJUSTED:
            if self.quantity == 0:
                problems.append("an adjustment must change the quantity")
        elif self.quantity <= 0:
            problems.append("quantity must be greater than zero")
        if (self.kind in _NEEDS_PROJECT) != (self.project_id is not None):
            problems.append(
                "issues, returns and consumption must name a project; other movements must not"
            )
        if self.kind in _NEEDS_REASON and not self.reason.strip():
            problems.append("write-offs and adjustments need a reason")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def store_delta(self) -> int:
        match self.kind:
            case MovementKind.RECEIVED | MovementKind.RETURNED:
                return self.quantity
            case MovementKind.ISSUED | MovementKind.WRITTEN_OFF:
                return -self.quantity
            case MovementKind.ADJUSTED:
                return self.quantity
            case MovementKind.CONSUMED:
                return 0

    @property
    def project_delta(self) -> int:
        match self.kind:
            case MovementKind.ISSUED:
                return self.quantity
            case MovementKind.RETURNED | MovementKind.CONSUMED:
                return -self.quantity
            case _:
                return 0


@dataclass(frozen=True, slots=True)
class StockPosition:
    on_hand: dict[LocationId, int]
    outstanding: dict[ProjectId, int]
    consumed: dict[ProjectId, int]

    def on_hand_at(self, location_id: LocationId) -> int:
        return self.on_hand.get(location_id, 0)

    def outstanding_with(self, project_id: ProjectId) -> int:
        return self.outstanding.get(project_id, 0)

    @property
    def total_on_hand(self) -> int:
        return sum(self.on_hand.values())


def position(movements: Iterable[StockMovement]) -> StockPosition:
    """Balances for one item type."""
    on_hand: dict[LocationId, int] = {}
    outstanding: dict[ProjectId, int] = {}
    consumed: dict[ProjectId, int] = {}
    for m in movements:
        on_hand[m.location_id] = on_hand.get(m.location_id, 0) + m.store_delta
        if m.project_id is not None:
            outstanding[m.project_id] = outstanding.get(m.project_id, 0) + m.project_delta
            if m.kind is MovementKind.CONSUMED:
                consumed[m.project_id] = consumed.get(m.project_id, 0) + m.quantity
    return StockPosition(on_hand=on_hand, outstanding=outstanding, consumed=consumed)


def check_new_movement(
    existing: Sequence[StockMovement], movement: StockMovement, item_type: ItemType
) -> None:
    """Validates ``movement`` against the item type and the current balances."""
    problems: list[str] = []
    if item_type.id != movement.item_type_id:
        problems.append("movement does not belong to this item type")
    if item_type.tracking is not TrackingMode.CONSUMABLE:
        problems.append(f"{item_type.name} is tracked individually, not as stock")
    if any(m.id == movement.id for m in existing):
        problems.append("this movement has already been recorded")
    if movement.sequence != len(existing) + 1:
        problems.append("stock was moved by someone else meanwhile; reload and try again")
    if not problems:
        current = position(existing)
        new_store = current.on_hand_at(movement.location_id) + movement.store_delta
        if new_store < 0:
            problems.append(
                f"only {current.on_hand_at(movement.location_id)} {item_type.name}(s) "
                "are in this store"
            )
        if movement.project_id is not None:
            outstanding = current.outstanding_with(movement.project_id)
            if outstanding + movement.project_delta < 0:
                problems.append(
                    f"the project only has {outstanding} {item_type.name}(s) outstanding"
                )
    if problems:
        raise RuleViolation(problems)


def needs_reorder(on_hand: int, reorder_level: int) -> bool:
    return on_hand <= reorder_level
