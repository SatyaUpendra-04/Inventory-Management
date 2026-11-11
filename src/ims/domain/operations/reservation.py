"""Reservations: equipment, kits and GCP banners booked for a project's dates.

A request is checked against everything that could get in its way (other bookings,
equipment already out, grounded items, documents expiring before the job ends, GCP
stock). An administrator approves or rejects it. Approval *books* each item: an entry
in the item's own sequenced booking ledger. Two approvals that overlap on the same
item cannot both succeed, even at the same moment, because the ledger accepts only one
entry per sequence number (ADR-0005, ADR-0008). An approved reservation is turned into
a deployment when the crew leaves, which releases the bookings.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.status import AssetStatus, Custody, Serviceability
from ims.domain.common.errors import InvalidTransition
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    DeploymentId,
    EntryId,
    KitId,
    LocationId,
    ProjectId,
    ReservationId,
    UserId,
)
from ims.domain.common.model import UtcDateTime, ValueModel, VersionedRecord
from ims.domain.operations.deployment import Readiness

MAX_BOOKING_DAYS = 180


class ReservationStatus(StrEnum):
    REQUESTED = "requested"  # waiting for an administrator
    APPROVED = "approved"  # every item is booked
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FULFILLED = "fulfilled"  # turned into a deployment


RESERVATION_TRANSITIONS = {
    ReservationStatus.REQUESTED: frozenset(
        {ReservationStatus.APPROVED, ReservationStatus.REJECTED, ReservationStatus.CANCELLED}
    ),
    ReservationStatus.APPROVED: frozenset(
        {ReservationStatus.CANCELLED, ReservationStatus.FULFILLED}
    ),
    ReservationStatus.REJECTED: frozenset(),
    ReservationStatus.CANCELLED: frozenset(),
    ReservationStatus.FULFILLED: frozenset(),
}


class Reservation(VersionedRecord):
    id: ReservationId
    project_id: ProjectId
    asset_ids: tuple[AssetId, ...] = ()
    kit_ids: tuple[KitId, ...] = ()
    starts_on: date
    ends_on: date
    gcp_quantity: int = Field(default=0, ge=0, le=10_000)
    gcp_site_id: LocationId | None = None
    notes: str = Field(default="", max_length=2000)
    requested_by: UserId
    requested_at: UtcDateTime
    status: ReservationStatus = ReservationStatus.REQUESTED
    decided_by: UserId | None = None
    decided_at: UtcDateTime | None = None
    decision_note: str = Field(default="", max_length=1000)
    deployment_id: DeploymentId | None = None

    @model_validator(mode="after")
    def _rules(self) -> Reservation:
        problems: list[str] = []
        if self.ends_on < self.starts_on:
            problems.append("the booking cannot end before it starts")
        elif (self.ends_on - self.starts_on).days >= MAX_BOOKING_DAYS:
            problems.append(f"a booking can cover at most {MAX_BOOKING_DAYS} days")
        if not self.asset_ids and not self.gcp_quantity:
            problems.append("choose equipment or GCP banners to reserve")
        if len(set(self.asset_ids)) != len(self.asset_ids):
            problems.append("an item can appear only once in a reservation")
        if self.gcp_quantity and self.gcp_site_id is None:
            problems.append("choose the store the GCP banners will come from")
        if self.status is ReservationStatus.REJECTED and not self.decision_note.strip():
            problems.append("give the reason for rejecting the request")
        if self.status is ReservationStatus.FULFILLED and self.deployment_id is None:
            problems.append("a fulfilled reservation names its deployment")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_live(self) -> bool:
        """Still holding (or asking for) equipment."""
        return self.status in {ReservationStatus.REQUESTED, ReservationStatus.APPROVED}

    def covers(self, day: date) -> bool:
        return self.starts_on <= day <= self.ends_on


def check_reservation_transition(reservation: Reservation, new: ReservationStatus) -> None:
    if new not in RESERVATION_TRANSITIONS[reservation.status]:
        raise InvalidTransition(
            f"A {reservation.status.value} reservation cannot become {new.value}."
        )


def overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


# ---------------------------------------------------------------------- booking ledger


class BookingChange(StrEnum):
    BOOKED = "booked"
    RELEASED = "released"


class BookingEvent(ValueModel):
    """One entry in an item's booking ledger (sequenced per asset)."""

    id: EntryId
    asset_id: AssetId
    sequence: int = Field(ge=1)
    change: BookingChange
    reservation_id: ReservationId
    project_id: ProjectId
    starts_on: date
    ends_on: date
    recorded_at: UtcDateTime
    recorded_by: UserId
    command_id: CommandId


@dataclass(frozen=True, slots=True)
class Booking:
    reservation_id: ReservationId
    project_id: ProjectId
    starts_on: date
    ends_on: date


