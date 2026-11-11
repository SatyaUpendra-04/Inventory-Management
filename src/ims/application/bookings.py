"""Booking ledger helpers shared by reservations and deployments (ADR-0008).

Each item has its own sequenced ledger of bookings. Writing an entry checks for an
overlapping booking first; the sequence rule then refuses a second writer that checked
at the same moment, so the same item can never be booked twice for the same days.
"""

from __future__ import annotations

from datetime import date

from ims.application.context import Actor, CommandContext
from ims.application.runner import add_once, update_once
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, DeploymentId, EntryId, ProjectId, ReservationId
from ims.domain.operations.reservation import (
    BookingChange,
    BookingEvent,
    Reservation,
    ReservationStatus,
    active_bookings,
    booking_label,
    clashing,
)
from ims.ports.clock import Clock
from ims.ports.repository import Storage


def booked_elsewhere(
    storage: Storage, asset_id: AssetId, day: date, project_id: ProjectId | None
) -> list[str]:
    """Other projects' bookings of this item that cover ``day`` (blocks a check-out).

    With no project chosen yet, every booking on that day counts.
    """
    labels: list[str] = []
    for booking in active_bookings(storage.bookings.for_asset(asset_id)):
        if booking.project_id != project_id and booking.starts_on <= day <= booking.ends_on:
            project = storage.projects.get(booking.project_id)
            code = project.code if project else "another project"
            labels.append(booking_label(code, booking.starts_on, booking.ends_on))
    return labels


def append_booking(
    storage: Storage,
    clock: Clock,
    ctx: CommandContext,
    actor: Actor,
    reservation: Reservation,
    asset_id: AssetId,
    change: BookingChange,
    purpose: str,
) -> None:
    """Books or releases one item for a reservation; idempotent within a command."""
    events = storage.bookings.for_asset(asset_id)
    event_id = EntryId(ctx.derive(purpose))
    if any(e.id == event_id for e in events):
        return
    held = active_bookings(events)
    if change is BookingChange.BOOKED:
        if any(b.reservation_id == reservation.id for b in held):
            return
        clash = clashing(held, reservation.starts_on, reservation.ends_on, reservation.id)
        if clash:
            first = clash[0]
            project = storage.projects.get(first.project_id)
            asset = storage.assets.get(asset_id)
            label = booking_label(
                project.code if project else "another project", first.starts_on, first.ends_on
            )
            tag = asset.asset_tag if asset else "An item"
            raise RuleViolation(f"{tag} is already booked for {label}.")
    elif not any(b.reservation_id == reservation.id for b in held):
        return  # nothing to release
    add_once(
        storage.bookings.append,
        BookingEvent(
            id=event_id, asset_id=asset_id, sequence=len(events) + 1, change=change,
            reservation_id=reservation.id, project_id=reservation.project_id,
            starts_on=reservation.starts_on, ends_on=reservation.ends_on,
            recorded_at=clock.now(), recorded_by=actor.user_id, command_id=ctx.command_id,
        ),
    )  # fmt: skip


def release_all(
    storage: Storage, clock: Clock, ctx: CommandContext, actor: Actor, reservation: Reservation,
    purpose: str,
) -> None:  # fmt: skip
    for asset_id in reversed(reservation.asset_ids):
        append_booking(
            storage, clock, ctx, actor, reservation, asset_id, BookingChange.RELEASED,
            f"{purpose}:{asset_id}",
        )  # fmt: skip


def fulfil(
    storage: Storage, clock: Clock, ctx: CommandContext, actor: Actor,
    reservation_id: ReservationId, deployment_id: DeploymentId,
) -> None:  # fmt: skip
    """The equipment went out: release the bookings and mark the reservation fulfilled."""
    reservation = storage.reservations.get(reservation_id)
    if reservation is None or reservation.status is ReservationStatus.FULFILLED:
        return
    release_all(storage, clock, ctx, actor, reservation, "fulfil")
    done = reservation.next_version(status=ReservationStatus.FULFILLED, deployment_id=deployment_id)
    update_once(storage.reservations.update, lambda: storage.reservations.get(reservation_id), done)
