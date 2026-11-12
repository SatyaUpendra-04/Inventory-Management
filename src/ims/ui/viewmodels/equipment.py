"""Equipment: the fleet list, one asset's full record, and everything you can do to it."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from ims.application.registry import AssetOverview, AssetSummary
from ims.domain.assets.catalogue import Category, ItemType, Meter, TrackingMode
from ims.domain.assets.documents import DOCUMENT_LABELS, DocumentKind, allowed_kinds
from ims.domain.assets.status import (
    AssetStatus,
    Custody,
    Serviceability,
    StatusChange,
    apply_change,
    required_permissions,
)
from ims.domain.common.errors import DomainError, RuleViolation
from ims.domain.common.ids import AssetId, DocumentId, ItemTypeId, LocationId
from ims.ui.app_services import Services
from ims.ui.labels import Label, write_label_sheet
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import (
    describe_error,
    local_path,
    local_time,
    optional_date,
    optional_decimal,
    text,
)
from ims.ui.viewmodels.maintenance import DEFECT_LABELS, due_row
from ims.ui.viewmodels.session import SessionViewModel

CATEGORY_LABELS = {
    Category.DRONE: "Drones",
    Category.DRONE_COMPONENT: "Drone parts",
    Category.BATTERY: "Batteries",
    Category.GNSS: "GNSS & controllers",
    Category.FIELD_ELECTRONICS: "Field electronics",
    Category.SURVEY_ACCESSORY: "Survey accessories",
    Category.DATA_MEDIA: "Data media",
    Category.CONSUMABLE: "Consumables",
}
SERVICEABILITY = {
    Serviceability.SERVICEABLE: ("success", "Serviceable"),
    Serviceability.LIMITED: ("warning", "Limited"),
    Serviceability.UNSERVICEABLE: ("danger", "Grounded"),
    Serviceability.RETIRED: ("neutral", "Retired"),
}
CUSTODY = {
    Custody.IN_STORE: "In store",
    Custody.RESERVED: "Reserved",
    Custody.DEPLOYED: "Deployed",
    Custody.IN_MAINTENANCE: "In maintenance",
    Custody.IN_TRANSIT: "In transit",
    Custody.DISPOSED: "Disposed",
}
METER_LABELS = {Meter.HOURS: "Flight hours", Meter.CYCLES: "Cycles", Meter.LANDINGS: "Landings"}
DOC_STATUS = {
    "valid": ("success", "Valid"),
    "expiring": ("warning", "Expiring"),
    "expired": ("danger", "Expired"),
    "permanent": ("info", "No expiry"),
}

# (key, label, change, needs reason)
_S, _C = Serviceability, Custody
STATUS_ACTIONS: tuple[tuple[str, str, StatusChange, bool], ...] = (
    ("ground", "Ground", StatusChange(serviceability=_S.UNSERVICEABLE, reason="x"), True),
    ("limit", "Mark limited", StatusChange(serviceability=_S.LIMITED, reason="x"), True),
    ("certify", "Return to service", StatusChange(serviceability=_S.SERVICEABLE), False),
    ("toMaintenance", "Send to maintenance", StatusChange(custody=_C.IN_MAINTENANCE), False),
    ("toStore", "Back in store", StatusChange(custody=_C.IN_STORE), False),
    ("retire", "Retire", StatusChange(serviceability=_S.RETIRED, reason="x"), True),
    ("dispose", "Dispose", StatusChange(custody=_C.DISPOSED, reason="x"), True),
)

_ROLES = (
    "assetId",
    "version",
    "tag",
    "itemTypeId",
    "itemType",
    "category",
    "categoryLabel",
    "serial",
    "makeModel",
    "site",
    "serviceKind",
    "serviceLabel",
    "custody",
    "custodyLabel",
    "meters",
    "kitCode",
    "complianceKind",
    "complianceText",
    "search",
)


def _meters_text(meters: dict[Meter, Decimal]) -> str:
    parts = []
    if Meter.HOURS in meters:
        hours = f"{meters[Meter.HOURS]:,.2f}".rstrip("0").rstrip(".")
        parts.append(f"{hours} h")
    if Meter.CYCLES in meters:
        cycles = int(meters[Meter.CYCLES])
        parts.append(f"{cycles:,} cycle{'' if cycles == 1 else 's'}")
    return " · ".join(parts)


def _make_model(make: str | None, model: str | None) -> str:
    return " ".join(p for p in (make, model) if p)


def _worst(problems: list[tuple[str, str]]) -> tuple[str, str]:
    if not problems:
        return "", ""
    kind = "danger" if any(s == "danger" for s, _ in problems) else "warning"
    first = next(m for s, m in problems if s == kind)
    more = len(problems) - 1
    return kind, first + (f" (+{more} more)" if more else "")


def _status_text(status: AssetStatus) -> str:
    return f"{SERVICEABILITY[status.serviceability][1]} · {CUSTODY[status.custody]}"


def _label_title(row: dict[str, Any]) -> str:
    return " · ".join(p for p in (row["itemType"], row["makeModel"]) if p)


def _row(s: AssetSummary) -> dict[str, Any]:
    service_kind, service_label = SERVICEABILITY[s.status.serviceability]
    compliance_kind, compliance_text = _worst(s.problems)
    make_model = _make_model(s.asset.make, s.asset.model)
    return {
        "assetId": str(s.asset.id),
        "version": s.asset.version,
        "tag": s.asset.asset_tag,
        "itemTypeId": str(s.item_type.id),
        "itemType": s.item_type.name,
        "category": s.item_type.category.value,
        "categoryLabel": CATEGORY_LABELS[s.item_type.category],
        "serial": s.asset.serial_number or "",
        "makeModel": make_model,
        "site": s.home_site.name if s.home_site else "",
        "serviceKind": service_kind,
        "serviceLabel": service_label,
        "custody": s.status.custody.value,
        "custodyLabel": CUSTODY[s.status.custody],
        "meters": _meters_text(s.meters),
        "kitCode": s.kit_code or "",
        "complianceKind": compliance_kind,
        "complianceText": compliance_text,
        "search": " ".join(
            [s.asset.asset_tag, s.item_type.name, s.asset.serial_number or "", make_model]
        ).lower(),
    }


def available_actions(status: AssetStatus, permissions: frozenset[str]) -> list[dict[str, Any]]:
    """Status changes that are both allowed by the rules and by the person's role."""
    actions: list[dict[str, Any]] = []
    for key, label, change, needs_reason in STATUS_ACTIONS:
        try:
            apply_change(status, change)
        except DomainError:
            continue
        if all(p.value in permissions for p in required_permissions(status, change)):
            actions.append({"key": key, "label": label, "needsReason": needs_reason})
    return actions


