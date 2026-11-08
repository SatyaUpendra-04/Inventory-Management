"""Sites: stores, mine sites, workshops and offices."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.application.sites import SiteService
from ims.domain.common.ids import LocationId
from ims.domain.sites.site import Site, SiteKind, SiteStatus
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import describe_error, optional_decimal, text
from ims.ui.viewmodels.session import SessionViewModel

KIND_LABELS = {
    SiteKind.STORE: "Store",
    SiteKind.MINE_SITE: "Mine site",
    SiteKind.WORKSHOP: "Workshop",
    SiteKind.OFFICE: "Office",
}
STATUS_LABELS = {
    SiteStatus.ACTIVE: ("success", "Active"),
    SiteStatus.PLANNED: ("info", "Planned"),
    SiteStatus.INACTIVE: ("neutral", "Inactive"),
}


def _row(site: Site) -> dict[str, Any]:
    status_kind, status_label = STATUS_LABELS[site.status]
    coordinates = (
        f"{site.latitude:.4f}, {site.longitude:.4f}"
        if site.latitude is not None and site.longitude is not None
        else ""
    )
    return {
        "siteId": str(site.id),
        "version": site.version,
        "code": site.code,
        "name": site.name,
        "kind": site.kind.value,
        "kindLabel": KIND_LABELS[site.kind],
        "region": site.region,
        "latitude": "" if site.latitude is None else str(site.latitude),
        "longitude": "" if site.longitude is None else str(site.longitude),
        "coordinates": coordinates,
        "area": "" if site.area_hectares is None else str(site.area_hectares),
        "mineral": site.mineral,
        "status": site.status.value,
        "statusKind": status_kind,
        "statusLabel": status_label,
        "notes": site.notes,
    }


_SITE_ROLES = (
    "siteId", "version", "code", "name", "kind", "kindLabel", "region", "latitude", "longitude",
    "coordinates", "area", "mineral", "status", "statusKind", "statusLabel", "notes",
)  # fmt: skip


def _fields(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": text(values, "code"),
        "name": text(values, "name"),
        "kind": SiteKind(text(values, "kind") or SiteKind.STORE.value),
        "region": text(values, "region"),
        "latitude": optional_decimal(values, "latitude", "Latitude"),
        "longitude": optional_decimal(values, "longitude", "Longitude"),
        "area_hectares": optional_decimal(values, "area", "Area"),
        "mineral": text(values, "mineral"),
        "status": SiteStatus(text(values, "status") or SiteStatus.ACTIVE.value),
        "notes": text(values, "notes"),
    }


class SitesViewModel(QObject):
    changed = Signal()
    saved = Signal(str)

    def __init__(
        self,
        session: SessionViewModel,
        sites: SiteService,
        tasks: TaskQueue,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._sites = sites
        self._tasks = tasks
        self._model = DictListModel(_SITE_ROLES, self)
        self._error = ""
        session.signedIn.connect(self.refresh)

    def _model_get(self) -> DictListModel:
        return self._model

    def _error_get(self) -> str:
        return self._error

    def _count_get(self) -> int:
        return self._model.rowCount()

    def _can_manage_get(self) -> bool:
        return self._session.can("site.manage")

    model = Property(QObject, _model_get, constant=True)
    error = Property(str, _error_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    canManage = Property(bool, _can_manage_get, notify=changed)  # noqa: N815

    def _run(self, work: Callable[[], Any], message: str) -> None:
        self._error = ""
        self.changed.emit()

        def done(_: Any) -> None:
            self.saved.emit(message)
            self.refresh()

        def failed(exc: BaseException) -> None:
            self._error = describe_error(exc)
            self.changed.emit()

        self._tasks.submit(work, done, failed)

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("site.view"):
            return

        def done(rows: list[dict[str, Any]]) -> None:
            self._model.reset(rows)
            self.changed.emit()

        actor = self._session.actor()
        self._tasks.submit(
            lambda: [_row(s) for s in self._sites.list_sites(actor)],
            done,
            lambda exc: self._fail(exc),
        )

    def _fail(self, exc: BaseException) -> None:
        self._error = describe_error(exc)
        self.changed.emit()

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    @Slot(str, result=dict)
    def site(self, site_id: str) -> dict[str, Any]:
        return self._model.find("siteId", site_id)

    @Slot(dict)
    def create(self, values: dict[str, Any]) -> None:
        fields = values.copy()
        self._run(
            lambda: self._sites.create(self._session.context(), **_fields(fields)), "Site added"
        )

    @Slot(str, int, dict)
    def update(self, site_id: str, version: int, values: dict[str, Any]) -> None:
        fields = values.copy()
        self._run(
            lambda: self._sites.update(
                self._session.context(), LocationId(uuid.UUID(site_id)), version, **_fields(fields)
            ),
            "Site saved",
        )

    @Slot(str, int)
    def remove(self, site_id: str, version: int) -> None:
        self._run(
            lambda: self._sites.delete(
                self._session.context(), LocationId(uuid.UUID(site_id)), version
            ),
            "Site removed",
        )

    @Slot(result=list)
    def kinds(self) -> list[dict[str, str]]:
        return [{"value": k.value, "label": label} for k, label in KIND_LABELS.items()]

    @Slot(result=list)
    def statuses(self) -> list[dict[str, str]]:
        return [{"value": s.value, "label": label} for s, (_, label) in STATUS_LABELS.items()]
