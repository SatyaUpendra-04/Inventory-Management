"""Projects: a survey job at a mine site, with its crew and dates."""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from types import MappingProxyType

from pydantic import Field, field_validator, model_validator

from ims.domain.common.errors import InvalidTransition, RuleViolation
from ims.domain.common.ids import LocationId, ProjectId, UserId
from ims.domain.common.model import UtcDateTime, VersionedRecord
from ims.domain.identity.user import User

_CODE = re.compile(r"^PRJ-[A-Z0-9-]{2,20}$")


class ProjectStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"  # equipment is (or has been) out on site
    COMPLETED = "completed"
    CANCELLED = "cancelled"


PROJECT_TRANSITIONS: MappingProxyType[ProjectStatus, frozenset[ProjectStatus]] = MappingProxyType(
    {
        ProjectStatus.PLANNED: frozenset({ProjectStatus.ACTIVE, ProjectStatus.CANCELLED}),
        ProjectStatus.ACTIVE: frozenset({ProjectStatus.COMPLETED}),
        ProjectStatus.COMPLETED: frozenset({ProjectStatus.ACTIVE}),  # reopen
        ProjectStatus.CANCELLED: frozenset({ProjectStatus.PLANNED}),  # reinstate
    }
)


class Project(VersionedRecord):
    id: ProjectId
    code: str
    name: str = Field(min_length=1, max_length=120)
    site_id: LocationId
    client: str = Field(default="", max_length=120)
    starts_on: date
    ends_on: date | None = None
    chief_pilot_id: UserId | None = None
    surveyor_id: UserId | None = None
    status: ProjectStatus = ProjectStatus.PLANNED
    notes: str = Field(default="", max_length=2000)
    deleted_at: UtcDateTime | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        normalised = value.strip().upper().replace(" ", "-")
        if not normalised.startswith("PRJ-"):
            normalised = f"PRJ-{normalised}"
        if not _CODE.match(normalised):
            raise ValueError("project code must look like PRJ-KJR-2611 (letters, digits, '-')")
        return normalised

    @model_validator(mode="after")
    def _dates(self) -> Project:
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("the end date cannot be before the start date")
        return self

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_open(self) -> bool:
        return self.status in {ProjectStatus.PLANNED, ProjectStatus.ACTIVE}


def check_transition(project: Project, new_status: ProjectStatus, *, open_deployments: int) -> None:
    """Rules for moving a project between states (raises :class:`InvalidTransition`)."""
    if new_status is project.status:
        raise InvalidTransition(f"The project is already {new_status.value}.")
    if new_status not in PROJECT_TRANSITIONS[project.status]:
        raise InvalidTransition(
            f"A {project.status.value} project cannot become {new_status.value}."
        )
    if new_status in {ProjectStatus.COMPLETED, ProjectStatus.CANCELLED} and open_deployments:
        raise InvalidTransition(
            "Return all equipment from this project before closing it "
            f"({open_deployments} deployment(s) still out)."
        )


def check_project_crew(chief_pilot: User | None, surveyor: User | None, day: date) -> None:
    """The chief pilot must hold a valid DGCA certificate; both must be active accounts."""
    problems: list[str] = []
    if chief_pilot is not None:
        if not chief_pilot.is_active or chief_pilot.is_deleted:
            problems.append(f"{chief_pilot.full_name} is not an active user.")
        elif chief_pilot.licence is None:
            problems.append(f"{chief_pilot.full_name} has no DGCA pilot certificate.")
        elif not chief_pilot.licence.is_valid_on(day):
            problems.append(f"{chief_pilot.full_name}'s DGCA pilot certificate has expired.")
    if surveyor is not None and (not surveyor.is_active or surveyor.is_deleted):
        problems.append(f"{surveyor.full_name} is not an active user.")
    if problems:
        raise RuleViolation(problems)
