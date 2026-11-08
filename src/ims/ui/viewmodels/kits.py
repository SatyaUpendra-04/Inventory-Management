"""Kits: named sets of equipment, checked against their templates."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.application.kits import KitOverview
from ims.domain.assets.status import Serviceability
from ims.domain.common.ids import AssetId, KitId, KitTemplateId, LocationId
from ims.ui.app_services import Services
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import describe_error, text
from ims.ui.viewmodels.session import SessionViewModel

_ROLES = (
    "kitId",
    "version",
    "code",
    "name",
    "templateName",
    "site",
    "memberCount",
    "statusKind",
    "statusLabel",
)


class KitsViewModel(QObject):
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
        self._error = ""
        self._detail: dict[str, Any] = {}
        self._detail_id: KitId | None = None
        self._names: dict[uuid.UUID, str] = {}
        session.signedIn.connect(self.refresh)

    def _model_get(self) -> DictListModel:
        return self._model

    def _error_get(self) -> str:
        return self._error

    def _count_get(self) -> int:
        return self._model.rowCount()

    def _detail_get(self) -> dict[str, Any]:
        return self._detail

    def _can_manage_get(self) -> bool:
        return self._session.can("asset.manage")

    model = Property(QObject, _model_get, constant=True)
    error = Property(str, _error_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    detail = Property(dict, _detail_get, notify=detailChanged)
    canManage = Property(bool, _can_manage_get, notify=changed)  # noqa: N815

    # ------------------------------------------------------------------ helpers

    def _fail(self, exc: BaseException) -> None:
        self._error = describe_error(exc)
        self.changed.emit()

    def _run(self, work: Callable[[], Any], message: str) -> None:
        self._error = ""
        self.changed.emit()

        def done(_: Any) -> None:
            self.saved.emit(message)
            self.refresh()
            if self._detail_id is not None:
                self.openKit(str(self._detail_id))

        self._tasks.submit(work, done, self._fail)

    def _status(self, overview: KitOverview) -> tuple[str, str]:
        if overview.completeness is None:
            return "info", "No template"
        missing = sum(overview.completeness.missing.values())
        return ("success", "Complete") if missing == 0 else ("warning", f"{missing} missing")

    def _row(self, overview: KitOverview, sites: Mapping[LocationId, str]) -> dict[str, Any]:
        kind, label = self._status(overview)
        kit = overview.kit
        return {
            "kitId": str(kit.id),
            "version": kit.version,
            "code": kit.code,
            "name": kit.name,
            "templateName": overview.template.name if overview.template else "",
            "site": sites.get(kit.home_site_id, "") if kit.home_site_id else "",
            "memberCount": len(overview.members),
            "statusKind": kind,
            "statusLabel": label,
        }

    # ------------------------------------------------------------------ slots

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("asset.view"):
            return
        actor = self._session.actor()

        def work() -> list[dict[str, Any]]:
            sites = {s.id: s.label for s in self._sv.sites.list_sites(actor)}
            self._names = {t.id: t.name for t in self._sv.catalogue.list_item_types(actor)}
            return [self._row(k, sites) for k in self._sv.kits.list_kits(actor)]

        def done(rows: list[dict[str, Any]]) -> None:
            self._model.reset(rows)
            self.changed.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    @Slot(result=list)
    def templates(self) -> list[dict[str, str]]:
        templates = self._sv.kits.templates(self._session.actor())
        return [{"value": "", "label": "No template"}] + [
            {"value": str(t.id), "label": t.name} for t in templates
        ]

    @Slot(str)
    def openKit(self, kit_id: str) -> None:  # noqa: N802
        self._detail_id = KitId(uuid.UUID(kit_id))
        actor = self._session.actor()

        def work() -> dict[str, Any]:
            overview = self._sv.kits.get(actor, KitId(uuid.UUID(kit_id)))
            kind, label = self._status(overview)
            names = self._names or {t.id: t.name for t in self._sv.catalogue.list_item_types(actor)}
            members = {m.id for m in overview.members}
            candidates = [
                {"value": str(s.asset.id), "label": f"{s.asset.asset_tag} · {s.item_type.name}"}
                for s in self._sv.registry.summaries(actor)
                if s.asset.id not in members
                and s.kit_code is None
                and s.status.serviceability is not Serviceability.RETIRED
            ]
            missing = overview.completeness.missing if overview.completeness else {}
            return {
                "kitId": str(overview.kit.id),
                "version": overview.kit.version,
                "code": overview.kit.code,
                "name": overview.kit.name,
                "templateName": overview.template.name if overview.template else "",
                "statusKind": kind,
                "statusLabel": label,
                "members": [
                    {
                        "assetId": str(m.id),
                        "tag": m.asset_tag,
                        "itemType": names.get(m.item_type_id, ""),
                    }
                    for m in overview.members
                ],
                "missing": [f"{n} x {names.get(t, '?')}" for t, n in missing.items()],
                "candidates": candidates,
            }

        def done(detail: dict[str, Any]) -> None:
            self._detail = detail
            self.detailChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot(dict)
    def create(self, values: dict[str, Any]) -> None:
        fields = values.copy()

        def work() -> None:
            template = text(fields, "templateId")
            site = text(fields, "homeSiteId")
            self._sv.kits.create(
                self._session.context(),
                code=text(fields, "code"),
                name=text(fields, "name"),
                template_id=KitTemplateId(uuid.UUID(template)) if template else None,
                home_site_id=LocationId(uuid.UUID(site)) if site else None,
                notes=text(fields, "notes"),
            )

        self._run(work, "Kit created")

    @Slot(str, int, str)
    def addMember(self, kit_id: str, version: int, asset_id: str) -> None:  # noqa: N802
        if not asset_id:
            return
        self._run(
            lambda: self._sv.kits.add_member(
                self._session.context(),
                KitId(uuid.UUID(kit_id)),
                version,
                AssetId(uuid.UUID(asset_id)),
            ),
            "Added to kit",
        )

    @Slot(str, int, str)
    def removeMember(self, kit_id: str, version: int, asset_id: str) -> None:  # noqa: N802
        self._run(
            lambda: self._sv.kits.remove_member(
                self._session.context(),
                KitId(uuid.UUID(kit_id)),
                version,
                AssetId(uuid.UUID(asset_id)),
            ),
            "Removed from kit",
        )

    @Slot(str, int)
    def breakUp(self, kit_id: str, version: int) -> None:  # noqa: N802
        def work() -> None:
            self._sv.kits.delete(self._session.context(), KitId(uuid.UUID(kit_id)), version)
            self._detail_id = None

        self._run(work, "Kit broken up")
