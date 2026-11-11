"""Deployments: equipment and crew checked out to a project, and returned after it.

A deployment touches many records (one status event per asset, stock movements for GCP
banners, the project). Storage has no multi-record transactions (ADR-0005), so the
deployment record itself is written first in ``pending`` state and acts as the plan:
a retry carries on from where it stopped, and a failure part-way is undone step by step
(compensation) and the deployment ends ``cancelled`` with the reason (ADR-0007).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.catalogue import Category
from ims.domain.assets.status import USABLE, AssetStatus, Custody, Serviceability
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    KitId,
    LocationId,
    ProjectId,
    ReservationId,
    UserId,
)
from ims.domain.common.model import UtcDateTime, ValueModel, VersionedRecord
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence


class DeploymentState(StrEnum):
    PENDING = "pending"  # being checked out; finished by a retry or undone
    OUT = "out"  # with the crew
    RETURNED = "returned"
    CANCELLED = "cancelled"  # could not be completed; every step was undone


class ReturnCondition(StrEnum):
    OK = "ok"  # back in store, serviceable
    LIMITED = "limited"  # usable with a deferred defect
    GROUNDED = "grounded"  # damaged: grounded and sent to maintenance


class ReturnLine(ValueModel):
    asset_id: AssetId
    condition: ReturnCondition = ReturnCondition.OK
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _defects_need_a_note(self) -> ReturnLine:
        if self.condition is not ReturnCondition.OK and not self.note.strip():
            raise ValueError("describe the defect for equipment that is not returned OK")
        return self


class Deployment(VersionedRecord):
    id: DeploymentId
    project_id: ProjectId
    asset_ids: tuple[AssetId, ...]
    kit_ids: tuple[KitId, ...] = ()
    crew_ids: tuple[UserId, ...]
    gcp_quantity: int = Field(default=0, ge=0, le=10_000)
    gcp_site_id: LocationId | None = None  # store the banners were issued from
    deployed_on: date
    created_at: UtcDateTime
    created_by: UserId
    state: DeploymentState = DeploymentState.PENDING
    notes: str = Field(default="", max_length=2000)
    failure: str = Field(default="", max_length=2000)
    returned_on: date | None = None
    returned_by: UserId | None = None
    returns: tuple[ReturnLine, ...] = ()
    gcp_returned: int = Field(default=0, ge=0)
    gcp_consumed: int = Field(default=0, ge=0)
    return_site_id: LocationId | None = None
    reservation_id: ReservationId | None = None  # the booking this check-out fulfils

    @model_validator(mode="after")
    def _rules(self) -> Deployment:
        problems: list[str] = []
        if not self.asset_ids:
            problems.append("a deployment needs at least one item of equipment")
        if len(set(self.asset_ids)) != len(self.asset_ids):
            problems.append("an item can appear only once in a deployment")
        if not self.crew_ids or len(set(self.crew_ids)) != len(self.crew_ids):
            problems.append("a deployment needs a crew, each person once")
        if self.gcp_quantity and self.gcp_site_id is None:
            problems.append("choose the store the GCP banners are issued from")
        if self.state is DeploymentState.RETURNED:
            if {r.asset_id for r in self.returns} != set(self.asset_ids):
                problems.append("every item must be accounted for on return")
            if self.gcp_returned + self.gcp_consumed != self.gcp_quantity:
                problems.append("GCP banners returned and consumed must add up to those issued")
            if self.returned_on is None or self.returned_by is None:
                problems.append("a return needs a date and the person returning")
            elif self.returned_on < self.deployed_on:
                problems.append("equipment cannot come back before it went out")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_open(self) -> bool:
        return self.state in {DeploymentState.PENDING, DeploymentState.OUT}


# ---------------------------------------------------------------------- readiness check


@dataclass(frozen=True, slots=True)
class AssetReadiness:
    """What the readiness check needs to know about one item."""

    asset_id: AssetId
    tag: str
    type_name: str
    category: Category
    status: AssetStatus
    compliance: Sequence[tuple[str, str]] = ()  # (danger | warning, message)
    fitted_problems: Sequence[str] = ()  # e.g. a grounded motor on this airframe
    maintenance_overdue: Sequence[str] = ()  # filled from Sprint 7
    booked_elsewhere: Sequence[
        str
    ] = ()  # e.g. "PRJ-JSP-2612, 10-14 Dec": another project's booking


@dataclass(frozen=True, slots=True)
class CrewMember:
    user_id: UserId
    name: str
    role: Role
    active: bool
    licence: PilotLicence | None


@dataclass(frozen=True, slots=True)
class Readiness:
    """``blockers`` stop the deployment; ``warnings`` are shown but do not."""

    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers


_DEPLOYABLE_FROM = frozenset({Custody.IN_STORE, Custody.RESERVED})
_CUSTODY_WORDS = {
    Custody.DEPLOYED: "is already deployed",
    Custody.IN_MAINTENANCE: "is in maintenance",
    Custody.IN_TRANSIT: "is in transit",
    Custody.DISPOSED: "has been disposed of",
}


def check_readiness(
    *,
    assets: Sequence[AssetReadiness],
    crew: Sequence[CrewMember],
    day: date,
    incomplete_kits: Sequence[str] = (),
    gcp_requested: int = 0,
    gcp_available: int = 0,
) -> Readiness:
    """Every reason the deployment cannot go ahead, and things worth a second look."""
    result = Readiness()
    block, warn = result.blockers.append, result.warnings.append
    if not assets:
        block("Choose the equipment to take.")
    for a in assets:
        name = f"{a.tag} ({a.type_name})"
        if a.status.serviceability is Serviceability.UNSERVICEABLE:
            block(f"{name} is grounded.")
        elif a.status.serviceability is Serviceability.RETIRED:
            block(f"{name} is retired.")
        elif a.status.serviceability is Serviceability.LIMITED:
            warn(f"{name} has a recorded limitation.")
        if a.status.custody not in _DEPLOYABLE_FROM:
            block(f"{name} {_CUSTODY_WORDS[a.status.custody]}.")
        for severity, message in a.compliance:
            (block if severity == "danger" else warn)(f"{a.tag}: {message}")
        for problem in a.fitted_problems:
            block(f"{a.tag}: {problem}")
        for task in a.maintenance_overdue:
            block(f"{a.tag}: maintenance overdue ({task}).")
        for booking in a.booked_elsewhere:
            block(f"{a.tag} is booked for {booking}.")

    if not crew:
        block("Choose the crew.")
    for person in crew:
        if not person.active:
            block(f"{person.name} is not an active user.")
        licence = person.licence
        if person.role is Role.PILOT and (licence is None or not licence.is_valid_on(day)):
            block(f"{person.name}'s DGCA pilot certificate has expired.")
        elif (
            licence is not None
            and licence.is_valid_on(day)
            and licence.status_on(day) == "expiring"
        ):
            warn(
                f"{person.name}'s DGCA pilot certificate expires on {licence.expires_on:%d %b %Y}."
            )
    flying = any(a.category is Category.DRONE for a in assets)
    licensed = [
        p for p in crew if p.active and p.licence is not None and p.licence.is_valid_on(day)
    ]
    if flying and not licensed:
        block("A drone is going out, so the crew needs a pilot with a valid DGCA certificate.")

    for kit in incomplete_kits:
        warn(f"{kit} is incomplete.")
    if gcp_requested > gcp_available:
        block(f"Only {gcp_available} GCP banners are in that store; {gcp_requested} requested.")
    return result


def return_status_change(
    current: AssetStatus, line: ReturnLine
) -> tuple[Serviceability | None, Custody]:
    """The serviceability (if it changes) and custody an item gets on return.

    A return never improves serviceability: lifting a limitation or a grounding is a
    certified maintenance step, not something the crew does at the store counter.
    """
    s = current.serviceability
    match line.condition:
        case ReturnCondition.OK:
            return None, Custody.IN_STORE
        case ReturnCondition.LIMITED:
            return (Serviceability.LIMITED if s is Serviceability.SERVICEABLE else None), (
                Custody.IN_STORE
            )
        case ReturnCondition.GROUNDED:
            return (Serviceability.UNSERVICEABLE if s in USABLE else None), Custody.IN_MAINTENANCE


def check_return(deployment: Deployment, lines: Sequence[ReturnLine], gcp_returned: int,
                 gcp_consumed: int) -> None:  # fmt: skip
    problems: list[str] = []
    if deployment.state is not DeploymentState.OUT:
        problems.append(f"This deployment is {deployment.state.value}, not out.")
    returned = [line.asset_id for line in lines]
    if len(set(returned)) != len(returned) or set(returned) != set(deployment.asset_ids):
        problems.append("Account for every item that went out, once each.")
    if gcp_returned < 0 or gcp_consumed < 0:
        problems.append("GCP banner counts cannot be negative.")
    elif gcp_returned + gcp_consumed != deployment.gcp_quantity:
        problems.append(
            f"{deployment.gcp_quantity} GCP banners went out; returned ({gcp_returned}) and "
            f"used or left on site ({gcp_consumed}) must add up to that."
        )
    if problems:
        raise RuleViolation(problems)
