"""Recording and correcting usage (hours, cycles, landings)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once
from ims.domain.assets.catalogue import Meter
from ims.domain.common.errors import NotFound
from ims.domain.common.ids import AssetId, EntryId, ProjectId
from ims.domain.identity.roles import Permission
from ims.domain.usage.ledger import UsageEntry, UsageSource, check_new_entry, totals
from ims.ports.clock import Clock
from ims.ports.repository import Storage


class UsageService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    def totals(self, actor: Actor, asset_id: AssetId) -> dict[Meter, Decimal]:
        actor.require(Permission.ASSET_VIEW)
        return totals(self._s.usage.for_asset(asset_id))

    def entries(self, actor: Actor, asset_id: AssetId) -> list[UsageEntry]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.usage.for_asset(asset_id)

    def record(
        self,
        ctx: CommandContext,
        *,
        asset_id: AssetId,
        meter: Meter,
        amount: Decimal,
        occurred_on: date,
        source: UsageSource,
        project_id: ProjectId | None = None,
        note: str = "",
    ) -> EntryId:
        """Records usage from the field, or an admin adjustment (which needs a reason)."""
        actor = ctx.require_actor()
        if source is UsageSource.ADJUSTMENT:
            actor.require(Permission.USAGE_CORRECT)
        else:
            actor.require(Permission.USAGE_RECORD)
        return self._append(
            ctx, actor, "usage.record", asset_id, meter=meter, amount=amount,
            occurred_on=occurred_on, source=source, project_id=project_id, note=note,
            reverses=None,
        )  # fmt: skip

    def reverse(
        self, ctx: CommandContext, asset_id: AssetId, entry_id: EntryId, note: str
    ) -> EntryId:
        """Cancels one earlier entry exactly. Entries are never edited or deleted."""
        actor = ctx.require_actor()
        actor.require(Permission.USAGE_CORRECT)
        target = next((e for e in self._s.usage.for_asset(asset_id) if e.id == entry_id), None)
        if target is None:
            raise NotFound("Usage entry not found.")
        return self._append(
            ctx, actor, "usage.reverse", asset_id, meter=target.meter, amount=-target.amount,
            occurred_on=target.occurred_on, source=UsageSource.REVERSAL,
            project_id=target.project_id, note=note or "Reversal", reverses=entry_id,
        )  # fmt: skip

    def _append(
        self, ctx: CommandContext, actor: Actor, action: str, asset_id: AssetId, *,
        meter: Meter, amount: Decimal, occurred_on: date, source: UsageSource,
        project_id: ProjectId | None, note: str, reverses: EntryId | None,
    ) -> EntryId:  # fmt: skip
        entry_id = EntryId(ctx.derive("usage"))

        def execute() -> Outcome:
            asset = self._s.assets.get(asset_id)
            if asset is None or asset.is_deleted:
                raise NotFound("Asset not found.")
            item_type = self._s.item_types.get(asset.item_type_id)
            if item_type is None:
                raise NotFound("Item type not found.")
            existing = self._s.usage.for_asset(asset_id)
            done = next((e for e in existing if e.id == entry_id), None)
            if done is None:
                entry = UsageEntry.build(
                    id=entry_id, asset_id=asset_id, sequence=len(existing) + 1, meter=meter,
                    amount=amount, occurred_on=occurred_on, source=source,
                    recorded_at=self._clock.now(), recorded_by=actor.user_id,
                    command_id=ctx.command_id, project_id=project_id, reverses=reverses, note=note,
                )  # fmt: skip
                check_new_entry(existing, entry, item_type)
                add_once(self._s.usage.append, entry)
                done = entry
            return Outcome("usage_entry", str(entry_id), None, done.model_dump(mode="json"))

        self._run.run(ctx, action, execute)
        return entry_id
