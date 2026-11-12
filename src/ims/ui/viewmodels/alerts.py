"""The alert centre behind the bell in the toolbar."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from ims.ui.app_services import Services
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import describe_error
from ims.ui.viewmodels.session import SessionViewModel

CATEGORY_LABELS = {
    "maintenance": "Maintenance",
    "defect": "Defects",
    "battery": "Batteries",
    "calibration": "Calibration",
    "document": "Documents",
    "licence": "Pilot certificates",
    "stock": "GCP stock",
    "reservation": "Reservations",
}
CATEGORY_ICONS = {
    "maintenance": "wrench",
    "defect": "alert",
    "battery": "battery",
    "calibration": "satellite",
    "document": "layers",
    "licence": "user",
    "stock": "flag",
    "reservation": "calendar",
}


class AlertsViewModel(QObject):
    changed = Signal()

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
        self._alerts: list[dict[str, Any]] = []
        self._error = ""
        # Many saves can arrive together; refresh once after they settle.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self.refresh)
        session.signedIn.connect(self.refresh)
        session.signedOut.connect(self._clear)

    def _alerts_get(self) -> list[dict[str, Any]]:
        return list(self._alerts)

    def _count_get(self) -> int:
        return sum(1 for a in self._alerts if a["severity"] in {"danger", "warning"})

    def _urgent_get(self) -> int:
        return sum(1 for a in self._alerts if a["severity"] == "danger")

    def _groups_get(self) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for alert in self._alerts:
            groups.setdefault(alert["category"], []).append(alert)
        order = list(CATEGORY_LABELS)
        return [
            {"category": c, "label": CATEGORY_LABELS[c], "icon": CATEGORY_ICONS[c], "alerts": items}
            for c, items in sorted(
                groups.items(),
                key=lambda kv: (
                    min({"danger": 0, "warning": 1, "info": 2}[a["severity"]] for a in kv[1]),
                    order.index(kv[0]),
                ),
            )
        ]

    def _error_get(self) -> str:
        return self._error

    alerts = Property(list, _alerts_get, notify=changed)
    groups = Property(list, _groups_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    urgentCount = Property(int, _urgent_get, notify=changed)  # noqa: N815
    error = Property(str, _error_get, notify=changed)

    def _clear(self) -> None:
        self._alerts = []
        self.changed.emit()

    @Slot()
    def refreshSoon(self) -> None:  # noqa: N802
        self._debounce.start()

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("asset.view"):
            return
        actor = self._session.actor()

        def work() -> list[dict[str, Any]]:
            return [
                {
                    "severity": a.severity,
                    "category": a.category,
                    "title": a.title,
                    "message": a.message,
                    "section": a.section,
                    "assetId": a.asset_id,
                }
                for a in self._sv.alerts.alerts(actor)
            ]

        def done(alerts: list[dict[str, Any]]) -> None:
            self._alerts = alerts
            self._error = ""
            self.changed.emit()

        def failed(exc: BaseException) -> None:
            self._error = describe_error(exc)
            self.changed.emit()

        self._tasks.submit(work, done, failed)
