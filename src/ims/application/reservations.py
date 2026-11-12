"""Reservations: request, check, approve (book), reject, cancel, and hand over to a deployment.

Approval books every item in its own sequenced ledger, one step per item (ADR-0008).
If any item is refused part-way (another approval booked it a moment earlier), the items
already booked are released again and the request stays waiting, so a reservation is
never half-approved and an item is never booked twice for the same days.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ims.application.airworthiness import planned_between
from ims.application.bookings import append_booking, release_all
from ims.application.context import Actor, CommandContext
from ims.application.deployments import gcp_item_type
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.documents import compliance_problems
from ims.domain.assets.status import Custody, replay
from ims.domain.common.errors import ConflictError, DomainError, NotFound, RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    EntryId,
    KitId,
    LocationId,
    ProjectId,
    ReservationId,
    uuid7,
)
from ims.domain.identity.roles import Permission
from ims.domain.kits import completeness
from ims.domain.operations.deployment import Readiness
from ims.domain.operations.reservation import (
    AssetSchedule,
    BookingChange,
    GcpForecast,
    Reservation,
    ReservationStatus,
    active_bookings,
    booking_label,
    check_conflicts,
    check_reservation_transition,
    clashing,
    overlaps,
)
from ims.domain.stock.ledger import position
from ims.ports.clock import Clock
from ims.ports.repository import Storage


@dataclass(frozen=True, slots=True)
class ConflictReport:
    conflicts: Readiness
    asset_ids: list[AssetId]  # chosen items plus every member of the chosen kits
    gcp: GcpForecast | None


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    """One bar on the calendar."""

    asset_id: AssetId | None  # None for a reservation of GCP banners only
    project_id: ProjectId
    starts_on: date
    ends_on: date
    kind: str  # requested | approved | out
    reservation_id: ReservationId | None = None
    deployment_id: DeploymentId | None = None


# ---------------------------------------------------------------------- service


class ReservationService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ queries

    def list_reservations(self, actor: Actor) -> list[Reservation]:
        actor.require(Permission.PROJECT_VIEW)
        return self._s.reservations.list()

    def get(self, actor: Actor, reservation_id: ReservationId) -> Reservation:
        actor.require(Permission.PROJECT_VIEW)
        return self._require(reservation_id)

    def schedule(self, actor: Actor, starts_on: date, ends_on: date) -> list[ScheduleEntry]:
        """Every booking, request and deployment that touches these dates."""
        actor.require(Permission.PROJECT_VIEW)
        today = self._clock.today()
        entries: list[ScheduleEntry] = []
        for r in self._s.reservations.list():
            if not r.is_live or not overlaps(r.starts_on, r.ends_on, starts_on, ends_on):
                continue
            kind = "approved" if r.status is ReservationStatus.APPROVED else "requested"
            targets: list[AssetId | None] = list(r.asset_ids) or [None]  # GCP-only bookings
            for asset_id in targets:
                entries.append(ScheduleEntry(asset_id, r.project_id, r.starts_on, r.ends_on,
                                             kind, reservation_id=r.id))  # fmt: skip
        for d in self._s.deployments.list():
            if d.state.value not in {"out", "returned"}:
                continue
            project = self._s.projects.get(d.project_id)
            if d.returned_on is not None:
                end = d.returned_on
            else:
                end = max(today, project.ends_on if project and project.ends_on else today)
            if not overlaps(d.deployed_on, end, starts_on, ends_on):
                continue
            for asset_id in d.asset_ids:
                entries.append(ScheduleEntry(asset_id, d.project_id, d.deployed_on, end, "out",
                                             deployment_id=d.id))  # fmt: skip
        return entries

    def gcp_booked(self, actor: Actor) -> dict[LocationId, int]:
        """GCP banners promised to live reservations, per store."""
        actor.require(Permission.STOCK_VIEW)
        booked: dict[LocationId, int] = {}
        for r in self._s.reservations.list():
            if r.is_live and r.gcp_quantity and r.gcp_site_id is not None:
                booked[r.gcp_site_id] = booked.get(r.gcp_site_id, 0) + r.gcp_quantity
        return booked

    def check(
        self,
        actor: Actor,
        *,
        starts_on: date,
        ends_on: date,
        asset_ids: Sequence[AssetId] = (),
        kit_ids: Sequence[KitId] = (),
        gcp_quantity: int = 0,
        gcp_site_id: LocationId | None = None,
        reservation_id: ReservationId | None = None,
    ) -> ConflictReport:
        """Everything that clashes with these dates, before anything is written."""
        actor.require(Permission.ASSET_VIEW)
        chosen, incomplete = self._resolve(asset_ids, kit_ids)
        # A request not saved yet gets a throwaway ID so it never clashes with itself.
        this = reservation_id or ReservationId(uuid7())
        schedules = [self._schedule(a, starts_on, ends_on, this) for a in chosen]
        forecast = self._gcp_forecast(gcp_site_id, this) if gcp_quantity else None
        conflicts = check_conflicts(
            assets=schedules, starts_on=starts_on, ends_on=ends_on, today=self._clock.today(),
            gcp_quantity=gcp_quantity, gcp=forecast, incomplete_kits=incomplete,
        )  # fmt: skip
        if gcp_quantity and gcp_site_id is None:
            conflicts.blockers.append("Choose the store the GCP banners will come from.")
        return ConflictReport(conflicts, chosen, forecast)

    # ------------------------------------------------------------------ commands

    def request(
        self,
        ctx: CommandContext,
        *,
        project_id: ProjectId,
        starts_on: date,
        ends_on: date,
        asset_ids: Sequence[AssetId] = (),
        kit_ids: Sequence[KitId] = (),
        gcp_quantity: int = 0,
        gcp_site_id: LocationId | None = None,
        notes: str = "",
    ) -> ReservationId:
        """Asks for equipment. An administrator's own request is booked straight away."""
        actor = ctx.require_actor()
        actor.require(Permission.RESERVATION_CREATE)
        reservation_id = ReservationId(ctx.derive("reservation"))

        def execute() -> Outcome:
            stored = self._s.reservations.get(reservation_id)
            if stored is None:
                project = self._s.projects.get(project_id)
                if project is None or project.is_deleted:
                    raise NotFound("Project not found.")
                if not project.is_open:
                    raise RuleViolation(f"Project {project.code} is {project.status.value}.")
                report = self.check(
                    actor, starts_on=starts_on, ends_on=ends_on, asset_ids=asset_ids,
                    kit_ids=kit_ids, gcp_quantity=gcp_quantity, gcp_site_id=gcp_site_id,
                    reservation_id=reservation_id,
                )  # fmt: skip
                if not report.conflicts.ok:
                    raise RuleViolation(report.conflicts.blockers)
                stored = Reservation.build(
                    id=reservation_id, project_id=project_id, asset_ids=tuple(report.asset_ids),
                    kit_ids=tuple(dict.fromkeys(kit_ids)), starts_on=starts_on, ends_on=ends_on,
                    gcp_quantity=gcp_quantity, gcp_site_id=gcp_site_id if gcp_quantity else None,
                    notes=notes, requested_by=actor.user_id, requested_at=self._clock.now(),
                )  # fmt: skip
                add_once(self._s.reservations.add, stored)
            if stored.status is ReservationStatus.REQUESTED and actor.has(
                Permission.RESERVATION_APPROVE
            ):
                stored = self._book(ctx, actor, stored, "Booked by an administrator")
            return Outcome("reservation", str(reservation_id), None, stored.model_dump(mode="json"))

        self._run.run(ctx, "reservation.request", execute)
        return reservation_id

    def approve(
        self, ctx: CommandContext, reservation_id: ReservationId, expected_version: int,
        note: str = "",
    ) -> ReservationId:  # fmt: skip
        actor = ctx.require_actor()
        actor.require(Permission.RESERVATION_APPROVE)

        def execute() -> Outcome:
            stored = self._require(reservation_id)
            if (
                stored.status is ReservationStatus.APPROVED
                and stored.version == expected_version + 1
            ):
                return Outcome("reservation", str(reservation_id), None, {"status": "approved"})
            self._expect(stored, expected_version)
            check_reservation_transition(stored, ReservationStatus.APPROVED)
            report = self.check(
                actor, starts_on=stored.starts_on, ends_on=stored.ends_on,
                asset_ids=stored.asset_ids, gcp_quantity=stored.gcp_quantity,
                gcp_site_id=stored.gcp_site_id, reservation_id=stored.id,
            )  # fmt: skip
            if not report.conflicts.ok:
                raise RuleViolation(report.conflicts.blockers)
            after = self._book(ctx, actor, stored, note)
            return Outcome(
                "reservation", str(reservation_id), {"status": stored.status.value},
                {"status": after.status.value},
            )  # fmt: skip

        self._run.run(ctx, "reservation.approve", execute)
        return reservation_id

    def reject(
        self, ctx: CommandContext, reservation_id: ReservationId, expected_version: int, note: str
    ) -> ReservationId:
        actor = ctx.require_actor()
        actor.require(Permission.RESERVATION_APPROVE)
        return self._decide(ctx, actor, reservation_id, expected_version,
                            ReservationStatus.REJECTED, note, "reservation.reject")  # fmt: skip

    def cancel(
        self, ctx: CommandContext, reservation_id: ReservationId, expected_version: int,
        note: str = "",
    ) -> ReservationId:  # fmt: skip
        """The requester or an administrator withdraws it; any bookings are released."""
        actor = ctx.require_actor()
        stored = self._require(reservation_id)
        if stored.requested_by != actor.user_id:
            actor.require(Permission.RESERVATION_APPROVE)
        else:
            actor.require(Permission.RESERVATION_CREATE)
        return self._decide(ctx, actor, reservation_id, expected_version,
                            ReservationStatus.CANCELLED, note, "reservation.cancel")  # fmt: skip

    # ------------------------------------------------------------------ helpers

    def _book(
        self, ctx: CommandContext, actor: Actor, reservation: Reservation, note: str
    ) -> Reservation:
        """Books every item; on refusal releases what was booked and reports why."""
        try:
            for asset_id in reservation.asset_ids:
                append_booking(self._s, self._clock, ctx, actor, reservation, asset_id,
                               BookingChange.BOOKED, f"book:{asset_id}")  # fmt: skip
        except DomainError as exc:
            for asset_id in reversed(reservation.asset_ids):
                if any(e.id == EntryId(ctx.derive(f"book:{asset_id}"))
                       for e in self._s.bookings.for_asset(asset_id)):  # fmt: skip
                    append_booking(self._s, self._clock, ctx, actor, reservation, asset_id,
                                   BookingChange.RELEASED, f"unbook:{asset_id}")  # fmt: skip
            reason = " ".join(exc.problems) if isinstance(exc, RuleViolation) else str(exc)
            raise RuleViolation(f"Nothing was booked: {reason}") from exc
        current = self._require(reservation.id)
        if current.status is ReservationStatus.APPROVED:
            return current
        approved = current.next_version(
            status=ReservationStatus.APPROVED, decided_by=actor.user_id,
            decided_at=self._clock.now(), decision_note=note.strip(),
        )  # fmt: skip
        update_once(self._s.reservations.update, lambda: self._s.reservations.get(reservation.id),
                    approved)  # fmt: skip
        return approved

    def _decide(
        self, ctx: CommandContext, actor: Actor, reservation_id: ReservationId,
        expected_version: int, status: ReservationStatus, note: str, action: str,
    ) -> ReservationId:  # fmt: skip
        def execute() -> Outcome:
            stored = self._require(reservation_id)
            if stored.status is status and stored.version == expected_version + 1:
                return Outcome("reservation", str(reservation_id), None, {"status": status.value})
            self._expect(stored, expected_version)
            check_reservation_transition(stored, status)
            if stored.status is ReservationStatus.APPROVED:
                release_all(self._s, self._clock, ctx, actor, stored, "release")
            after = stored.next_version(
                status=status, decided_by=actor.user_id, decided_at=self._clock.now(),
                decision_note=note.strip(),
            )  # fmt: skip
            update_once(self._s.reservations.update,
                        lambda: self._s.reservations.get(reservation_id), after)  # fmt: skip
            return Outcome(
                "reservation", str(reservation_id), {"status": stored.status.value},
                {"status": status.value, "note": note},
            )  # fmt: skip

        self._run.run(ctx, action, execute)
        return reservation_id

    def _expect(self, stored: Reservation, expected_version: int) -> None:
        if stored.version != expected_version:
            raise ConflictError(
                "This reservation was changed by someone else. Reload and try again."
            )

    def _require(self, reservation_id: ReservationId) -> Reservation:
        reservation = self._s.reservations.get(reservation_id)
        if reservation is None:
            raise NotFound("Reservation not found.")
        return reservation

    def _resolve(
        self, asset_ids: Sequence[AssetId], kit_ids: Sequence[KitId]
    ) -> tuple[list[AssetId], list[str]]:
        chosen: dict[AssetId, None] = {}
        incomplete: list[str] = []
        for kit_id in dict.fromkeys(kit_ids):
            kit = self._s.kits.get(kit_id)
            if kit is None or kit.is_deleted:
                raise NotFound("Kit not found.")
            chosen.update(dict.fromkeys(kit.members))
            template = self._s.kit_templates.get(kit.template_id) if kit.template_id else None
            if template is not None:
                types = {}
                for member in kit.members:
                    asset = self._s.assets.get(member)
                    if asset is not None:
                        types[member] = asset.item_type_id
                if not completeness(template, types).complete:
                    incomplete.append(kit.code)
        chosen.update(dict.fromkeys(asset_ids))
        return list(chosen), incomplete

    def _schedule(
        self, asset_id: AssetId, starts_on: date, ends_on: date, this: ReservationId
    ) -> AssetSchedule:
        asset = self._s.assets.get(asset_id)
        if asset is None or asset.is_deleted:
            raise NotFound("Asset not found.")
        item_type = self._s.item_types.get(asset.item_type_id)
        if item_type is None:
            raise NotFound("Item type not found.")
        status = replay(self._s.status_events.for_asset(asset_id))

        def code(project_id: ProjectId) -> str:
            project = self._s.projects.get(project_id)
            return project.code if project else "another project"

        booked = [
            booking_label(code(b.project_id), b.starts_on, b.ends_on)
            for b in clashing(
                active_bookings(self._s.bookings.for_asset(asset_id)), starts_on, ends_on, this
            )
        ]
        requested = [
            booking_label(code(r.project_id), r.starts_on, r.ends_on)
            for r in self._s.reservations.list()
            if r.id != this
            and r.status is ReservationStatus.REQUESTED
            and asset_id in r.asset_ids
            and overlaps(r.starts_on, r.ends_on, starts_on, ends_on)
        ]
        out_with = ""
        if status.custody is Custody.DEPLOYED:
            for d in self._s.deployments.list():
                if d.is_open and asset_id in d.asset_ids:
                    project = self._s.projects.get(d.project_id)
                    due = project.ends_on if project and project.ends_on else None
                    out_with = code(d.project_id) + (f" (due back {due:%d %b})" if due else "")
                    break
        documents = [
            message
            for severity, message in compliance_problems(
                item_type, self._s.documents.for_asset(asset_id), ends_on
            )
            if severity == "danger"
        ]
        return AssetSchedule(
            asset_id=asset_id, tag=asset.asset_tag, type_name=item_type.name, status=status,
            booked=booked, requested=requested, out_with=out_with, documents=documents,
            maintenance=planned_between(self._s, asset_id, starts_on, ends_on),
        )  # fmt: skip

    def _gcp_forecast(self, site_id: LocationId | None, this: ReservationId) -> GcpForecast | None:
        gcp = gcp_item_type(self._s)
        if gcp is None or site_id is None:
            return None
        on_hand = position(self._s.stock.for_item_type(gcp.id)).on_hand_at(site_id)
        booked = sum(
            r.gcp_quantity
            for r in self._s.reservations.list()
            if r.id != this and r.is_live and r.gcp_site_id == site_id
        )
        level = next(
            (lv.level for lv in self._s.reorder_levels.list()
             if lv.item_type_id == gcp.id and lv.location_id == site_id),
            None,
        )  # fmt: skip
        return GcpForecast(on_hand=on_hand, already_booked=booked, reorder_level=level)
