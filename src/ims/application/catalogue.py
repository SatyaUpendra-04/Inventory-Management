"""Equipment catalogue use cases."""

from __future__ import annotations

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once
from ims.domain.assets.catalogue import DEFAULT_CATALOGUE, ItemType
from ims.domain.common.errors import NotFound, RuleViolation
from ims.domain.common.ids import ItemTypeId
from ims.domain.identity.roles import Permission
from ims.ports.repository import Storage


class CatalogueService:
    def __init__(self, storage: Storage, runner: CommandRunner) -> None:
        self._s = storage
        self._run = runner

    def list_item_types(self, actor: Actor, *, include_inactive: bool = False) -> list[ItemType]:
        actor.require(Permission.ASSET_VIEW)
        return self._s.item_types.list(include_inactive=include_inactive)

    def get(self, actor: Actor, item_type_id: ItemTypeId) -> ItemType:
        actor.require(Permission.ASSET_VIEW)
        item_type = self._s.item_types.get(item_type_id)
        if item_type is None:
            raise NotFound("Item type not found.")
        return item_type

    def install_defaults(self, ctx: CommandContext) -> int:
        """Adds any default item types that are missing. Safe to run any number of times."""
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        added: list[str] = []

        def execute() -> Outcome:
            for item_type in DEFAULT_CATALOGUE:
                if self._s.item_types.get(item_type.id) is None:
                    add_once(self._s.item_types.add, item_type)
                    added.append(item_type.code)
            return Outcome("catalogue", "defaults", None, {"added": added})

        self._run.run(ctx, "catalogue.install_defaults", execute)
        return len(added)

    def add_item_type(self, ctx: CommandContext, item_type: ItemType) -> ItemTypeId:
        """Adds a new item type. Its ID must come from ``ctx.derive('item_type')``."""
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        if item_type.id != ctx.derive("item_type"):
            raise RuleViolation("New item types must use the ID derived from the command.")

        def execute() -> Outcome:
            if self._s.item_types.get(item_type.id) is None:
                existing = self._s.item_types.find_by_code(item_type.code)
                if existing is not None:
                    raise RuleViolation(f"Item code {item_type.code} is already in use.")
            add_once(self._s.item_types.add, item_type)
            return Outcome("item_type", str(item_type.id), None, item_type.model_dump(mode="json"))

        self._run.run(ctx, "catalogue.add_item_type", execute)
        return item_type.id
