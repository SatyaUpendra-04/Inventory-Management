"""Consumable stock (GCP banners and similar)."""

from __future__ import annotations

from collections.abc import Mapping
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


@dataclass(frozen=True, slots=True)
class VarianceLine:
    """One store in a stocktake: what the records said, what was counted, the difference."""

    location_id: LocationId
    expected: int
    counted: int

    @property
    def variance(self) -> int:
        return self.counted - self.expected


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

    def stocktake(
        self,
        ctx: CommandContext,
        item_type_id: ItemTypeId,
        counts: Mapping[LocationId, int],
        note: str = "",
    ) -> list[VarianceLine]:
        """Counts every listed store at once; each difference is logged as an adjustment.

        Returns the variance report. Retrying the same command records nothing twice.
        """
        actor = ctx.require_actor()
        actor.require(Permission.STOCK_MANAGE)
        if not counts:
            raise RuleViolation("Enter a count for at least one store.")
        if any(n < 0 for n in counts.values()):
            raise RuleViolation("A count cannot be negative.")
        for site in counts:
            if self._s.sites.get(site) is None:
                raise NotFound("Site not found.")
        # Expected stock is what the records said before this stocktake's own adjustments,
        # so a retried command reports (and records) exactly the same thing.
        movements = self._s.stock.for_item_type(item_type_id)
        before = position([m for m in movements if m.command_id != ctx.command_id])
        report = [
            VarianceLine(site, before.on_hand_at(site), counts[site])
            for site in sorted(counts, key=str)
        ]
        label = note.strip() or f"Stocktake {self._clock.today():%d %b %Y}"

        def execute() -> Outcome:
            for line in report:
                if line.variance:
                    append_movement(
                        self._s, self._clock, ctx, actor, item_type_id=item_type_id,
                        location_id=line.location_id, kind=MovementKind.ADJUSTED,
                        quantity=line.variance,
                        reason=f"{label}: counted {line.counted}, records said {line.expected}",
                        purpose=f"stocktake:{line.location_id}",
                    )  # fmt: skip
            return Outcome(
                "stocktake", str(ctx.command_id), None,
                {str(r.location_id): {"expected": r.expected, "counted": r.counted}
                 for r in report},
            )  # fmt: skip

        self._run.run(ctx, "stock.stocktake", execute)
        return report
