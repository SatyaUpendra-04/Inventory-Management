"""Consumable stock (GCP banners and similar)."""

from __future__ import annotations

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once
from ims.domain.common.errors import NotFound
from ims.domain.common.ids import EntryId, ItemTypeId, LocationId, ProjectId
from ims.domain.identity.roles import Permission
from ims.domain.stock.ledger import (
    MovementKind,
    StockMovement,
    StockPosition,
    check_new_movement,
    position,
)
from ims.ports.clock import Clock
from ims.ports.repository import Storage

_CREW_MOVEMENTS = frozenset({MovementKind.ISSUED, MovementKind.RETURNED, MovementKind.CONSUMED})


class StockService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    def position(self, actor: Actor, item_type_id: ItemTypeId) -> StockPosition:
        actor.require(Permission.STOCK_VIEW)
        return position(self._s.stock.for_item_type(item_type_id))

    def movements(self, actor: Actor, item_type_id: ItemTypeId) -> list[StockMovement]:
        actor.require(Permission.STOCK_VIEW)
        return self._s.stock.for_item_type(item_type_id)

    def record(
        self,
        ctx: CommandContext,
        *,
        item_type_id: ItemTypeId,
        location_id: LocationId,
        kind: MovementKind,
        quantity: int,
        project_id: ProjectId | None = None,
        reason: str = "",
    ) -> EntryId:
        actor = ctx.require_actor()
        actor.require(Permission.STOCK_MOVE if kind in _CREW_MOVEMENTS else Permission.STOCK_MANAGE)
        movement_id = EntryId(ctx.derive("stock"))

        def execute() -> Outcome:
            item_type = self._s.item_types.get(item_type_id)
            if item_type is None:
                raise NotFound("Item type not found.")
            existing = self._s.stock.for_item_type(item_type_id)
            done = next((m for m in existing if m.id == movement_id), None)
            if done is None:
                movement = StockMovement.build(
                    id=movement_id, item_type_id=item_type_id, sequence=len(existing) + 1,
                    location_id=location_id, kind=kind, quantity=quantity,
                    recorded_at=self._clock.now(), recorded_by=actor.user_id,
                    command_id=ctx.command_id, project_id=project_id, reason=reason,
                )  # fmt: skip
                check_new_movement(existing, movement, item_type)
                add_once(self._s.stock.append, movement)
                done = movement
            return Outcome("stock_movement", str(movement_id), None, done.model_dump(mode="json"))

        self._run.run(ctx, f"stock.{kind.value}", execute)
        return movement_id
