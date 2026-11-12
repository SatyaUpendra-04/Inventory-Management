"""Flight and survey logs, and the usage they put on every item involved.

A log writes several usage entries (one ledger per asset) and then the log itself, which
marks it complete. A retry finds its earlier entries and carries on. If an entry is
refused part-way, the entries already written are reversed and nothing is logged.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from ims.application.airworthiness import ground_if_needed
from ims.application.context import Actor, CommandContext
from ims.application.deployments import fitted_parts
from ims.application.ledgers import append_usage
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.catalogue import ItemType
from ims.domain.common.errors import ConflictError, DomainError, NotFound, RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    EntryId,
    SortieId,
    SurveySessionId,
    UserId,
)
from ims.domain.identity.roles import Permission
from ims.domain.operations.deployment import CrewMember, Deployment
from ims.domain.operations.field_logs import (
    Sortie,
    SurveyMode,
    SurveySession,
    UsagePlan,
    check_session,
    check_sortie,
    session_usage,
    sortie_usage,
)
from ims.domain.usage.ledger import UsageSource
from ims.ports.clock import Clock
from ims.ports.repository import Storage


class FieldLogService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ queries

    def flights_with_media(self, actor: Actor, media_id: AssetId) -> list[Sortie]:
        """Flights whose data an SD card or disk carried."""
        actor.require(Permission.PROJECT_VIEW)
        return [s for s in self._s.sorties.list() if media_id in s.media_ids and not s.is_void]

    # ------------------------------------------------------------------ sorties

    def log_sortie(
        self,
        ctx: CommandContext,
        *,
        deployment_id: DeploymentId,
        drone_id: AssetId,
        pilot_id: UserId,
        flown_on: date,
        hours: Decimal,
        landings: int = 1,
        cycles: int = 1,
        battery_ids: Sequence[AssetId] = (),
        ppk_base_id: AssetId | None = None,
        media_ids: Sequence[AssetId] = (),
        notes: str = "",
    ) -> SortieId:
        actor = ctx.require_actor()
        actor.require(Permission.USAGE_RECORD)
        sortie_id = SortieId(ctx.derive("sortie"))

        def execute() -> Outcome:
            done = self._s.sorties.get(sortie_id)
            if done is not None:
                return Outcome("sortie", str(sortie_id), None, done.model_dump(mode="json"))
            deployment = self._deployment(deployment_id)
            draft = Sortie.build(
                id=sortie_id, project_id=deployment.project_id, deployment_id=deployment_id,
                drone_id=drone_id, pilot_id=pilot_id, flown_on=flown_on, hours=hours,
                landings=landings, cycles=cycles, battery_ids=tuple(battery_ids),
                ppk_base_id=ppk_base_id, media_ids=tuple(media_ids), notes=notes,
                recorded_at=self._clock.now(), recorded_by=actor.user_id,
            )  # fmt: skip
            involved = [drone_id, *battery_ids, *media_ids, *([ppk_base_id] if ppk_base_id else [])]
            types = self._types(involved)
            check_sortie(
                draft, deployment, today=self._clock.today(), pilot=self._crew(pilot_id),
                types=types,
            )  # fmt: skip
            fitted = fitted_parts(self._s, drone_id)
            types.update(self._types(fitted))
            plan = sortie_usage(draft, fitted, types)
            ids = self._write_usage(ctx, actor, plan, flown_on, deployment, "Flight")
            sortie = draft.model_copy(update={"usage_entries": tuple(ids)})
            add_once(self._s.sorties.add, sortie)
            self._ground_used(ctx, actor, ids)
            return Outcome("sortie", str(sortie_id), None, sortie.model_dump(mode="json"))

        self._run.run(ctx, "sortie.log", execute)
        return sortie_id

    def void_sortie(
        self, ctx: CommandContext, sortie_id: SortieId, expected_version: int, reason: str
    ) -> None:
        """Cancels a wrong flight log; every hour, landing and cycle it added is reversed."""
        self._void(
            ctx, "sortie", expected_version, reason,
            lambda: self._s.sorties.get(sortie_id), self._s.sorties.update,
        )  # fmt: skip

    # ------------------------------------------------------------------ survey sessions

    def log_session(
        self,
        ctx: CommandContext,
        *,
        deployment_id: DeploymentId,
        surveyor_id: UserId,
        surveyed_on: date,
        hours: Decimal,
        mode: SurveyMode = SurveyMode.RTK,
        base_id: AssetId | None = None,
        rover_ids: Sequence[AssetId] = (),
        controller_id: AssetId | None = None,
        battery_ids: Sequence[AssetId] = (),
        area_ha: Decimal | None = None,
        points: int = 0,
        fix_rate: Decimal | None = None,
        notes: str = "",
    ) -> SurveySessionId:
        actor = ctx.require_actor()
        actor.require(Permission.USAGE_RECORD)
        session_id = SurveySessionId(ctx.derive("survey-session"))

        def execute() -> Outcome:
            done = self._s.survey_sessions.get(session_id)
            if done is not None:
                return Outcome(
                    "survey_session", str(session_id), None, done.model_dump(mode="json")
                )
            deployment = self._deployment(deployment_id)
            draft = SurveySession.build(
                id=session_id, project_id=deployment.project_id, deployment_id=deployment_id,
                surveyor_id=surveyor_id, surveyed_on=surveyed_on, hours=hours, mode=mode,
                base_id=base_id, rover_ids=tuple(rover_ids), controller_id=controller_id,
                battery_ids=tuple(battery_ids), area_ha=area_ha, points=points,
                fix_rate=fix_rate, notes=notes, recorded_at=self._clock.now(),
                recorded_by=actor.user_id,
            )  # fmt: skip
            involved = [*draft.receivers, *battery_ids, *([controller_id] if controller_id else [])]
            types = self._types(involved)
            check_session(
                draft, deployment, today=self._clock.today(), surveyor=self._crew(surveyor_id),
                types=types,
            )  # fmt: skip
            plan = session_usage(draft, types)
            ids = self._write_usage(ctx, actor, plan, surveyed_on, deployment, "Survey session")
            session = draft.model_copy(update={"usage_entries": tuple(ids)})
            add_once(self._s.survey_sessions.add, session)
            self._ground_used(ctx, actor, ids)
            return Outcome("survey_session", str(session_id), None, session.model_dump(mode="json"))

        self._run.run(ctx, "survey_session.log", execute)
        return session_id

    def void_session(
        self, ctx: CommandContext, session_id: SurveySessionId, expected_version: int, reason: str
    ) -> None:
        self._void(
            ctx, "survey_session", expected_version, reason,
            lambda: self._s.survey_sessions.get(session_id), self._s.survey_sessions.update,
        )  # fmt: skip

    # ------------------------------------------------------------------ helpers

    def _write_usage(
        self, ctx: CommandContext, actor: Actor, plan: UsagePlan, day: date,
        deployment: Deployment, label: str,
    ) -> list[tuple[AssetId, EntryId]]:  # fmt: skip
        written: list[tuple[AssetId, EntryId]] = []
        try:
            for asset_id, meter, amount in plan:
                entry = append_usage(
                    self._s, self._clock, ctx, actor, asset_id, meter=meter, amount=amount,
                    occurred_on=day, source=UsageSource.SORTIE, project_id=deployment.project_id,
                    note=label, purpose=f"usage:{asset_id}:{meter.value}",
                )  # fmt: skip
                written.append((asset_id, entry.id))
        except DomainError:
            for asset_id, entry_id in reversed(written):
                self._reverse(ctx, actor, asset_id, entry_id, f"{label} not logged")
            raise
        return written

    def _ground_used(
        self, ctx: CommandContext, actor: Actor, written: list[tuple[AssetId, EntryId]]
    ) -> None:
        """An item this log took past a limit is grounded straight away (ARCHITECTURE §4.3)."""
        for asset_id in dict.fromkeys(a for a, _ in written):
            ground_if_needed(self._s, self._clock, ctx, actor, asset_id, f"ground:{asset_id}")

    def _reverse(
        self, ctx: CommandContext, actor: Actor, asset_id: AssetId, entry_id: EntryId, note: str
    ) -> None:
        target = next((e for e in self._s.usage.for_asset(asset_id) if e.id == entry_id), None)
        if target is None:
            return
        append_usage(
            self._s, self._clock, ctx, actor, asset_id, meter=target.meter, amount=-target.amount,
            occurred_on=target.occurred_on, source=UsageSource.REVERSAL,
            project_id=target.project_id, note=note, reverses=entry_id,
            purpose=f"reverse:{entry_id}",
        )  # fmt: skip

    def _void(
        self, ctx: CommandContext, entity: str, expected_version: int, reason: str,
        get: Callable[[], Any], update: Callable[[Any], None],
    ) -> None:  # fmt: skip
        actor = ctx.require_actor()
        actor.require(Permission.USAGE_CORRECT)
        if not reason.strip():
            raise RuleViolation("Give a reason for cancelling this log.")

        def execute() -> Outcome:
            log = get()
            if log is None:
                raise NotFound("Log not found.")
            if log.is_void:
                return Outcome(entity, str(log.id), None, {"voided": True})
            if log.version != expected_version:
                raise ConflictError("This log was changed by someone else. Reload and try again.")
            for asset_id, entry_id in log.usage_entries:
                self._reverse(ctx, actor, asset_id, entry_id, f"Cancelled: {reason}")
            after = log.next_version(voided_at=self._clock.now(), void_reason=reason.strip())
            update_once(update, get, after)
            return Outcome(
                entity, str(log.id), {"voided": False}, {"voided": True, "reason": reason}
            )

        self._run.run(ctx, f"{entity}.void", execute)

    def _deployment(self, deployment_id: DeploymentId) -> Deployment:
        deployment = self._s.deployments.get(deployment_id)
        if deployment is None:
            raise NotFound("Deployment not found.")
        return deployment

    def _types(self, asset_ids: Sequence[AssetId]) -> dict[AssetId, ItemType]:
        types: dict[AssetId, ItemType] = {}
        for asset_id in asset_ids:
            asset = self._s.assets.get(asset_id)
            if asset is None or asset.is_deleted:
                raise NotFound("Asset not found.")
            item_type = self._s.item_types.get(asset.item_type_id)
            if item_type is None:
                raise NotFound("Item type not found.")
            types[asset_id] = item_type
        return types

    def _crew(self, user_id: UserId) -> CrewMember:
        user = self._s.users.get(user_id)
        if user is None:
            raise NotFound("Person not found.")
        return CrewMember(
            user_id=user.id, name=user.full_name, role=user.role,
            active=user.is_active and not user.is_deleted, licence=user.licence,
        )  # fmt: skip
