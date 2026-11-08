"""Asset registry: configuration, compliance documents, firmware and the full asset view."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import ItemType, Meter
from ims.domain.assets.configuration import (
    ConfigChange,
    ConfigEvent,
    Placement,
    check_install,
    current_placement,
)
from ims.domain.assets.documents import (
    AssetDocument,
    DocumentKind,
    check_document_for_type,
    compliance_problems,
)
from ims.domain.assets.firmware import FirmwareRecord, check_new_firmware
from ims.domain.assets.status import AssetStatus, Serviceability, StatusEvent, replay
from ims.domain.common.errors import ConflictError, NotFound, RuleViolation
from ims.domain.common.ids import AssetId, DocumentId, EntryId
from ims.domain.files import DOCUMENT_KINDS, MAX_DOCUMENT_BYTES, check_upload
from ims.domain.identity.roles import Permission
from ims.domain.kits import Kit
from ims.domain.sites.site import Site
from ims.domain.usage.ledger import totals
from ims.ports.clock import Clock
from ims.ports.files import FileStore
from ims.ports.repository import Storage

DOCUMENT_FIELDS = frozenset({"kind", "reference", "issuer", "issued_on", "valid_until", "notes"})


@dataclass(frozen=True, slots=True)
class InstalledComponent:
    asset: Asset
    item_type: ItemType
    position: str


@dataclass(frozen=True, slots=True)
class AssetOverview:
    asset: Asset
    item_type: ItemType
    status: AssetStatus
    meters: dict[Meter, Decimal]
    home_site: Site | None
    installed_on: tuple[Asset, str] | None  # (parent airframe, position) when a component
    components: list[InstalledComponent]
    documents: list[tuple[AssetDocument, str]]  # (document, status)
    firmware: list[FirmwareRecord]
    kit: Kit | None
    problems: list[tuple[str, str]]  # (severity, message)
    history: list[StatusEvent]


@dataclass(frozen=True, slots=True)
class AssetSummary:
    """One row of the equipment list."""

    asset: Asset
    item_type: ItemType
    status: AssetStatus
    meters: dict[Meter, Decimal]
    home_site: Site | None
    kit_code: str | None
    problems: list[tuple[str, str]]


@dataclass(frozen=True, slots=True)
class ComplianceAlert:
    asset: Asset
    item_type: ItemType
    severity: str
    message: str


class RegistryService:
    def __init__(
        self, storage: Storage, runner: CommandRunner, clock: Clock, files: FileStore
    ) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock
        self._files = files

    # ------------------------------------------------------------------ queries

    def overview(self, actor: Actor, asset_id: AssetId) -> AssetOverview:
        actor.require(Permission.ASSET_VIEW)
        asset = self._require_asset(asset_id)
        item_type = self._type_of(asset)
        today = self._clock.today()
        documents = self._s.documents.for_asset(asset_id)
        placement = self._placement(asset_id)
        installed_on = None
        if placement is not None:
            parent = self._s.assets.get(placement.parent_id)
            if parent is not None:
                installed_on = (parent, placement.position)
        home = self._s.sites.get(asset.home_site_id) if asset.home_site_id else None
        return AssetOverview(
            asset=asset,
            item_type=item_type,
            status=replay(self._s.status_events.for_asset(asset_id)),
            meters=totals(self._s.usage.for_asset(asset_id)),
            home_site=home,
            installed_on=installed_on,
            components=self._components(asset_id),
            documents=[(d, d.status_on(today)) for d in documents],
            firmware=self._s.firmware.for_asset(asset_id),
            kit=self._s.kits.find_by_member(asset_id),
            problems=compliance_problems(item_type, documents, today),
            history=self._s.status_events.for_asset(asset_id),
        )

    def summaries(self, actor: Actor) -> list[AssetSummary]:
        """Every registered asset with status, meters, site, kit and compliance."""
        actor.require(Permission.ASSET_VIEW)
        today = self._clock.today()
        types = {t.id: t for t in self._s.item_types.list(include_inactive=True)}
        sites = {s.id: s for s in self._s.sites.list(include_deleted=True)}
        kit_of: dict[AssetId, str] = {m: k.code for k in self._s.kits.list() for m in k.members}
        documents: dict[AssetId, list[AssetDocument]] = {}
        for document in self._s.documents.list():
            documents.setdefault(document.asset_id, []).append(document)
        rows: list[AssetSummary] = []
        for asset in self._s.assets.list():
            item_type = types.get(asset.item_type_id)
            if item_type is None:
                continue
            rows.append(
                AssetSummary(
                    asset=asset,
                    item_type=item_type,
                    status=replay(self._s.status_events.for_asset(asset.id)),
                    meters=totals(self._s.usage.for_asset(asset.id)),
                    home_site=sites.get(asset.home_site_id) if asset.home_site_id else None,
                    kit_code=kit_of.get(asset.id),
                    problems=compliance_problems(item_type, documents.get(asset.id, []), today),
                )
            )
        return rows

    def loose_components(self, actor: Actor) -> list[tuple[Asset, ItemType]]:
        """Components that are not installed anywhere (candidates for fitting)."""
        actor.require(Permission.ASSET_VIEW)
        result: list[tuple[Asset, ItemType]] = []
        for asset in self._s.assets.list():
            item_type = self._s.item_types.get(asset.item_type_id)
            if (
                item_type is not None
                and item_type.is_component
                and self._placement(asset.id) is None
            ):
                result.append((asset, item_type))
        return result

    def compliance_alerts(self, actor: Actor) -> list[ComplianceAlert]:
        """Every missing, expired or soon-expiring document across the fleet."""
        actor.require(Permission.ASSET_VIEW)
        today = self._clock.today()
        by_asset: dict[AssetId, list[AssetDocument]] = {}
        for document in self._s.documents.list():
            by_asset.setdefault(document.asset_id, []).append(document)
        alerts: list[ComplianceAlert] = []
        for asset in self._s.assets.list():
            item_type = self._type_of(asset)
            status = replay(self._s.status_events.for_asset(asset.id))
            if status.serviceability is Serviceability.RETIRED:
                continue
            for severity, message in compliance_problems(
                item_type, by_asset.get(asset.id, []), today
            ):
                alerts.append(ComplianceAlert(asset, item_type, severity, message))
        return sorted(alerts, key=lambda a: (a.severity != "danger", a.asset.asset_tag))

    # ------------------------------------------------------------------ configuration

    def install(
        self,
        ctx: CommandContext,
        component_id: AssetId,
        parent_id: AssetId,
        position: str = "",
        note: str = "",
    ) -> AssetId:
        """Fits a component (motor, propellers, camera ...) to a drone airframe."""
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)
        return self._config(
            ctx, actor, component_id, parent_id, ConfigChange.INSTALLED, position, note
        )

    def remove(self, ctx: CommandContext, component_id: AssetId, note: str = "") -> AssetId:
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)
        placement = self._placement(component_id)
        event_id = EntryId(ctx.derive("config"))
        done = any(e.id == event_id for e in self._s.configuration.for_component(component_id))
        if placement is None and not done:
            raise RuleViolation("This component is not installed on anything.")
        parent_id = placement.parent_id if placement else self._last_parent(component_id)
        position = placement.position if placement else ""
        return self._config(
            ctx, actor, component_id, parent_id, ConfigChange.REMOVED, position, note
        )

    def _config(
        self, ctx: CommandContext, actor: Actor, component_id: AssetId, parent_id: AssetId,
        change: ConfigChange, position: str, note: str,
    ) -> AssetId:  # fmt: skip
        event_id = EntryId(ctx.derive("config"))

        def execute() -> Outcome:
            component = self._require_asset(component_id)
            parent = self._require_asset(parent_id)
            events = self._s.configuration.for_component(component_id)
            if not any(e.id == event_id for e in events):
                if change is ConfigChange.INSTALLED:
                    check_install(
                        component_type=self._type_of(component),
                        component_status=replay(self._s.status_events.for_asset(component_id)),
                        component_placement=current_placement(events),
                        parent_type=self._type_of(parent),
                        parent_status=replay(self._s.status_events.for_asset(parent_id)),
                        position=position,
                        occupied_positions=[c.position for c in self._components(parent_id)],
                    )
                event = ConfigEvent(
                    id=event_id, component_id=component_id, sequence=len(events) + 1,
                    change=change, parent_id=parent_id, position=position.strip(),
                    recorded_at=self._clock.now(), recorded_by=actor.user_id,
                    command_id=ctx.command_id, note=note,
                )  # fmt: skip
                add_once(self._s.configuration.append, event)
            return Outcome(
                "configuration", str(component_id), None,
                {"change": change.value, "parent": str(parent_id), "position": position},
            )  # fmt: skip

        self._run.run(ctx, f"configuration.{change.value}", execute)
        return component_id

    # ------------------------------------------------------------------ documents

    def add_document(
        self,
        ctx: CommandContext,
        asset_id: AssetId,
        *,
        kind: DocumentKind,
        reference: str,
        issuer: str = "",
        issued_on: date | None = None,
        valid_until: date | None = None,
        notes: str = "",
        file_content: bytes | None = None,
    ) -> DocumentId:
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        document_id = DocumentId(ctx.derive("document"))
        file_ref = self._store_file(file_content)

        def execute() -> Outcome:
            asset = self._require_asset(asset_id)
            document = AssetDocument.build(
                id=document_id, asset_id=asset_id, kind=kind, reference=reference, issuer=issuer,
                issued_on=issued_on, valid_until=valid_until, file=file_ref, notes=notes,
            )  # fmt: skip
            check_document_for_type(document, self._type_of(asset))
            add_once(self._s.documents.add, document)
            return Outcome("document", str(document_id), None, document.model_dump(mode="json"))

        self._run.run(ctx, "document.add", execute)
        return document_id

    def update_document(
        self,
        ctx: CommandContext,
        document_id: DocumentId,
        expected_version: int,
        *,
        file_content: bytes | None = None,
        **changes: Any,
    ) -> DocumentId:
        ctx.require_actor().require(Permission.ASSET_MANAGE)
        unknown = set(changes) - DOCUMENT_FIELDS
        if unknown:
            raise RuleViolation(
                f"These fields cannot be changed here: {', '.join(sorted(unknown))}."
            )
        file_ref = self._store_file(file_content)
        if file_ref is not None:
            changes["file"] = file_ref

        def execute() -> Outcome:
            stored = self._require_document(document_id)
            candidate = stored.next_version(**changes)
            if stored.version == expected_version + 1 and candidate.model_dump(
                exclude={"version"}
            ) == stored.model_dump(exclude={"version"}):
                return Outcome("document", str(document_id), None, stored.model_dump(mode="json"))
            if stored.version != expected_version:
                raise ConflictError(
                    "This document was changed by someone else. Reload and try again."
                )
            check_document_for_type(candidate, self._type_of(self._require_asset(stored.asset_id)))
            update_once(
                self._s.documents.update, lambda: self._s.documents.get(document_id), candidate
            )
            return Outcome(
                "document", str(document_id), stored.model_dump(mode="json"),
                candidate.model_dump(mode="json"),
            )  # fmt: skip

        self._run.run(ctx, "document.update", execute)
        return document_id

    def remove_document(
        self, ctx: CommandContext, document_id: DocumentId, expected_version: int
    ) -> DocumentId:
        ctx.require_actor().require(Permission.ASSET_MANAGE)

        def execute() -> Outcome:
            stored = self._s.documents.get(document_id)
            if stored is None:
                raise NotFound("Document not found.")
            if stored.is_deleted:
                return Outcome("document", str(document_id), None, None)
            if stored.version != expected_version:
                raise ConflictError(
                    "This document was changed by someone else. Reload and try again."
                )
            after = stored.next_version(deleted_at=self._clock.now())
            update_once(self._s.documents.update, lambda: self._s.documents.get(document_id), after)
            return Outcome("document", str(document_id), stored.model_dump(mode="json"), None)

        self._run.run(ctx, "document.remove", execute)
        return document_id

    # ------------------------------------------------------------------ firmware

    def record_firmware(
        self,
        ctx: CommandContext,
        asset_id: AssetId,
        version: str,
        installed_on: date,
        note: str = "",
    ) -> EntryId:
        actor = ctx.require_actor()
        actor.require(Permission.MAINTENANCE_MANAGE)
        record_id = EntryId(ctx.derive("firmware"))

        def execute() -> Outcome:
            self._require_asset(asset_id)
            existing = self._s.firmware.for_asset(asset_id)
            done = next((r for r in existing if r.id == record_id), None)
            if done is None:
                record = FirmwareRecord.build(
                    id=record_id, asset_id=asset_id, sequence=len(existing) + 1, version=version,
                    installed_on=installed_on, recorded_at=self._clock.now(),
                    recorded_by=actor.user_id, command_id=ctx.command_id, note=note,
                )  # fmt: skip
                check_new_firmware(existing, record)
                add_once(self._s.firmware.append, record)
                done = record
            return Outcome("firmware", str(asset_id), None, done.model_dump(mode="json"))

        self._run.run(ctx, "firmware.record", execute)
        return record_id

    # ------------------------------------------------------------------ helpers

    def _require_asset(self, asset_id: AssetId) -> Asset:
        asset = self._s.assets.get(asset_id)
        if asset is None or asset.is_deleted:
            raise NotFound("Asset not found.")
        return asset

    def _require_document(self, document_id: DocumentId) -> AssetDocument:
        document = self._s.documents.get(document_id)
        if document is None or document.is_deleted:
            raise NotFound("Document not found.")
        return document

    def _type_of(self, asset: Asset) -> ItemType:
        item_type = self._s.item_types.get(asset.item_type_id)
        if item_type is None:
            raise NotFound("Item type not found.")
        return item_type

    def _placement(self, component_id: AssetId) -> Placement | None:
        return current_placement(self._s.configuration.for_component(component_id))

    def _last_parent(self, component_id: AssetId) -> AssetId:
        events = self._s.configuration.for_component(component_id)
        if not events:
            raise RuleViolation("This component has never been installed.")
        return events[-1].parent_id

    def _components(self, parent_id: AssetId) -> list[InstalledComponent]:
        installed: list[InstalledComponent] = []
        seen: set[AssetId] = set()
        for event in self._s.configuration.for_parent(parent_id):
            if event.component_id in seen:
                continue
            seen.add(event.component_id)
            placement = self._placement(event.component_id)
            if placement is not None and placement.parent_id == parent_id:
                component = self._s.assets.get(event.component_id)
                if component is not None:
                    installed.append(
                        InstalledComponent(component, self._type_of(component), placement.position)
                    )
        return sorted(installed, key=lambda c: (c.position or "~", c.asset.asset_tag))

    def _store_file(self, content: bytes | None) -> str | None:
        if content is None:
            return None
        kind = check_upload(content, DOCUMENT_KINDS, MAX_DOCUMENT_BYTES)
        return self._files.put(content, kind)
