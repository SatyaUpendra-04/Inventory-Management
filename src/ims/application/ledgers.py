"""Appending to the asset and stock ledgers, shared by every service that changes them.

Each helper is idempotent within a command: the entry ID is derived from the command ID
and a ``purpose``, so a retried command finds its own earlier entry and returns it
instead of writing a second one (ADR-0005). One command can therefore write many
entries (a deployment: one status event per asset) and still be retried safely.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ims.application.context import Actor, CommandContext
from ims.application.runner import add_once
from ims.domain.assets.catalogue import Meter
from ims.domain.assets.status import (
    StatusChange,
    StatusEvent,
    apply_change,
    replay,
    required_permissions,
)
from ims.domain.common.errors import NotFound
from ims.domain.common.ids import AssetId, EntryId, ItemTypeId, LocationId, ProjectId
from ims.domain.stock.ledger import MovementKind, StockMovement, check_new_movement
from ims.domain.usage.ledger import UsageEntry, UsageSource, check_new_entry
from ims.ports.clock import Clock
from ims.ports.repository import Storage


def append_status(
    storage: Storage,
    clock: Clock,
    ctx: CommandContext,
    actor: Actor,
    asset_id: AssetId,
    change: StatusChange,
    purpose: str = "status",
) -> StatusEvent:
    """Applies one status change if the rules and the actor's role allow it."""
    events = storage.status_events.for_asset(asset_id)
    event_id = EntryId(ctx.derive(purpose))
    done = next((e for e in events if e.id == event_id), None)
    if done is not None:
        return done
    current = replay(events)
    actor.require(*sorted(required_permissions(current, change)))
    after = apply_change(current, change)
    event = StatusEvent(
        id=event_id, asset_id=asset_id, sequence=len(events) + 1, command_id=ctx.command_id,
        recorded_at=clock.now(), recorded_by=actor.user_id, before=current, after=after,
        reason=change.reason, project_id=change.project_id,
    )  # fmt: skip
    add_once(storage.status_events.append, event)
    return event


def append_usage(
    storage: Storage,
    clock: Clock,
    ctx: CommandContext,
    actor: Actor,
    asset_id: AssetId,
    *,
    meter: Meter,
    amount: Decimal,
    occurred_on: date,
    source: UsageSource,
    project_id: ProjectId | None = None,
    note: str = "",
    reverses: EntryId | None = None,
    purpose: str = "usage",
) -> UsageEntry:
    asset = storage.assets.get(asset_id)
    if asset is None or asset.is_deleted:
        raise NotFound("Asset not found.")
    item_type = storage.item_types.get(asset.item_type_id)
    if item_type is None:
        raise NotFound("Item type not found.")
    existing = storage.usage.for_asset(asset_id)
    entry_id = EntryId(ctx.derive(purpose))
    done = next((e for e in existing if e.id == entry_id), None)
    if done is not None:
        return done
    entry = UsageEntry.build(
        id=entry_id, asset_id=asset_id, sequence=len(existing) + 1, meter=meter, amount=amount,
        occurred_on=occurred_on, source=source, recorded_at=clock.now(),
        recorded_by=actor.user_id, command_id=ctx.command_id, project_id=project_id,
        reverses=reverses, note=note,
    )  # fmt: skip
    check_new_entry(existing, entry, item_type)
    add_once(storage.usage.append, entry)
    return entry


def append_movement(
    storage: Storage,
    clock: Clock,
    ctx: CommandContext,
    actor: Actor,
    *,
    item_type_id: ItemTypeId,
    location_id: LocationId,
    kind: MovementKind,
    quantity: int,
    project_id: ProjectId | None = None,
    reason: str = "",
    purpose: str = "stock",
) -> StockMovement:
    item_type = storage.item_types.get(item_type_id)
    if item_type is None:
        raise NotFound("Item type not found.")
    existing = storage.stock.for_item_type(item_type_id)
    movement_id = EntryId(ctx.derive(purpose))
    done = next((m for m in existing if m.id == movement_id), None)
    if done is not None:
        return done
    movement = StockMovement.build(
        id=movement_id, item_type_id=item_type_id, sequence=len(existing) + 1,
        location_id=location_id, kind=kind, quantity=quantity, recorded_at=clock.now(),
        recorded_by=actor.user_id, command_id=ctx.command_id, project_id=project_id,
        reason=reason,
    )  # fmt: skip
    check_new_movement(existing, movement, item_type)
    add_once(storage.stock.append, movement)
    return movement