class EquipmentViewModel(QObject):
    changed = Signal()
    detailChanged = Signal()  # noqa: N815
    saved = Signal(str)

    def __init__(
        self,
        session: SessionViewModel,
        services: Services,
        tasks: TaskQueue,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._sv = services
        self._tasks = tasks
        self._model = DictListModel(_ROLES, self)
        self._all: list[dict[str, Any]] = []
        self._visible: list[dict[str, Any]] = []
        self._search = ""
        self._category = ""
        self._attention_only = False
        self._error = ""
        self._detail: dict[str, Any] = {}
        self._detail_id: AssetId | None = None
        self._types: list[ItemType] = []
        self._sites: list[dict[str, str]] = []
        session.signedIn.connect(self._on_signed_in)

    # ------------------------------------------------------------------ properties

    def _model_get(self) -> DictListModel:
        return self._model

    def _error_get(self) -> str:
        return self._error

    def _count_get(self) -> int:
        return self._model.rowCount()

    def _total_get(self) -> int:
        return len(self._all)

    def _attention_get(self) -> int:
        return sum(1 for r in self._all if r["complianceKind"])

    def _detail_get(self) -> dict[str, Any]:
        return self._detail

    def _can_manage_get(self) -> bool:
        return self._session.can("asset.manage")

    def _can_maintain_get(self) -> bool:
        return self._session.can("maintenance.manage")

    def _category_get(self) -> str:
        return self._category

    def _attention_only_get(self) -> bool:
        return self._attention_only

    model = Property(QObject, _model_get, constant=True)
    error = Property(str, _error_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    total = Property(int, _total_get, notify=changed)
    attentionCount = Property(int, _attention_get, notify=changed)  # noqa: N815
    detail = Property(dict, _detail_get, notify=detailChanged)
    canManage = Property(bool, _can_manage_get, notify=changed)  # noqa: N815
    canMaintain = Property(bool, _can_maintain_get, notify=changed)  # noqa: N815
    category = Property(str, _category_get, notify=changed)
    attentionOnly = Property(bool, _attention_only_get, notify=changed)  # noqa: N815

    # Options for drop-downs; they update when the catalogue and sites have loaded.
    def _category_options_get(self) -> list[dict[str, str]]:
        return self.categories()

    def _type_options_get(self) -> list[dict[str, Any]]:
        return self.itemTypes()

    def _site_options_get(self) -> list[dict[str, str]]:
        return self.sites()

    categoryOptions = Property(list, _category_options_get, notify=changed)  # noqa: N815
    itemTypeOptions = Property(list, _type_options_get, notify=changed)  # noqa: N815
    siteOptions = Property(list, _site_options_get, notify=changed)  # noqa: N815

    # ------------------------------------------------------------------ plumbing

    def _fail(self, exc: BaseException) -> None:
        self._error = describe_error(exc)
        self.changed.emit()

    def _run(self, work: Callable[[], Any], message: str, *, reopen: bool = True) -> None:
        self._error = ""
        self.changed.emit()

        def done(_: Any) -> None:
            if message:
                self.saved.emit(message)
            self.refresh()
            if reopen and self._detail_id is not None:
                self.openAsset(str(self._detail_id))

        self._tasks.submit(work, done, self._fail)

    def _apply_filter(self) -> None:
        needle = self._search.strip().lower()
        rows = [
            r
            for r in self._all
            if (not self._category or r["category"] == self._category)
            and (not self._attention_only or r["complianceKind"])
            and (not needle or needle in r["search"])
        ]
        self._visible = rows
        self._model.reset(rows)
        self.changed.emit()

    def _on_signed_in(self) -> None:
        if self._session.can("asset.manage"):
            # Standard catalogue and kit templates; both installs are idempotent.
            def install() -> None:
                self._sv.catalogue.install_defaults(self._session.context())
                self._sv.kits.install_default_templates(self._session.context())

            self._tasks.submit(install, lambda _: self.refresh(), self._fail)
        else:
            self.refresh()

    # ------------------------------------------------------------------ list

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("asset.view"):
            return
        actor = self._session.actor()

        def work() -> tuple[list[dict[str, Any]], list[ItemType], list[dict[str, str]]]:
            rows = [_row(s) for s in self._sv.registry.summaries(actor)]
            types = self._sv.catalogue.list_item_types(actor)
            sites = [
                {"value": str(s.id), "label": s.label} for s in self._sv.sites.list_sites(actor)
            ]
            return sorted(rows, key=lambda r: r["tag"]), types, sites

        def done(result: tuple[list[dict[str, Any]], list[ItemType], list[dict[str, str]]]) -> None:
            self._all, self._types, self._sites = result
            self._apply_filter()

        self._tasks.submit(work, done, self._fail)

    @Slot(str)
    def setSearch(self, value: str) -> None:  # noqa: N802
        self._search = value
        self._apply_filter()

    @Slot(str)
    def setCategory(self, value: str) -> None:  # noqa: N802
        self._category = value
        self._apply_filter()

    @Slot(bool)
    def setAttentionOnly(self, value: bool) -> None:  # noqa: N802
        self._attention_only = value
        self._apply_filter()

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    @Slot(result=list)
    def categories(self) -> list[dict[str, str]]:
        present = {t.category for t in self._types}
        return [{"value": "", "label": "All equipment"}] + [
            {"value": c.value, "label": label}
            for c, label in CATEGORY_LABELS.items()
            if c in present and c is not Category.CONSUMABLE
        ]

    @Slot(result=list)
    def itemTypes(self) -> list[dict[str, Any]]:  # noqa: N802
        """Individually tracked item types for the register form."""
        return [
            {
                "value": str(t.id),
                "label": f"{t.name}  ·  {CATEGORY_LABELS[t.category]}",
                "serialized": t.tracking is TrackingMode.SERIALIZED,
                "warranty": t.tracks_warranty,
                "meters": [m.value for m in sorted(t.meters)],
            }
            for t in sorted(self._types, key=lambda t: (list(Category).index(t.category), t.name))
            if t.is_individually_tracked
        ]

    @Slot(result=list)
    def sites(self) -> list[dict[str, str]]:
        return [{"value": "", "label": "No home site"}, *self._sites]

    @Slot(str, result=str)
    def suggestTag(self, item_type_id: str) -> str:  # noqa: N802
        if not item_type_id:
            return ""
        try:
            return self._sv.assets.suggest_tag(
                self._session.actor(), ItemTypeId(uuid.UUID(item_type_id))
            )
        except DomainError:
            return ""

    # ------------------------------------------------------------------ register & edit

    @Slot(dict)
    def register(self, values: dict[str, Any]) -> None:
        fields = values.copy()

        def work() -> None:
            meters: dict[Meter, Decimal] = {}
            for meter in Meter:
                amount = optional_decimal(fields, meter.value, METER_LABELS[meter])
                if amount:
                    meters[meter] = amount
            site = text(fields, "homeSiteId")
            self._sv.assets.register(
                self._session.context(),
                item_type_id=ItemTypeId(uuid.UUID(text(fields, "itemTypeId"))),
                asset_tag=text(fields, "tag"),
                serial_number=text(fields, "serial") or None,
                make=text(fields, "make") or None,
                model=text(fields, "model") or None,
                acquired_on=optional_date(fields, "acquiredOn"),
                warranty_until=optional_date(fields, "warrantyUntil"),
                home_site_id=LocationId(uuid.UUID(site)) if site else None,
                notes=text(fields, "notes"),
                opening_balances=meters,
            )

        if not text(fields, "itemTypeId"):
            self._fail(RuleViolation("Choose what kind of equipment this is."))
            return
        self._run(work, f"{text(fields, 'tag').upper()} registered", reopen=False)

    @Slot(str, int, dict)
    def update(self, asset_id: str, version: int, values: dict[str, Any]) -> None:
        fields = values.copy()

        def work() -> None:
            site = text(fields, "homeSiteId")
            self._sv.assets.update(
                self._session.context(),
                AssetId(uuid.UUID(asset_id)),
                version,
                asset_tag=text(fields, "tag"),
                serial_number=text(fields, "serial") or None,
                make=text(fields, "make") or None,
                model=text(fields, "model") or None,
                acquired_on=optional_date(fields, "acquiredOn"),
                warranty_until=optional_date(fields, "warrantyUntil"),
                home_site_id=LocationId(uuid.UUID(site)) if site else None,
                notes=text(fields, "notes"),
            )

        self._run(work, "Saved")

    # ------------------------------------------------------------------ detail

    @Slot(str)
    def openAsset(self, asset_id: str) -> None:  # noqa: N802
        self._detail_id = AssetId(uuid.UUID(asset_id))
        actor = self._session.actor()
        permissions = frozenset(self._session.permission_codes())

        def work() -> dict[str, Any]:
            overview = self._sv.registry.overview(actor, AssetId(uuid.UUID(asset_id)))
            maintenance = self._maintenance(actor, AssetId(uuid.UUID(asset_id)))
            loose = (
                self._sv.registry.loose_components(actor)
                if overview.item_type.category is Category.DRONE
                else []
            )
            detail = self._detail_dict(overview, permissions, loose)
            detail["maintenance"] = maintenance
            return detail

        def done(detail: dict[str, Any]) -> None:
            self._detail = detail
            self.detailChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot()
    def reloadAsset(self) -> None:  # noqa: N802
        """Re-reads the open asset (after maintenance changed it elsewhere)."""
        if self._detail_id is not None:
            self.openAsset(str(self._detail_id))

    def _maintenance(self, actor: Any, asset_id: AssetId) -> dict[str, Any]:
        tasks = [due_row(d) for d in self._sv.maintenance.asset_due(actor, asset_id)]
        defects = [
            {"number": d.number, "description": d.description,
             "stateKind": DEFECT_LABELS[d.state][0], "stateLabel": DEFECT_LABELS[d.state][1],
             "limitation": d.limitation,
             "deferredUntil": f"{d.deferred_until:%d %b %Y}" if d.deferred_until else ""}
            for d in self._sv.maintenance.defects(actor)
            if d.asset_id == asset_id and d.is_open
        ]  # fmt: skip
        order = next(
            (
                w
                for w in self._sv.maintenance.work_orders(actor)
                if w.asset_id == asset_id and w.is_open
            ),
            None,
        )
        return {
            "tasks": tasks,
            "defects": defects,
            "grounding": self._sv.maintenance.grounding_reasons(actor, asset_id),
            "workOrderId": str(order.id) if order else "",
            "workOrder": f"{order.number} · {order.title}" if order else "",
        }

    @Slot()
    def closeAsset(self) -> None:  # noqa: N802
        self._detail_id = None
        self._detail = {}
        self.detailChanged.emit()

    def _detail_dict(
        self, o: AssetOverview, permissions: frozenset[str], loose: list[tuple[Any, ItemType]]
    ) -> dict[str, Any]:
        service_kind, service_label = SERVICEABILITY[o.status.serviceability]
        return {
            "assetId": str(o.asset.id),
            "version": o.asset.version,
            "tag": o.asset.asset_tag,
            "itemTypeId": str(o.item_type.id),
            "itemType": o.item_type.name,
            "categoryLabel": CATEGORY_LABELS[o.item_type.category],
            "isDrone": o.item_type.category is Category.DRONE,
            "isComponent": o.item_type.is_component,
            "serial": o.asset.serial_number or "",
            "make": o.asset.make or "",
            "model": o.asset.model or "",
            "acquiredOn": o.asset.acquired_on.isoformat() if o.asset.acquired_on else "",
            "warrantyUntil": o.asset.warranty_until.isoformat() if o.asset.warranty_until else "",
            "tracksWarranty": o.item_type.tracks_warranty,
            "homeSiteId": str(o.asset.home_site_id) if o.asset.home_site_id else "",
            "site": o.home_site.label if o.home_site else "",
            "notes": o.asset.notes,
            "serviceKind": service_kind,
            "serviceLabel": service_label,
            "custodyLabel": CUSTODY[o.status.custody],
            "meters": [
                {
                    "label": METER_LABELS[m],
                    "value": f"{v:,.1f}" if m is Meter.HOURS else f"{v:,.0f}",
                }
                for m, v in sorted(o.meters.items())
            ],
            "installedOn": (
                {
                    "tag": o.installed_on[0].asset_tag,
                    "assetId": str(o.installed_on[0].id),
                    "position": o.installed_on[1],
                }
                if o.installed_on
                else {}
            ),
            "components": [
                {
                    "assetId": str(c.asset.id),
                    "tag": c.asset.asset_tag,
                    "itemType": c.item_type.name,
                    "position": c.position or "—",
                }
                for c in o.components
            ],
            "looseComponents": [
                {"value": str(a.id), "label": f"{a.asset_tag} · {t.name}"} for a, t in loose
            ],
            "documents": [
                {
                    "documentId": str(d.id),
                    "version": d.version,
                    "kind": d.kind.value,
                    "kindLabel": DOCUMENT_LABELS[d.kind],
                    "reference": d.reference,
                    "issuer": d.issuer,
                    "validUntil": d.valid_until.strftime("%d %b %Y") if d.valid_until else "",
                    "statusKind": DOC_STATUS[status][0],
                    "statusLabel": DOC_STATUS[status][1],
                    "hasFile": d.file is not None,
                }
                for d, status in o.documents
            ],
            "problems": [{"kind": k, "text": t} for k, t in o.problems],
            "firmware": [
                {
                    "version": f.version,
                    "installedOn": f.installed_on.strftime("%d %b %Y"),
                    "note": f.note,
                }
                for f in reversed(o.firmware)
            ],
            "kitCode": o.kit.code if o.kit else "",
            "history": [
                {
                    "when": local_time(e.recorded_at),
                    "from": _status_text(e.before),
                    "to": _status_text(e.after),
                    "reason": e.reason,
                }
                for e in reversed(o.history)
            ],
            "actions": available_actions(o.status, permissions),
            "documentKinds": [
                {"value": k.value, "label": DOCUMENT_LABELS[k]} for k in allowed_kinds(o.item_type)
            ],
        }

    # ------------------------------------------------------------------ actions on one asset

    @Slot(str, str, str)
    def changeStatus(self, asset_id: str, action: str, reason: str) -> None:  # noqa: N802
        """Applies one of ``STATUS_ACTIONS`` (ground, return to service, retire ...)."""
        found = next((a for a in STATUS_ACTIONS if a[0] == action), None)
        if found is None:
            return
        _, label, template, needs_reason = found
        if needs_reason and not reason.strip():
            self._fail(RuleViolation("Give a reason for this change."))
            return
        change = StatusChange(
            serviceability=template.serviceability, custody=template.custody, reason=reason.strip()
        )
        self._run(
            lambda: self._sv.assets.change_status(
                self._session.context(), AssetId(uuid.UUID(asset_id)), change
            ),
            f"{label}: done",
        )

    @Slot(str, str, str)
    def installComponent(self, parent_id: str, component_id: str, position: str) -> None:  # noqa: N802
        if not component_id:
            self._fail(RuleViolation("Choose the part to fit."))
            return
        self._run(
            lambda: self._sv.registry.install(
                self._session.context(),
                AssetId(uuid.UUID(component_id)),
                AssetId(uuid.UUID(parent_id)),
                position,
            ),
            "Part fitted",
        )

    @Slot(str, str)
    def removeComponent(self, component_id: str, note: str) -> None:  # noqa: N802
        self._run(
            lambda: self._sv.registry.remove(
                self._session.context(), AssetId(uuid.UUID(component_id)), note
            ),
            "Part removed",
        )

    @Slot(str, dict, str)
    def addDocument(self, asset_id: str, values: dict[str, Any], file_url: str) -> None:  # noqa: N802
        fields = values.copy()

        def work() -> None:
            content = Path(local_path(file_url)).read_bytes() if file_url else None
            self._sv.registry.add_document(
                self._session.context(),
                AssetId(uuid.UUID(asset_id)),
                kind=DocumentKind(text(fields, "kind") or DocumentKind.OTHER.value),
                reference=text(fields, "reference"),
                issuer=text(fields, "issuer"),
                issued_on=optional_date(fields, "issuedOn"),
                valid_until=optional_date(fields, "validUntil"),
                notes=text(fields, "notes"),
                file_content=content,
            )

        self._run(work, "Document added")

    @Slot(str, int)
    def removeDocument(self, document_id: str, version: int) -> None:  # noqa: N802
        self._run(
            lambda: self._sv.registry.remove_document(
                self._session.context(), DocumentId(uuid.UUID(document_id)), version
            ),
            "Document removed",
        )

    @Slot(str, str, str, str)
    def recordFirmware(self, asset_id: str, version: str, installed_on: str, note: str) -> None:  # noqa: N802
        def work() -> None:
            day = optional_date({"d": installed_on}, "d")
            if day is None:
                raise RuleViolation("Choose the date the firmware was installed.")
            self._sv.registry.record_firmware(
                self._session.context(), AssetId(uuid.UUID(asset_id)), version, day, note
            )

        self._run(work, "Firmware recorded")

    # ------------------------------------------------------------------ labels

    @Slot(list, str, int)
    def printLabels(self, asset_ids: list[str], save_url: str, start_position: int) -> None:  # noqa: N802
        """Writes a PDF label sheet for the given assets (all listed ones if empty) and opens it."""
        wanted = set(asset_ids)
        rows = [r for r in self._visible if not wanted or r["assetId"] in wanted]
        path = Path(local_path(save_url))
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")

        def work() -> Path:
            write_label_sheet(
                [Label(r["tag"], _label_title(r), r["serial"]) for r in rows],
                path,
                start_position=max(0, start_position),
            )
            return path

        def done(written: Path) -> None:
            self.saved.emit(f"{len(rows)} labels saved")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(written)))

        if not rows:
            self._fail(RuleViolation("There are no assets to print labels for."))
            return
        self._tasks.submit(work, done, self._fail)
