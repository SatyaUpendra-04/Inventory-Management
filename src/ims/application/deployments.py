"""Deployments: checking equipment, crew and GCP banners out to a project, and back in.

Deploying writes many records with no transaction to hold them together (ADR-0005), so
it runs as a small saga (ADR-0007):

1. The readiness check runs; any blocker stops it before anything is written.
2. The deployment is saved as ``pending``. It is the plan the remaining steps follow.
3. Each item is marked deployed, the GCP banners are issued, the project becomes active.
4. The deployment is marked ``out``.

Every step has an ID derived from the command, so retrying a command that stopped
part-way carries on where it stopped. If a step is *refused* (someone else deployed the
same drone a moment earlier, say), the steps already taken are undone in reverse order
and the deployment ends ``cancelled`` with the reason. Nothing is left half-deployed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ims.application.bookings import booked_elsewhere, fulfil
from ims.application.context import Actor, CommandContext
from ims.application.ledgers import append_movement, append_status
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import ItemType, TrackingMode
from ims.domain.assets.configuration import current_placement
from ims.domain.assets.documents import compliance_problems
from ims.domain.assets.status import (
    USABLE,
    Custody,
    StatusChange,
    apply_change,
    replay,
)
from ims.domain.common.errors import ConflictError, DomainError, NotFound, RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    EntryId,
    ItemTypeId,
    KitId,
    LocationId,
    ProjectId,
    ReservationId,
    UserId,
)
from ims.domain.identity.roles import Permission
from ims.domain.kits import completeness
from ims.domain.operations.deployment import (
    AssetReadiness,
    CrewMember,
    Deployment,
    DeploymentState,
    Readiness,
    ReturnLine,
    check_readiness,
    check_return,
    return_status_change,
)
from ims.domain.operations.project import ProjectStatus
from ims.domain.operations.reservation import ReservationStatus
from ims.domain.stock.ledger import MovementKind, position
from ims.ports.clock import Clock
from ims.ports.repository import Storage


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    readiness: Readiness
    asset_ids: list[AssetId]  # chosen items plus every member of the chosen kits
    gcp_available: int


def fitted_parts(storage: Storage, parent_id: AssetId) -> list[AssetId]:
    """Components installed on an airframe right now."""
    seen: list[AssetId] = []
    for event in storage.configuration.for_parent(parent_id):
        if event.component_id in seen:
            continue
        placement = current_placement(storage.configuration.for_component(event.component_id))
        if placement is not None and placement.parent_id == parent_id:
            seen.append(event.component_id)
    return seen


def gcp_item_type(storage: Storage) -> ItemType | None:
    return next(
        (t for t in storage.item_types.list() if t.tracking is TrackingMode.CONSUMABLE), None
    )


class DeploymentService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ queries

    def list_deployments(self, actor: Actor) -> list[Deployment]:
        actor.require(Permission.PROJECT_VIEW)
        return self._s.deployments.list()

    def get(self, actor: Actor, deployment_id: DeploymentId) -> Deployment:
        actor.require(Permission.PROJECT_VIEW)
        return self._require(deployment_id)

    def readiness(
        self,
        actor: Actor,
        *,
        asset_ids: Sequence[AssetId] = (),
        kit_ids: Sequence[KitId] = (),
        crew_ids: Sequence[UserId] = (),
        gcp_quantity: int = 0,
        gcp_site_id: LocationId | None = None,
        day: date | None = None,
        project_id: ProjectId | None = None,
    ) -> ReadinessReport:
        """Everything that would stop this deployment, before anything is written."""
        actor.require(Permission.ASSET_VIEW)
        day = day or self._clock.today()
        chosen, incomplete = self._resolve(asset_ids, kit_ids)
        assets = [self._asset_readiness(a, day, project_id) for a in chosen]
        crew = [self._crew_member(u) for u in crew_ids]
        available = self._gcp_available(gcp_site_id)
        readiness = check_readiness(
            assets=assets, crew=crew, day=day, incomplete_kits=incomplete,
            gcp_requested=gcp_quantity, gcp_available=available,
        )  # fmt: skip
        if gcp_quantity and gcp_site_id is None:
            readiness.blockers.append("Choose the store the GCP banners come from.")
        if gcp_quantity < 0:
            readiness.blockers.append("The number of GCP banners cannot be negative.")
        return ReadinessReport(readiness, chosen, available)

    # ------------------------------------------------------------------ deploy

    def deploy(
        self,
        ctx: CommandContext,
        *,
        project_id: ProjectId,
        asset_ids: Sequence[AssetId] = (),
        kit_ids: Sequence[KitId] = (),
        crew_ids: Sequence[UserId],
        gcp_quantity: int = 0,
        gcp_site_id: LocationId | None = None,
        deployed_on: date | None = None,
        notes: str = "",
        reservation_id: ReservationId | None = None,
    ) -> DeploymentId:
        """Checks equipment out; with ``reservation_id`` it fulfils that booking."""
        actor = ctx.require_actor()
        actor.require(Permission.DEPLOYMENT_CREATE)
        if gcp_quantity:
            actor.require(Permission.STOCK_MOVE)
        deployment_id = DeploymentId(ctx.derive("deployment"))

        def execute() -> Outcome:
            plan = self._s.deployments.get(deployment_id)
            if plan is None:
                plan = self._plan(
                    ctx, actor, deployment_id, project_id, asset_ids, kit_ids, crew_ids,
                    gcp_quantity, gcp_site_id, deployed_on, notes, reservation_id,
                )  # fmt: skip
            if plan.state is DeploymentState.PENDING:
                try:
                    self._carry_out(ctx, actor, plan)
                except DomainError as exc:
                    # Undo, and still record the command (with its audit entry) so the
                    # attempt and its reason are on file; the caller then reports it.
                    self._undo(ctx, actor, plan, _message(exc))
                plan = self._require(deployment_id)
            return Outcome("deployment", str(deployment_id), None, plan.model_dump(mode="json"))

        self._run.run(ctx, "deployment.create", execute)
        result = self._require(deployment_id)
        if result.state is DeploymentState.CANCELLED:
            raise RuleViolation(
                f"The deployment could not be completed, so nothing was deployed: {result.failure}"
            )
        return deployment_id

    def _plan(
        self, ctx: CommandContext, actor: Actor, deployment_id: DeploymentId,
        project_id: ProjectId, asset_ids: Sequence[AssetId], kit_ids: Sequence[KitId],
        crew_ids: Sequence[UserId], gcp_quantity: int, gcp_site_id: LocationId | None,
        deployed_on: date | None, notes: str, reservation_id: ReservationId | None = None,
    ) -> Deployment:  # fmt: skip
        project = self._s.projects.get(project_id)
        if project is None or project.is_deleted:
            raise NotFound("Project not found.")
        if not project.is_open:
            raise RuleViolation(f"Project {project.code} is {project.status.value}.")
        day = deployed_on or self._clock.today()
        if day > self._clock.today():
            raise RuleViolation("Equipment cannot be deployed with a date in the future.")
        if reservation_id is not None:
            reservation = self._s.reservations.get(reservation_id)
            if reservation is None:
                raise NotFound("Reservation not found.")
            if reservation.project_id != project_id:
                raise RuleViolation("That reservation is for another project.")
            if reservation.status is not ReservationStatus.APPROVED:
                raise RuleViolation(f"That reservation is {reservation.status.value}.")
        report = self.readiness(
            actor, asset_ids=asset_ids, kit_ids=kit_ids, crew_ids=crew_ids,
            gcp_quantity=gcp_quantity, gcp_site_id=gcp_site_id, day=day, project_id=project_id,
        )  # fmt: skip
        if not report.readiness.ok:
            raise RuleViolation(report.readiness.blockers)
        plan = Deployment.build(
            id=deployment_id, project_id=project_id, asset_ids=tuple(report.asset_ids),
            kit_ids=tuple(dict.fromkeys(kit_ids)), crew_ids=tuple(crew_ids),
            gcp_quantity=gcp_quantity, gcp_site_id=gcp_site_id if gcp_quantity else None,
            deployed_on=day, created_at=self._clock.now(), created_by=actor.user_id,
            notes=notes, reservation_id=reservation_id,
        )  # fmt: skip
        add_once(self._s.deployments.add, plan)
        return plan

    def _carry_out(self, ctx: CommandContext, actor: Actor, plan: Deployment) -> None:
        project = self._s.projects.get(plan.project_id)
        code = project.code if project else "project"
        for asset_id in plan.asset_ids:
            append_status(
                self._s, self._clock, ctx, actor, asset_id,
                StatusChange(custody=Custody.DEPLOYED, project_id=plan.project_id,
                             reason=f"Deployed to {code}"),
                purpose=f"deploy:{asset_id}",
            )  # fmt: skip
        if plan.gcp_quantity and plan.gcp_site_id is not None:
            gcp = gcp_item_type(self._s)
            if gcp is None:
                raise NotFound("The GCP banner item type is missing.")
            append_movement(
                self._s, self._clock, ctx, actor, item_type_id=gcp.id,
                location_id=plan.gcp_site_id, kind=MovementKind.ISSUED,
                quantity=plan.gcp_quantity, project_id=plan.project_id,
                reason=f"Issued to {code}", purpose="gcp-issue",
            )  # fmt: skip
        if project is not None and project.status is ProjectStatus.PLANNED:
            active = project.next_version(status=ProjectStatus.ACTIVE)
            update_once(self._s.projects.update, lambda: self._s.projects.get(project.id), active)
        stored = self._require(plan.id)
        if stored.state is DeploymentState.PENDING:
            out = stored.next_version(state=DeploymentState.OUT)
            update_once(self._s.deployments.update, lambda: self._s.deployments.get(plan.id), out)
        if plan.reservation_id is not None:
            fulfil(self._s, self._clock, ctx, actor, plan.reservation_id, plan.id)

    def _undo(self, ctx: CommandContext, actor: Actor, plan: Deployment, reason: str) -> None:
        """Compensation: reverses every step this deployment took, newest first."""
        for asset_id in reversed(plan.asset_ids):
            deployed = EntryId(ctx.derive(f"deploy:{asset_id}"))
            if any(e.id == deployed for e in self._s.status_events.for_asset(asset_id)):
                append_status(
                    self._s, self._clock, ctx, actor, asset_id,
                    StatusChange(custody=Custody.IN_STORE, reason="Deployment undone"),
                    purpose=f"undo:{asset_id}",
                )  # fmt: skip
        gcp = gcp_item_type(self._s)
        issued = EntryId(ctx.derive("gcp-issue"))
        if (
            gcp is not None
            and plan.gcp_site_id is not None
            and any(m.id == issued for m in self._s.stock.for_item_type(gcp.id))
        ):
            append_movement(
                self._s, self._clock, ctx, actor, item_type_id=gcp.id,
                location_id=plan.gcp_site_id, kind=MovementKind.RETURNED,
                quantity=plan.gcp_quantity, project_id=plan.project_id,
                reason="Deployment undone", purpose="gcp-undo",
            )  # fmt: skip
        stored = self._require(plan.id)
        if stored.state is DeploymentState.PENDING:
            cancelled = stored.next_version(state=DeploymentState.CANCELLED, failure=reason[:2000])
            update_once(
                self._s.deployments.update, lambda: self._s.deployments.get(plan.id), cancelled
            )

    # ------------------------------------------------------------------ return

    def return_equipment(
        self,
        ctx: CommandContext,
        deployment_id: DeploymentId,
        expected_version: int,
        *,
        lines: Sequence[ReturnLine],
        gcp_returned: int = 0,
        gcp_consumed: int = 0,
        return_site_id: LocationId | None = None,
        returned_on: date | None = None,
    ) -> DeploymentId:
        """Brings everything back: each item's condition, and what became of the banners."""
        actor = ctx.require_actor()
        actor.require(Permission.DEPLOYMENT_RETURN)
        if gcp_returned or gcp_consumed:
            actor.require(Permission.STOCK_MOVE)

        def execute() -> Outcome:
            stored = self._require(deployment_id)
            if stored.state is DeploymentState.RETURNED and stored.version == expected_version + 1:
                return Outcome("deployment", str(deployment_id), None, {"state": "returned"})
            if stored.version != expected_version:
                raise ConflictError(
                    "This deployment was changed by someone else. Reload and try again."
                )
            check_return(stored, lines, gcp_returned, gcp_consumed)
            day = returned_on or self._clock.today()
            problems: list[str] = []
            if day > self._clock.today():
                problems.append("The return date cannot be in the future.")
            if day < stored.deployed_on:
                problems.append("Equipment cannot come back before it went out.")
            if gcp_returned and return_site_id is None:
                problems.append("Choose the store the GCP banners are returned to.")
            if problems:
                raise RuleViolation(problems)
            changes = self._return_changes(ctx, stored, lines)
            for asset_id, change in changes:
                append_status(
                    self._s, self._clock, ctx, actor, asset_id, change,
                    purpose=f"return:{asset_id}",
                )  # fmt: skip
            self._settle_gcp(ctx, actor, stored, gcp_returned, gcp_consumed, return_site_id)
            after = stored.next_version(
                state=DeploymentState.RETURNED, returned_on=day, returned_by=actor.user_id,
                returns=tuple(lines), gcp_returned=gcp_returned, gcp_consumed=gcp_consumed,
                return_site_id=return_site_id if gcp_returned else None,
            )  # fmt: skip
            update_once(
                self._s.deployments.update, lambda: self._s.deployments.get(deployment_id), after
            )
            return Outcome(
                "deployment", str(deployment_id), {"state": stored.state.value},
                after.model_dump(mode="json"),
            )  # fmt: skip

        self._run.run(ctx, "deployment.return", execute)
        return deployment_id

    def _return_changes(
        self, ctx: CommandContext, deployment: Deployment, lines: Sequence[ReturnLine]
    ) -> list[tuple[AssetId, StatusChange]]:
        """Checks every item's change before any is written, skipping ones a retry did."""
        changes: list[tuple[AssetId, StatusChange]] = []
        problems: list[str] = []
        for line in lines:
            events = self._s.status_events.for_asset(line.asset_id)
            if any(e.id == EntryId(ctx.derive(f"return:{line.asset_id}")) for e in events):
                continue
            current = replay(events)
            serviceability, custody = return_status_change(current, line)
            change = StatusChange(
                serviceability=serviceability, custody=custody,
                reason=line.note or "Returned", project_id=deployment.project_id,
            )  # fmt: skip
            try:
                apply_change(current, change)
            except DomainError as exc:
                asset = self._s.assets.get(line.asset_id)
                problems.append(f"{asset.asset_tag if asset else line.asset_id}: {_message(exc)}")
            changes.append((line.asset_id, change))
        if problems:
            raise RuleViolation(problems)
        return changes

    def _settle_gcp(
        self, ctx: CommandContext, actor: Actor, deployment: Deployment, returned: int,
        consumed: int, return_site_id: LocationId | None,
    ) -> None:  # fmt: skip
        if not deployment.gcp_quantity:
            return
        gcp = gcp_item_type(self._s)
        if gcp is None or deployment.gcp_site_id is None:
            raise NotFound("The GCP banner item type is missing.")
        project = self._s.projects.get(deployment.project_id)
        code = project.code if project else "the project"
        if returned and return_site_id is not None:
            append_movement(
                self._s, self._clock, ctx, actor, item_type_id=gcp.id,
                location_id=return_site_id, kind=MovementKind.RETURNED, quantity=returned,
                project_id=deployment.project_id, reason=f"Returned from {code}",
                purpose="gcp-return",
            )  # fmt: skip
        if consumed:
            append_movement(
                self._s, self._clock, ctx, actor, item_type_id=gcp.id,
                location_id=deployment.gcp_site_id, kind=MovementKind.CONSUMED,
                quantity=consumed, project_id=deployment.project_id,
                reason=f"Used or left on site at {code}", purpose="gcp-consumed",
            )  # fmt: skip

    # ------------------------------------------------------------------ helpers

    def _require(self, deployment_id: DeploymentId) -> Deployment:
        deployment = self._s.deployments.get(deployment_id)
        if deployment is None:
            raise NotFound("Deployment not found.")
        return deployment

    def _resolve(
        self, asset_ids: Sequence[AssetId], kit_ids: Sequence[KitId]
    ) -> tuple[list[AssetId], list[str]]:
        chosen: dict[AssetId, None] = {}
        incomplete: list[str] = []
        for kit_id in dict.fromkeys(kit_ids):
            kit = self._s.kits.get(kit_id)
            if kit is None or kit.is_deleted:
                raise NotFound("Kit not found.")
            for member in kit.members:
                chosen[member] = None
            if kit.template_id is not None:
                template = self._s.kit_templates.get(kit.template_id)
                member_types = {m: self._asset(m).item_type_id for m in kit.members}
                if template is not None and not completeness(template, member_types).complete:
                    incomplete.append(kit.code)
        for asset_id in asset_ids:
            chosen[asset_id] = None
        return list(chosen), incomplete

    def _asset(self, asset_id: AssetId) -> Asset:
        asset = self._s.assets.get(asset_id)
        if asset is None or asset.is_deleted:
            raise NotFound("Asset not found.")
        return asset

    def _type(self, item_type_id: ItemTypeId) -> ItemType:
        item_type = self._s.item_types.get(item_type_id)
        if item_type is None:
            raise NotFound("Item type not found.")
        return item_type

    def _asset_readiness(
        self, asset_id: AssetId, day: date, project_id: ProjectId | None = None
    ) -> AssetReadiness:
        asset = self._asset(asset_id)
        item_type = self._type(asset.item_type_id)
        fitted_problems: list[str] = []
        for part_id in fitted_parts(self._s, asset_id):
            part = self._asset(part_id)
            if replay(self._s.status_events.for_asset(part_id)).serviceability not in USABLE:
                part_type = self._type(part.item_type_id)
                fitted_problems.append(
                    f"fitted {part_type.name.lower()} {part.asset_tag} is grounded"
                )
        return AssetReadiness(
            asset_id=asset_id,
            tag=asset.asset_tag,
            type_name=item_type.name,
            category=item_type.category,
            status=replay(self._s.status_events.for_asset(asset_id)),
            compliance=compliance_problems(item_type, self._s.documents.for_asset(asset_id), day),
            fitted_problems=fitted_problems,
            booked_elsewhere=booked_elsewhere(self._s, asset_id, day, project_id),
        )

    def _crew_member(self, user_id: UserId) -> CrewMember:
        user = self._s.users.get(user_id)
        if user is None:
            raise NotFound("Person not found.")
        return CrewMember(
            user_id=user.id, name=user.full_name, role=user.role,
            active=user.is_active and not user.is_deleted, licence=user.licence,
        )  # fmt: skip

    def _gcp_available(self, site_id: LocationId | None) -> int:
        gcp = gcp_item_type(self._s)
        if gcp is None or site_id is None:
            return 0
        return position(self._s.stock.for_item_type(gcp.id)).on_hand_at(site_id)


def _message(exc: BaseException) -> str:
    if isinstance(exc, RuleViolation):
        return " ".join(exc.problems)
    return str(exc)
