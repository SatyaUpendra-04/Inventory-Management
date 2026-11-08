"""Consumable stock (GCP banners and similar)."""

from __future__ import annotations

from dataclasses import dataclass

from ims.application.context import Actor, CommandContext
from ims.application.ledgers import append_movement
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.catalogue import TrackingMode
from ims.domain.common.errors import NotFound, RuleViolation
from ims.domain.common.ids import EntryId, ItemTypeId, LocationId, ProjectId
from ims.domain.identity.roles import Permission
from ims.domain.stock.ledger import (
    MovementKind,
    StockMovement,
    StockPosition,
    needs_reorder,
    position,
)
from ims.domain.stock.reorder import ReorderLevel, reorder_level_id
from ims.ports.clock import Clock
from ims.ports.repository import Storage

_CREW_MOVEMENTS = frozenset({MovementKind.ISSUED, MovementKind.RETURNED, MovementKind.CONSUMED})


@dataclass(frozen=True, slots=True)
class SiteStock:
    location_id: LocationId
    on_hand: int
    reorder_level: int | None

    @property
    def low(self) -> bool:
        return self.reorder_level is not None and needs_reorder(self.on_hand, self.reorder_level)


class StockService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    def position(self, actor: Actor, item_type_id: ItemTypeId) -> StockPosition:
        actor.require(Permission.STOCK_VIEW)
        return position(self._s.stock.for_item_type(item_type_id))

    def by_site(self, actor: Actor, item_type_id: ItemTypeId) -> list[SiteStock]:
        """On-hand quantity and reorder level at every site that has either."""
        actor.require(Permission.STOCK_VIEW)
        pos = position(self._s.stock.for_item_type(item_type_id))
        levels = {
            r.location_id: r.level
            for r in self._s.reorder_levels.list()
            if r.item_type_id == item_type_id
        }
        sites = set(pos.on_hand) | set(levels)
        return [
            SiteStock(site, pos.on_hand_at(site), levels.get(site))
            for site in sorted(sites, key=str)
        ]

    def set_reorder_level(
        self, ctx: CommandContext, item_type_id: ItemTypeId, location_id: LocationId, level: int
    ) -> None:
        """Alert when stock at the site falls to ``level`` or fewer."""
        ctx.require_actor().require(Permission.STOCK_MANAGE)
        level_id = reorder_level_id(item_type_id, location_id)

        def execute() -> Outcome:
            item_type = self._s.item_types.get(item_type_id)
            if item_type is None:
                raise NotFound("Item type not found.")
            if item_type.tracking is not TrackingMode.CONSUMABLE:
                raise RuleViolation(f"{item_type.name} is not counted stock.")
            if self._s.sites.get(location_id) is None:
                raise NotFound("Site not found.")
            stored = self._s.reorder_levels.get(level_id)
            if stored is None:
                record = ReorderLevel.build(
                    id=level_id, item_type_id=item_type_id, location_id=location_id, level=level
                )
                add_once(self._s.reorder_levels.add, record)
                return Outcome("reorder_level", str(level_id), None, {"level": level})
            if stored.level == level:
                return Outcome("reorder_level", str(level_id), None, {"level": level})
            after = stored.next_version(level=level)
            update_once(
                self._s.reorder_levels.update, lambda: self._s.reorder_levels.get(level_id), after
            )
            return Outcome(
                "reorder_level", str(level_id), {"level": stored.level}, {"level": level}
            )

        self._run.run(ctx, "stock.set_reorder_level", execute)

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
            movement = append_movement(
                self._s, self._clock, ctx, actor, item_type_id=item_type_id,
                location_id=location_id, kind=kind, quantity=quantity, project_id=project_id,
                reason=reason,
            )  # fmt: skip
            return Outcome(
                "stock_movement", str(movement_id), None, movement.model_dump(mode="json")
            )

        self._run.run(ctx, f"stock.{kind.value}", execute)
        return movement_id
