"""Kits and kit templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.asset import Asset
from ims.domain.common.errors import ConflictError, NotFound, RuleViolation
from ims.domain.common.ids import AssetId, ItemTypeId, KitId, KitTemplateId, LocationId
from ims.domain.identity.roles import Permission
from ims.domain.kits import (
    DEFAULT_TEMPLATES,
    Completeness,
    Kit,
    KitTemplate,
    check_member,
    completeness,
)
from ims.ports.clock import Clock
from ims.ports.repository import Storage

KIT_FIELDS = frozenset({"code", "name", "template_id", "home_site_id", "notes"})


@dataclass(frozen=True, slots=True)
class KitOverview:
    kit: Kit
    template: KitTemplate | None
    members: list[Asset]
    completeness: Completeness | None


def _snapshot(kit: Kit) -> dict[str, Any]:
    return kit.model_dump(mode="json")


class KitService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ templates

    def install_default_templates(self, ctx: CommandContext) -> int:
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        added: list[str] = []

        def execute() -> Outcome:
            for template in DEFAULT_TEMPLATES:
                if self._s.kit_templates.get(template.id) is None:
                    add_once(self._s.kit_templates.add, template)
                    added.append(template.name)
            return Outcome("kit_templates", "defaults", None, {"added": added})

        self._run.run(ctx, "kit_templates.install_defaults", execute)
        return len(added)

    def templates(self, actor: Actor) -> list[KitTemplate]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.kit_templates.list()

    # ------------------------------------------------------------------ kits

    def list_kits(self, actor: Actor) -> list[KitOverview]:
        actor.require(Permission.ASSET_VIEW)
        return [self._overview(k) for k in self._s.kits.list()]

    def get(self, actor: Actor, kit_id: KitId) -> KitOverview:
        actor.require(Permission.ASSET_VIEW)
        return self._overview(self._require(kit_id))

    def create(
        self,
        ctx: CommandContext,
        *,
        code: str,
        name: str,
        template_id: KitTemplateId | None = None,
        home_site_id: LocationId | None = None,
        notes: str = "",
    ) -> KitId:
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        kit_id = KitId(ctx.derive("kit"))

        def execute() -> Outcome:
            kit = Kit.build(
                id=kit_id, code=code, name=name, template_id=template_id,
                home_site_id=home_site_id, notes=notes,
            )  # fmt: skip
            if template_id is not None and self._s.kit_templates.get(template_id) is None:
                raise NotFound("Kit template not found.")
            if self._s.kits.get(kit_id) is None:
                self._check_unique(kit)
            add_once(self._s.kits.add, kit)
            return Outcome("kit", str(kit_id), None, _snapshot(kit))

        self._run.run(ctx, "kit.create", execute)
        return kit_id

    def update(
        self, ctx: CommandContext, kit_id: KitId, expected_version: int, **changes: Any
    ) -> KitId:
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        unknown = set(changes) - KIT_FIELDS
        if unknown:
            raise RuleViolation(
                f"These fields cannot be changed here: {', '.join(sorted(unknown))}."
            )
        return self._change(
            ctx, kit_id, expected_version, "kit.update", lambda k: k.next_version(**changes)
        )

    def add_member(
        self, ctx: CommandContext, kit_id: KitId, expected_version: int, asset_id: AssetId
    ) -> KitId:
        ctx.require_actor().require(Permission.ASSET_MANAGE)

        def change(kit: Kit) -> Kit:
            if asset_id in kit.members:
                raise RuleViolation("That asset is already in this kit.")
            asset = self._s.assets.get(asset_id)
            if asset is None or asset.is_deleted:
                raise NotFound("Asset not found.")
            item_type = self._s.item_types.get(asset.item_type_id)
            if item_type is None:
                raise NotFound("Item type not found.")
            other = self._s.kits.find_by_member(asset_id)
            check_member(item_type, other.code if other and other.id != kit.id else None)
            return kit.next_version(members=(*kit.members, asset_id))

        return self._change(ctx, kit_id, expected_version, "kit.add_member", change)

    def remove_member(
        self, ctx: CommandContext, kit_id: KitId, expected_version: int, asset_id: AssetId
    ) -> KitId:
        ctx.require_actor().require(Permission.ASSET_MANAGE)

        def change(kit: Kit) -> Kit:
            if asset_id not in kit.members:
                raise RuleViolation("That asset is not in this kit.")
            return kit.next_version(members=tuple(m for m in kit.members if m != asset_id))

        return self._change(ctx, kit_id, expected_version, "kit.remove_member", change)

    def delete(self, ctx: CommandContext, kit_id: KitId, expected_version: int) -> KitId:
        """Breaks the kit up; its assets stay registered and become free to join other kits."""
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        return self._change(
            ctx, kit_id, expected_version, "kit.delete",
            lambda k: k.next_version(deleted_at=self._clock.now(), members=()),
        )  # fmt: skip

    # ------------------------------------------------------------------ helpers

    def _change(self, ctx: CommandContext, kit_id: KitId, expected_version: int, action: str,
                change: Any) -> KitId:  # fmt: skip
        def execute() -> Outcome:
            stored = self._s.kits.get(kit_id)
            if stored is None:
                raise NotFound("Kit not found.")
            if stored.version == expected_version + 1:
                return Outcome("kit", str(kit_id), None, _snapshot(stored))  # retry, already done
            if stored.version != expected_version:
                raise ConflictError("This kit was changed by someone else. Reload and try again.")
            if stored.is_deleted:
                raise NotFound("Kit not found.")
            after = change(stored)
            self._check_unique(after)
            update_once(self._s.kits.update, lambda: self._s.kits.get(kit_id), after)
            return Outcome("kit", str(kit_id), _snapshot(stored), _snapshot(after))

        self._run.run(ctx, action, execute)
        return kit_id

    def _require(self, kit_id: KitId) -> Kit:
        kit = self._s.kits.get(kit_id)
        if kit is None or kit.is_deleted:
            raise NotFound("Kit not found.")
        return kit

    def _check_unique(self, kit: Kit) -> None:
        other = self._s.kits.find_by_code(kit.code)
        if other is not None and other.id != kit.id:
            raise RuleViolation(f"Kit code {kit.code} is already in use.")

    def _overview(self, kit: Kit) -> KitOverview:
        template = self._s.kit_templates.get(kit.template_id) if kit.template_id else None
        members = [a for a in (self._s.assets.get(m) for m in kit.members) if a is not None]
        types: dict[AssetId, ItemTypeId] = {a.id: a.item_type_id for a in members}
        return KitOverview(
            kit=kit,
            template=template,
            members=members,
            completeness=completeness(template, types) if template else None,
        )
