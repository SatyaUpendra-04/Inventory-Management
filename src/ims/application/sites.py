"""Sites: stores, mine sites, workshops and offices (rules catalogue L1, L2)."""

from __future__ import annotations

from typing import Any

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.catalogue import TrackingMode
from ims.domain.common.errors import ConflictError, NotFound, RuleViolation
from ims.domain.common.ids import LocationId
from ims.domain.identity.roles import Permission
from ims.domain.sites.site import Site
from ims.domain.stock.ledger import position
from ims.ports.clock import Clock
from ims.ports.repository import Storage

SITE_FIELDS = frozenset(
    {"code", "name", "kind", "region", "latitude", "longitude", "area_hectares", "mineral",
     "status", "notes"}
)  # fmt: skip


def _snapshot(site: Site) -> dict[str, Any]:
    return site.model_dump(mode="json")


class SiteService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    def list_sites(self, actor: Actor, *, include_deleted: bool = False) -> list[Site]:
        actor.require(Permission.SITE_VIEW)
        return self._s.sites.list(include_deleted=include_deleted)

    def get(self, actor: Actor, site_id: LocationId) -> Site:
        actor.require(Permission.SITE_VIEW)
        return self._require(site_id)

    def create(self, ctx: CommandContext, **fields: Any) -> LocationId:
        ctx.require_actor().require(Permission.SITE_MANAGE)
        self._check_fields(fields)
        site_id = LocationId(ctx.derive("site"))

        def execute() -> Outcome:
            site = Site.build(id=site_id, **fields)
            if self._s.sites.get(site_id) is None:
                self._check_unique(site)
            add_once(self._s.sites.add, site)
            return Outcome("site", str(site_id), None, _snapshot(site))

        self._run.run(ctx, "site.create", execute)
        return site_id

    def update(
        self, ctx: CommandContext, site_id: LocationId, expected_version: int, **changes: Any
    ) -> LocationId:
        ctx.require_actor().require(Permission.SITE_MANAGE)
        self._check_fields(changes)

        def execute() -> Outcome:
            stored = self._require(site_id)
            candidate = stored.next_version(**changes)
            if stored.version == expected_version + 1 and candidate.model_dump(
                exclude={"version"}
            ) == stored.model_dump(exclude={"version"}):
                return Outcome("site", str(site_id), None, _snapshot(stored))
            if stored.version != expected_version:
                raise ConflictError("This site was changed by someone else. Reload and try again.")
            self._check_unique(candidate)
            update_once(self._s.sites.update, lambda: self._s.sites.get(site_id), candidate)
            return Outcome("site", str(site_id), _snapshot(stored), _snapshot(candidate))

        self._run.run(ctx, "site.update", execute)
        return site_id

    def delete(self, ctx: CommandContext, site_id: LocationId, expected_version: int) -> LocationId:
        """Soft delete; refused while stock is still held at the site (rule L2)."""
        ctx.require_actor().require(Permission.SITE_MANAGE)

        def execute() -> Outcome:
            stored = self._s.sites.get(site_id)
            if stored is None:
                raise NotFound("Site not found.")
            if stored.is_deleted:
                return Outcome("site", str(site_id), None, _snapshot(stored))
            if stored.version != expected_version:
                raise ConflictError("This site was changed by someone else. Reload and try again.")
            held = self._stock_held_at(site_id)
            if held:
                raise RuleViolation(
                    f"{stored.label} still holds stock ({held}). Move or write it off first."
                )
            after = stored.next_version(deleted_at=self._clock.now())
            update_once(self._s.sites.update, lambda: self._s.sites.get(site_id), after)
            return Outcome("site", str(site_id), _snapshot(stored), _snapshot(after))

        self._run.run(ctx, "site.delete", execute)
        return site_id

    # ------------------------------------------------------------------ helpers

    def _require(self, site_id: LocationId) -> Site:
        site = self._s.sites.get(site_id)
        if site is None or site.is_deleted:
            raise NotFound("Site not found.")
        return site

    def _check_fields(self, fields: dict[str, Any]) -> None:
        unknown = set(fields) - SITE_FIELDS
        if unknown:
            raise RuleViolation(f"These fields cannot be set here: {', '.join(sorted(unknown))}.")

    def _check_unique(self, site: Site) -> None:
        existing = self._s.sites.find_by_code(site.code)
        if existing is not None and existing.id != site.id:
            note = " by a deleted site" if existing.is_deleted else ""
            raise RuleViolation(f"Site code {site.code} is already in use{note}.")

    def _stock_held_at(self, site_id: LocationId) -> str:
        held: list[str] = []
        for item_type in self._s.item_types.list(include_inactive=True):
            if item_type.tracking is not TrackingMode.CONSUMABLE:
                continue
            quantity = position(self._s.stock.for_item_type(item_type.id)).on_hand_at(site_id)
            if quantity:
                held.append(f"{quantity} x {item_type.name}")
        return ", ".join(held)