def active_bookings(events: Iterable[BookingEvent]) -> list[Booking]:
    """Bookings in force, replayed from the ledger (and checked for a broken chain)."""
    held: dict[ReservationId, Booking] = {}
    for expected, event in enumerate(events, start=1):
        if event.sequence != expected:
            raise InvalidTransition(f"Booking history is broken at event {event.id}.")
        if event.change is BookingChange.BOOKED:
            if event.reservation_id in held:
                raise InvalidTransition(f"Booking history books twice at event {event.id}.")
            held[event.reservation_id] = Booking(
                event.reservation_id, event.project_id, event.starts_on, event.ends_on
            )
        else:
            if held.pop(event.reservation_id, None) is None:
                raise InvalidTransition(f"Booking history releases wrongly at event {event.id}.")
    return sorted(held.values(), key=lambda b: (b.starts_on, str(b.reservation_id)))


def clashing(
    bookings: Iterable[Booking], starts_on: date, ends_on: date, reservation_id: ReservationId
) -> list[Booking]:
    """Other reservations' bookings that overlap these dates."""
    return [
        b
        for b in bookings
        if b.reservation_id != reservation_id
        and overlaps(b.starts_on, b.ends_on, starts_on, ends_on)
    ]


# ---------------------------------------------------------------------- conflict check


@dataclass(frozen=True, slots=True)
class AssetSchedule:
    """What the conflict check needs to know about one item for the requested dates."""

    asset_id: AssetId
    tag: str
    type_name: str
    status: AssetStatus
    booked: Sequence[str] = ()  # other approved bookings that overlap: "PRJ-X, 10-14 Dec"
    requested: Sequence[str] = ()  # other pending requests that overlap
    out_with: str = ""  # "PRJ-X (due back 20 Nov)" when deployed elsewhere
    documents: Sequence[str] = ()  # "insurance expires 3 Dec", missing documents
    maintenance: Sequence[str] = ()  # planned maintenance in the window (Sprint 7)


@dataclass(frozen=True, slots=True)
class GcpForecast:
    on_hand: int
    already_booked: int  # by other live reservations from the same store
    reorder_level: int | None

    def left_after(self, quantity: int) -> int:
        return self.on_hand - self.already_booked - quantity


def check_conflicts(
    *,
    assets: Sequence[AssetSchedule],
    starts_on: date,
    ends_on: date,
    today: date,
    gcp_quantity: int = 0,
    gcp: GcpForecast | None = None,
    incomplete_kits: Sequence[str] = (),
) -> Readiness:
    """Blockers stop a booking; warnings are things to sort out before the job."""
    result = Readiness()
    block, warn = result.blockers.append, result.warnings.append
    if ends_on < starts_on:
        block("The booking cannot end before it starts.")
    if starts_on < today:
        block("The booking cannot start in the past.")
    if not assets and not gcp_quantity:
        block("Choose equipment or GCP banners to reserve.")
    for a in assets:
        name = f"{a.tag} ({a.type_name})"
        for other in a.booked:
            block(f"{name} is already booked for {other}.")
        s = a.status
        if s.serviceability is Serviceability.RETIRED or s.custody is Custody.DISPOSED:
            block(f"{name} is retired.")
        elif s.serviceability is Serviceability.UNSERVICEABLE:
            warn(f"{name} is grounded; it must be repaired before the job.")
        elif s.serviceability is Serviceability.LIMITED:
            warn(f"{name} has a recorded limitation.")
        if a.out_with:
            warn(f"{name} is out with {a.out_with}.")
        if s.custody is Custody.IN_MAINTENANCE:
            warn(f"{name} is in maintenance.")
        for other in a.requested:
            warn(f"{name} is also requested for {other}.")
        for problem in a.documents:
            warn(f"{a.tag}: {problem}.")
        for task in a.maintenance:
            warn(f"{a.tag}: maintenance planned ({task}).")
    for kit in incomplete_kits:
        warn(f"{kit} is incomplete.")
    if gcp_quantity and gcp is not None:
        left = gcp.left_after(gcp_quantity)
        if left < 0:
            warn(
                f"GCP banners: {gcp.on_hand} in that store, {gcp.already_booked} already booked; "
                f"this booking is {-left} short. Order more before the job."
            )
        elif gcp.reorder_level is not None and left <= gcp.reorder_level:
            warn(
                f"GCP banners: bookings would leave {left} in that store, at or below its "
                f"reorder level of {gcp.reorder_level}."
            )
    return result


def booking_label(code: str, starts_on: date, ends_on: date) -> str:
    """e.g. ``PRJ-JSP-2612, 10-14 Dec``, with an en dash between the dates."""
    dash = f" {chr(0x2013)} "
    if starts_on == ends_on:
        return f"{code}, {starts_on:%d %b}"
    if starts_on.month == ends_on.month and starts_on.year == ends_on.year:
        return f"{code}, {starts_on:%d}{dash}{ends_on:%d %b}"
    return f"{code}, {starts_on:%d %b}{dash}{ends_on:%d %b}"


__all__ = [
    "MAX_BOOKING_DAYS",
    "AssetSchedule",
    "Booking",
    "BookingChange",
    "BookingEvent",
    "GcpForecast",
    "Reservation",
    "ReservationStatus",
    "active_bookings",
    "booking_label",
    "check_conflicts",
    "check_reservation_transition",
    "clashing",
    "overlaps",
]
