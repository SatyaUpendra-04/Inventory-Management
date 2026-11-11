"""GCP banner stock: quantities per site, reorder levels, receipts, write-offs and counts."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.domain.assets.catalogue import TrackingMode, default_item_type_id
from ims.domain.common.errors import DomainError, RuleViolation
from ims.domain.common.ids import ItemTypeId, LocationId
from ims.domain.stock.ledger import MovementKind
from ims.ui.app_services import Services
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import describe_error, local_time
from ims.ui.viewmodels.session import SessionViewModel

GCP_BANNER = default_item_type_id("GCP_BANNER")
KIND_LABELS = {
    MovementKind.RECEIVED: "Received",
    MovementKind.ISSUED: "Issued to project",
    MovementKind.RETURNED: "Returned from project",
    MovementKind.CONSUMED: "Used on project",
    MovementKind.WRITTEN_OFF: "Written off",
    MovementKind.ADJUSTED: "Count adjustment",
}
_SITE_ROLES = ("siteId", "site", "onHand", "booked", "free", "level", "statusKind", "statusLabel")
_MOVE_ROLES = ("when", "kind", "site", "quantity", "reason", "by")


class StockViewModel(QObject):
    changed = Signal()
    saved = Signal(str)
    varianceChanged = Signal()  # noqa: N815

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
        self._sites = DictListModel(_SITE_ROLES, self)
        self._moves = DictListModel(_MOVE_ROLES, self)
        self._item_type: ItemTypeId = ItemTypeId(GCP_BANNER)
        self._item_name = "GCP banner"
        self._total = 0
        self._low = 0
        self._error = ""
        self._site_choices: list[dict[str, str]] = []
        self._variance: list[dict[str, Any]] = []
        session.signedIn.connect(self.refresh)

    def _sites_get(self) -> DictListModel:
        return self._sites

    def _moves_get(self) -> DictListModel:
        return self._moves

    def _total_get(self) -> int:
        return self._total

    def _low_get(self) -> int:
        return self._low

    def _error_get(self) -> str:
        return self._error

    def _name_get(self) -> str:
        return self._item_name

    def _can_manage_get(self) -> bool:
        return self._session.can("stock.manage")

    def _variance_get(self) -> list[dict[str, Any]]:
        return list(self._variance)

    variance = Property(list, _variance_get, notify=varianceChanged)
    sites = Property(QObject, _sites_get, constant=True)
    movements = Property(QObject, _moves_get, constant=True)
    total = Property(int, _total_get, notify=changed)
    lowCount = Property(int, _low_get, notify=changed)  # noqa: N815
    error = Property(str, _error_get, notify=changed)
    itemName = Property(str, _name_get, notify=changed)  # noqa: N815
    canManage = Property(bool, _can_manage_get, notify=changed)  # noqa: N815

    def _fail(self, exc: BaseException) -> None:
        self._error = describe_error(exc)
        self.changed.emit()

    def _run(self, work: Callable[[], Any], message: str) -> None:
        self._error = ""
        self.changed.emit()

        def done(_: Any) -> None:
            self.saved.emit(message)
            self.refresh()

        self._tasks.submit(work, done, self._fail)

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("stock.view"):
            return
        actor = self._session.actor()

        def work() -> dict[str, Any]:
            sites = {s.id: s for s in self._sv.sites.list_sites(actor, include_deleted=True)}
            item_type = next(
                (
                    t
                    for t in self._sv.catalogue.list_item_types(actor)
                    if t.tracking is TrackingMode.CONSUMABLE and t.id == self._item_type
                ),
                None,
            )
            users: dict[Any, str] = {}
            booked = self._sv.reservations.gcp_booked(actor)
            rows = []
            for row in self._sv.stock.by_site(actor, self._item_type):
                site = sites.get(row.location_id)
                kind, label = ("danger", "Reorder") if row.low else ("success", "OK")
                free = row.on_hand - booked.get(row.location_id, 0)
                if not row.low and row.reorder_level is not None and free <= row.reorder_level:
                    # Enough on the shelf today, but promised banners will take it under.
                    kind, label = "warning", "Bookings go below level"
                if row.reorder_level is None:
                    kind, label = "neutral", "No level set"
                rows.append(
                    {
                        "siteId": str(row.location_id),
                        "site": site.label if site else "Unknown site",
                        "onHand": row.on_hand,
                        "booked": booked.get(row.location_id, 0),
                        "free": row.on_hand - booked.get(row.location_id, 0),
                        "level": "" if row.reorder_level is None else str(row.reorder_level),
                        "statusKind": kind,
                        "statusLabel": label,
                    }
                )
            moves = []
            for m in reversed(self._sv.stock.movements(actor, self._item_type)[-50:]):
                site = sites.get(m.location_id)
                if m.recorded_by not in users:
                    try:
                        users[m.recorded_by] = self._sv.users.get(actor, m.recorded_by).full_name
                    except DomainError:  # crew cannot look up other people; show no name
                        users[m.recorded_by] = ""
                # Store movements show the signed change in the store; project ones the count.
                quantity = f"{m.store_delta:+d}" if m.store_delta else str(m.quantity)
                moves.append(
                    {
                        "when": local_time(m.recorded_at),
                        "kind": KIND_LABELS[m.kind],
                        "site": site.code if site else "",
                        "quantity": quantity,
                        "reason": m.reason,
                        "by": users[m.recorded_by],
                    }
                )
            choices = [
                {"value": str(s.id), "label": s.label} for s in sites.values() if not s.is_deleted
            ]
            return {
                "name": item_type.name if item_type else "GCP banner",
                "rows": rows,
                "moves": moves,
                "choices": sorted(choices, key=lambda c: c["label"]),
            }

        def done(result: dict[str, Any]) -> None:
            self._item_name = result["name"]
            self._sites.reset(result["rows"])
            self._moves.reset(result["moves"])
            self._total = sum(r["onHand"] for r in result["rows"])
            self._low = sum(1 for r in result["rows"] if r["statusKind"] == "danger")
            self._site_choices = result["choices"]
            self.changed.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    @Slot(result=list)
    def siteChoices(self) -> list[dict[str, str]]:  # noqa: N802
        return list(self._site_choices)

    def _quantity(self, raw: str) -> int:
        try:
            value = int(str(raw).strip())
        except ValueError as exc:
            raise RuleViolation("Enter a whole number.") from exc
        return value

    @Slot(str, str, str)
    def receive(self, site_id: str, quantity: str, reason: str) -> None:
        def work() -> None:
            self._sv.stock.record(
                self._session.context(),
                item_type_id=self._item_type,
                location_id=LocationId(uuid.UUID(site_id)),
                kind=MovementKind.RECEIVED,
                quantity=self._quantity(quantity),
                reason=reason,
            )

        self._run(work, "Stock received")

    @Slot(str, str, str)
    def writeOff(self, site_id: str, quantity: str, reason: str) -> None:  # noqa: N802
        def work() -> None:
            self._sv.stock.record(
                self._session.context(),
                item_type_id=self._item_type,
                location_id=LocationId(uuid.UUID(site_id)),
                kind=MovementKind.WRITTEN_OFF,
                quantity=self._quantity(quantity),
                reason=reason,
            )

        self._run(work, "Stock written off")

    @Slot(str, str, str)
    def count(self, site_id: str, counted: str, reason: str) -> None:
        """Records a stock count; the difference from the books becomes an adjustment."""

        def work() -> int:
            actor = self._session.actor()
            location = LocationId(uuid.UUID(site_id))
            physical = self._quantity(counted)
            if physical < 0:
                raise RuleViolation("A count cannot be negative.")
            on_books = self._sv.stock.position(actor, self._item_type).on_hand_at(location)
            difference = physical - on_books
            if difference:
                self._sv.stock.record(
                    self._session.context(),
                    item_type_id=self._item_type,
                    location_id=location,
                    kind=MovementKind.ADJUSTED,
                    quantity=difference,
                    reason=reason or f"Stock count: {physical} counted, {on_books} on record",
                )
            return difference

        def done(difference: int) -> None:
            self.saved.emit(
                "Count matches the records"
                if difference == 0
                else f"Count recorded ({difference:+d})"
            )
            self.refresh()

        self._error = ""
        self.changed.emit()
        self._tasks.submit(work, done, self._fail)

    @Slot(str, str)
    def setReorderLevel(self, site_id: str, level: str) -> None:  # noqa: N802
        def work() -> None:
            self._sv.stock.set_reorder_level(
                self._session.context(),
                self._item_type,
                LocationId(uuid.UUID(site_id)),
                self._quantity(level),
            )

        self._run(work, "Reorder level saved")

    @Slot(dict, str)
    def stocktake(self, counts: dict[str, Any], note: str) -> None:
        """Counts several stores at once; the variance report appears in ``variance``."""
        values = {k: v for k, v in counts.items() if str(v).strip() != ""}

        def work() -> list[dict[str, Any]]:
            parsed = {LocationId(uuid.UUID(k)): self._quantity(str(v)) for k, v in values.items()}
            report = self._sv.stock.stocktake(
                self._session.context(), self._item_type, parsed, note
            )
            names = {s["value"]: s["label"] for s in self._site_choices}
            return [
                {"site": names.get(str(r.location_id), ""), "expected": r.expected,
                 "counted": r.counted, "variance": f"{r.variance:+d}" if r.variance else "0",
                 "kind": "success" if r.variance == 0 else "warning"}
                for r in report
            ]  # fmt: skip

        def done(report: list[dict[str, Any]]) -> None:
            self._variance = report
            self.varianceChanged.emit()
            changed = sum(1 for r in report if r["variance"] != "0")
            self.saved.emit(
                "Stocktake recorded: every store matches"
                if not changed
                else f"Stocktake recorded: {changed} store(s) adjusted"
            )
            self.refresh()

        self._error = ""
        self.changed.emit()
        self._tasks.submit(work, done, self._fail)

    @Slot()
    def clearVariance(self) -> None:  # noqa: N802
        self._variance = []
        self.varianceChanged.emit()
