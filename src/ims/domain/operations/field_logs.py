"""Field logs: sorties (individual flights) and survey sessions.

Logging one turns into usage-ledger entries for every item involved: the airframe's
hours, landings and cycles; a cycle on each battery; flight hours on every part fitted
to the airframe at the time; hours on the PPK base and on the GNSS receivers.
A log is never edited. A mistake is voided, which reverses its usage entries exactly.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.catalogue import Category, ItemType, Meter
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    EntryId,
    ProjectId,
    SortieId,
    SurveySessionId,
    UserId,
)
from ims.domain.common.model import UtcDateTime, VersionedRecord
from ims.domain.operations.deployment import CrewMember, Deployment, DeploymentState

MAX_FLIGHT_HOURS = Decimal(8)
MAX_SESSION_HOURS = Decimal(24)

UsagePlan = list[tuple[AssetId, Meter, Decimal]]


class _FieldLog(VersionedRecord):
    project_id: ProjectId
    deployment_id: DeploymentId
    hours: Decimal = Field(gt=0, decimal_places=2)
    battery_ids: tuple[AssetId, ...] = ()
    notes: str = Field(default="", max_length=2000)
    recorded_at: UtcDateTime
    recorded_by: UserId
    # (asset, usage entry) pairs this log wrote, so voiding can reverse them exactly
    usage_entries: tuple[tuple[AssetId, EntryId], ...] = ()
    voided_at: UtcDateTime | None = None
    void_reason: str = Field(default="", max_length=1000)

    @property
    def is_void(self) -> bool:
        return self.voided_at is not None


class Sortie(_FieldLog):
    """One flight."""

    id: SortieId
    drone_id: AssetId
    pilot_id: UserId
    flown_on: date
    landings: int = Field(default=1, ge=0, le=100)
    cycles: int = Field(default=1, ge=0, le=100)
    ppk_base_id: AssetId | None = None
    media_ids: tuple[AssetId, ...] = ()  # SD cards / disks that carried this flight's data

    @model_validator(mode="after")
    def _rules(self) -> Sortie:
        problems: list[str] = []
        if self.hours > MAX_FLIGHT_HOURS:
            problems.append(f"a single flight cannot be longer than {MAX_FLIGHT_HOURS} hours")
        if len(set(self.battery_ids)) != len(self.battery_ids):
            problems.append("each battery once per flight")
        if self.drone_id in {*self.battery_ids, *self.media_ids}:
            problems.append("the drone cannot also be a battery or data card")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class SurveyMode(StrEnum):
    RTK = "rtk"
    PPK = "ppk"
    STATIC = "static"


class SurveySession(_FieldLog):
    """One GNSS survey session: which receiver was the base and which the rovers."""

    id: SurveySessionId
    surveyor_id: UserId
    surveyed_on: date
    mode: SurveyMode = SurveyMode.RTK
    base_id: AssetId | None = None
    rover_ids: tuple[AssetId, ...] = ()
    controller_id: AssetId | None = None
    area_ha: Decimal | None = Field(default=None, ge=0, le=100_000, decimal_places=2)
    points: int = Field(default=0, ge=0, le=1_000_000)
    fix_rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=1)

    @model_validator(mode="after")
    def _rules(self) -> SurveySession:
        problems: list[str] = []
        if self.hours > MAX_SESSION_HOURS:
            problems.append(f"a survey session cannot be longer than {MAX_SESSION_HOURS} hours")
        if self.base_id is None and not self.rover_ids:
            problems.append("choose the base or at least one rover")
        if len(set(self.rover_ids)) != len(self.rover_ids):
            problems.append("each rover once")
        if self.base_id is not None and self.base_id in self.rover_ids:
            problems.append("one receiver cannot be the base and a rover in the same session")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def receivers(self) -> tuple[AssetId, ...]:
        return ((self.base_id,) if self.base_id else ()) + self.rover_ids


# ---------------------------------------------------------------------- checks


def _check_common(
    deployment: Deployment, day: date, today: date, asset_ids: Iterable[AssetId]
) -> list[str]:
    problems: list[str] = []
    if deployment.state not in {DeploymentState.OUT, DeploymentState.RETURNED}:
        problems.append("Logs can only be added to a deployment that went out.")
    if day > today:
        problems.append("The date cannot be in the future.")
    if day < deployment.deployed_on:
        problems.append("The date is before the equipment went out.")
    if deployment.returned_on is not None and day > deployment.returned_on:
        problems.append("The date is after the equipment came back.")
    missing = [a for a in asset_ids if a not in deployment.asset_ids]
    if missing:
        problems.append("Only equipment from this deployment can be logged.")
    return problems


def check_sortie(
    sortie: Sortie,
    deployment: Deployment,
    *,
    today: date,
    pilot: CrewMember,
    types: dict[AssetId, ItemType],
) -> None:
    involved = [sortie.drone_id, *sortie.battery_ids, *sortie.media_ids]
    if sortie.ppk_base_id:
        involved.append(sortie.ppk_base_id)
    problems = _check_common(deployment, sortie.flown_on, today, involved)
    if pilot.user_id not in deployment.crew_ids:
        problems.append(f"{pilot.name} is not in this deployment's crew.")
    if pilot.licence is None or not pilot.licence.is_valid_on(sortie.flown_on):
        problems.append(f"{pilot.name} had no valid DGCA pilot certificate on that day.")
    if types[sortie.drone_id].category is not Category.DRONE:
        problems.append("Choose a drone airframe.")
    if any(types[b].code != "DRONE_BATTERY" for b in sortie.battery_ids):
        problems.append("Only drone flight batteries can power a flight.")
    if any(types[m].category is not Category.DATA_MEDIA for m in sortie.media_ids):
        problems.append("Only SD cards and hard disks can carry flight data.")
    if sortie.ppk_base_id and Meter.HOURS not in types[sortie.ppk_base_id].meters:
        problems.append("Choose a GNSS receiver as the PPK base.")
    if problems:
        raise RuleViolation(problems)


def check_session(
    session: SurveySession,
    deployment: Deployment,
    *,
    today: date,
    surveyor: CrewMember,
    types: dict[AssetId, ItemType],
) -> None:
    involved = [*session.receivers, *session.battery_ids]
    if session.controller_id:
        involved.append(session.controller_id)
    problems = _check_common(deployment, session.surveyed_on, today, involved)
    if surveyor.user_id not in deployment.crew_ids:
        problems.append(f"{surveyor.name} is not in this deployment's crew.")
    if any(types[r].category is not Category.GNSS or Meter.HOURS not in types[r].meters
           for r in session.receivers):  # fmt: skip
        problems.append("Base and rovers must be GNSS receivers.")
    if session.controller_id and types[session.controller_id].code != "CONTROLLER":
        problems.append("Choose a survey controller.")
    if any(types[b].category is not Category.BATTERY for b in session.battery_ids):
        problems.append("Only batteries can be logged as batteries.")
    if problems:
        raise RuleViolation(problems)


# ---------------------------------------------------------------------- usage


def sortie_usage(
    sortie: Sortie, fitted: Sequence[AssetId], types: dict[AssetId, ItemType]
) -> UsagePlan:
    """Usage entries a flight produces. ``fitted`` are parts installed on the airframe."""
    plan: UsagePlan = []

    def add(asset: AssetId, meter: Meter, amount: Decimal) -> None:
        if amount > 0 and meter in types[asset].meters:
            plan.append((asset, meter, amount))

    add(sortie.drone_id, Meter.HOURS, sortie.hours)
    add(sortie.drone_id, Meter.LANDINGS, Decimal(sortie.landings))
    add(sortie.drone_id, Meter.CYCLES, Decimal(sortie.cycles))
    for battery in sortie.battery_ids:
        add(battery, Meter.CYCLES, Decimal(1))
    for part in fitted:
        add(part, Meter.HOURS, sortie.hours)
        add(part, Meter.LANDINGS, Decimal(sortie.landings))
    if sortie.ppk_base_id:
        add(sortie.ppk_base_id, Meter.HOURS, sortie.hours)
    return plan


def session_usage(session: SurveySession, types: dict[AssetId, ItemType]) -> UsagePlan:
    plan: UsagePlan = []
    for receiver in session.receivers:
        if Meter.HOURS in types[receiver].meters:
            plan.append((receiver, Meter.HOURS, session.hours))
    for battery in session.battery_ids:
        if Meter.CYCLES in types[battery].meters:
            plan.append((battery, Meter.CYCLES, Decimal(1)))
    return plan
