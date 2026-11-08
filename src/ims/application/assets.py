"""Asset registration and status changes."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from ims.application.context import Actor, CommandContext
from ims.application.ledgers import append_status
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.asset import Asset, check_asset_against_type
from ims.domain.assets.catalogue import ItemType, Meter
from ims.domain.assets.status import (
    AssetStatus,
    StatusChange,
    StatusEvent,
    replay,
)
from ims.domain.common.errors import ConflictError, NotFound, RuleViolation
from ims.domain.common.ids import AssetId, EntryId, ItemTypeId, LocationId
from ims.domain.identity.roles import Permission
from ims.domain.usage.ledger import UsageEntry, UsageSource, check_new_entry
from ims.ports.clock import Clock
from ims.ports.repository import Storage

ASSET_EDITABLE_FIELDS = frozenset(
    {
        "asset_tag",
        "serial_number",
        "make",
        "model",
        "acquired_on",
        "warranty_until",
        "home_site_id",
        "notes",
    }
)


class AssetService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ queries

    def get(self, actor: Actor, asset_id: AssetId) -> Asset:
        actor.require(Permission.ASSET_VIEW)
        return self._require(asset_id)

    def list_assets(self, actor: Actor, *, item_type_id: ItemTypeId | None = None) -> list[Asset]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.assets.list(item_type_id=item_type_id)

    def status(self, actor: Actor, asset_id: AssetId) -> AssetStatus:
        actor.require(Permission.ASSET_VIEW)
        return replay(self._s.status_events.for_asset(asset_id))

    def suggest_tag(self, actor: Actor, item_type_id: ItemTypeId) -> str:
        """The next free tag for an item type, e.g. ``DRN-0004``."""
        actor.require(Permission.ASSET_VIEW)
        item_type = self._require_type(item_type_id)
        prefix = item_type.tag_prefix or "AST"
        numbers = [
            int(a.asset_tag.split("-", 1)[1])
            for a in self._s.assets.list(include_deleted=True)
            if a.asset_tag.startswith(f"{prefix}-") and a.asset_tag.split("-", 1)[1].isdigit()
        ]
        return f"{prefix}-{max(numbers, default=0) + 1:04d}"

    def history(self, actor: Actor, asset_id: AssetId) -> list[StatusEvent]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.status_events.for_asset(asset_id)

    # ------------------------------------------------------------------ commands

    def register(
        self,
        ctx: CommandContext,
        *,
        item_type_id: ItemTypeId,
        asset_tag: str,
        serial_number: str | None = None,
        make: str | None = None,
        model: str | None = None,
        acquired_on: date | None = None,
        warranty_until: date | None = None,
        notes: str = "",
        home_site_id: LocationId | None = None,
        opening_balances: Mapping[Meter, Decimal] | None = None,
    ) -> AssetId:
        """Registers a unit, with optional opening meter readings (e.g. hours already flown)."""
        actor = ctx.require_actor()
        actor.require(Permission.ASSET_MANAGE)

        def execute() -> Outcome:
            item_type = self._require_type(item_type_id)
            asset = Asset.build(
                id=ctx.derive("asset"), item_type_id=item_type_id, asset_tag=asset_tag,
                serial_number=serial_number, make=make, model=model, acquired_on=acquired_on,
                warranty_until=warranty_until, home_site_id=home_site_id, notes=notes,
            )  # fmt: skip
            check_asset_against_type(asset, item_type)
            if self._s.assets.get(asset.id) is None:
                self._check_unique(asset)
            add_once(self._s.assets.add, asset)
            for meter, amount in sorted((opening_balances or {}).items()):
                self._add_opening_balance(ctx, actor, asset, item_type, meter, amount)
            return Outcome("asset", str(asset.id), None, asset.model_dump(mode="json"))

        self._run.run(ctx, "asset.register", execute)
        return AssetId(ctx.derive("asset"))

    def update(
        self, ctx: CommandContext, asset_id: AssetId, expected_version: int, **changes: Any
    ) -> AssetId:
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        unknown = set(changes) - ASSET_EDITABLE_FIELDS
        if unknown:
            raise RuleViolation(
                f"These fields cannot be changed here: {', '.join(sorted(unknown))}."
            )

        def execute() -> Outcome:
            stored = self._require(asset_id)
            candidate = stored.next_version(**changes)
            if stored.version == expected_version + 1 and candidate.model_dump(
                exclude={"version"}
            ) == stored.model_dump(exclude={"version"}):
                return Outcome("asset", str(asset_id), None, stored.model_dump(mode="json"))
            if stored.version != expected_version:
                raise ConflictError("This asset was changed by someone else. Reload and try again.")
            check_asset_against_type(candidate, self._require_type(stored.item_type_id))
            self._check_unique(candidate)
            update_once(self._s.assets.update, lambda: self._s.assets.get(asset_id), candidate)
            return Outcome(
                "asset", str(asset_id), stored.model_dump(mode="json"),
                candidate.model_dump(mode="json"),
            )  # fmt: skip

        self._run.run(ctx, "asset.update", execute)
        return asset_id

    def change_status(
        self, ctx: CommandContext, asset_id: AssetId, change: StatusChange
    ) -> AssetId:
        """Applies one serviceability and/or custody change, if the rules and role allow it."""
        actor = ctx.require_actor()

        def execute() -> Outcome:
            self._require(asset_id)
            event = append_status(self._s, self._clock, ctx, actor, asset_id, change)
            return Outcome(
                "asset_status", str(asset_id), event.before.model_dump(mode="json"),
                event.after.model_dump(mode="json"),
            )  # fmt: skip

        self._run.run(ctx, "asset.change_status", execute)
        return asset_id

    # ------------------------------------------------------------------ helpers

    def _add_opening_balance(
        self, ctx: CommandContext, actor: Actor, asset: Asset, item_type: ItemType,
        meter: Meter, amount: Decimal,
    ) -> None:  # fmt: skip
        existing = self._s.usage.for_asset(asset.id)
        entry_id = EntryId(ctx.derive(f"opening:{meter.value}"))
        if any(e.id == entry_id for e in existing):
            return
        entry = UsageEntry.build(
            id=entry_id, asset_id=asset.id, sequence=len(existing) + 1, meter=meter,
            amount=amount, occurred_on=self._clock.today(), source=UsageSource.OPENING_BALANCE,
            recorded_at=self._clock.now(), recorded_by=actor.user_id, command_id=ctx.command_id,
            note="Opening balance at registration",
        )  # fmt: skip
        check_new_entry(existing, entry, item_type)
        add_once(self._s.usage.append, entry)

    def _require(self, asset_id: AssetId) -> Asset:
        asset = self._s.assets.get(asset_id)
        if asset is None or asset.is_deleted:
            raise NotFound("Asset not found.")
        return asset

    def _require_type(self, item_type_id: ItemTypeId) -> ItemType:
        item_type = self._s.item_types.get(item_type_id)
        if item_type is None:
            raise NotFound("Item type not found.")
        return item_type

    def _check_unique(self, asset: Asset) -> None:
        problems: list[str] = []
        by_tag = self._s.assets.find_by_tag(asset.asset_tag)
        if by_tag is not None and by_tag.id != asset.id:
            problems.append(f"Asset tag {asset.asset_tag} is already in use.")
        if asset.serial_number is not None:
            by_serial = self._s.assets.find_by_serial(asset.item_type_id, asset.serial_number)
            if by_serial is not None and by_serial.id != asset.id:
                problems.append(
                    f"Serial number {asset.serial_number} is already registered "
                    f"(asset {by_serial.asset_tag})."
                )
        if problems:
            raise RuleViolation(problems)
