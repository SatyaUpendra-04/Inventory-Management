"""Configuration: which components are installed on which drone, and when (ARCHITECTURE §3).

Every install and removal is an appended event in the component's own stream, so each
motor, propeller set or camera keeps a complete record of the airframes it has flown on.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.catalogue import Category, ItemType
from ims.domain.assets.status import AssetStatus, Serviceability
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, CommandId, EntryId, UserId
from ims.domain.common.model import UtcDateTime, ValueModel


class ConfigChange(StrEnum):
    INSTALLED = "installed"
    REMOVED = "removed"


class ConfigEvent(ValueModel):
    id: EntryId
    component_id: AssetId
    sequence: int = Field(ge=1)  # 1, 2, 3 ... per component; storage rejects duplicates
    change: ConfigChange
    parent_id: AssetId  # the airframe it was installed on or removed from
    position: str = Field(default="", max_length=40)  # e.g. "Motor 1", "Payload"
    recorded_at: UtcDateTime
    recorded_by: UserId
    command_id: CommandId
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _not_on_itself(self) -> ConfigEvent:
        if self.component_id == self.parent_id:
            raise ValueError("a component cannot be installed on itself")
        return self


@dataclass(frozen=True, slots=True)
class Placement:
    parent_id: AssetId
    position: str


def current_placement(events: Iterable[ConfigEvent]) -> Placement | None:
    """Where a component is now (``None`` if loose), checking the history is consistent."""
    placement: Placement | None = None
    for expected, event in enumerate(events, start=1):
        if event.sequence != expected:
            raise RuleViolation(f"Configuration history is broken at event {event.id}.")
        if event.change is ConfigChange.INSTALLED:
            if placement is not None:
                raise RuleViolation(f"Configuration history installs twice at event {event.id}.")
            placement = Placement(event.parent_id, event.position)
        else:
            if placement is None or placement.parent_id != event.parent_id:
                raise RuleViolation(f"Configuration history removes wrongly at event {event.id}.")
            placement = None
    return placement


def check_install(
    *,
    component_type: ItemType,
    component_status: AssetStatus,
    component_placement: Placement | None,
    parent_type: ItemType,
    parent_status: AssetStatus,
    position: str,
    occupied_positions: Iterable[str],
) -> None:
    """Rules for fitting a component to an airframe (raises :class:`RuleViolation`)."""
    problems: list[str] = []
    if not component_type.is_component:
        problems.append(f"{component_type.name} is not a component that can be installed")
    if parent_type.category is not Category.DRONE:
        problems.append("components can only be installed on a drone airframe")
    if component_placement is not None:
        problems.append("this component is already installed; remove it first")
    if component_status.serviceability not in {Serviceability.SERVICEABLE, Serviceability.LIMITED}:
        problems.append("grounded or retired components cannot be installed")
    if parent_status.serviceability is Serviceability.RETIRED:
        problems.append("nothing can be installed on a retired airframe")
    taken = {p.strip().lower(): p.strip() for p in occupied_positions if p.strip()}
    if position.strip() and position.strip().lower() in taken:
        existing = taken[position.strip().lower()]
        problems.append(f"position {existing} on this airframe is already taken")
    if problems:
        raise RuleViolation(problems)
