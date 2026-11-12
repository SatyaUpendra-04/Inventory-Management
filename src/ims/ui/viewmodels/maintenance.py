"""Maintenance: what is due, defects, work orders and the programme."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DefectId,
    ItemTypeId,
    MaintenanceTaskId,
    WorkOrderId,
)
from ims.domain.maintenance.defects import Defect, DefectState
from ims.domain.maintenance.programme import DueState, MaintenanceTask, TaskDue
from ims.domain.maintenance.work_orders import WORK_ORDER_TRANSITIONS, WorkOrder, WorkOrderState
from ims.ui.app_services import Services
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import describe_error, local_time, optional_date, text
from ims.ui.viewmodels.session import SessionViewModel

DUE_LABELS = {
    DueState.OK: ("success", "OK"),
    DueState.DUE_SOON: ("info", "Due soon"),
    DueState.DUE: ("warning", "Due"),
    DueState.OVERDUE: ("danger", "Overdue"),
}
DEFECT_LABELS = {
    DefectState.REPORTED: ("warning", "To assess"),
    DefectState.GROUNDED: ("danger", "Grounding"),
    DefectState.DEFERRED: ("info", "Deferred"),
    DefectState.RECTIFIED: ("success", "Fixed"),
    DefectState.CANCELLED: ("neutral", "Not a defect"),
}
ORDER_LABELS = {
    WorkOrderState.OPEN: ("info", "Open"),
    WorkOrderState.IN_PROGRESS: ("info", "In progress"),
    WorkOrderState.AWAITING_PARTS: ("warning", "Awaiting parts"),
    WorkOrderState.COMPLETED: ("warning", "Awaiting sign-off"),
    WorkOrderState.CERTIFIED: ("success", "Returned to service"),
    WorkOrderState.CANCELLED: ("neutral", "Cancelled"),
}
MOVE_LABELS = {
    WorkOrderState.IN_PROGRESS: "Start work",
    WorkOrderState.AWAITING_PARTS: "Waiting for parts",
    WorkOrderState.CANCELLED: "Cancel work order",
}


def intervals_text(task: MaintenanceTask) -> str:
    parts = []
    if task.every_hours is not None:
        parts.append(f"{task.every_hours.normalize():f} h")
    if task.every_cycles is not None:
        parts.append(f"{task.every_cycles} cycles")
    if task.every_landings is not None:
        parts.append(f"{task.every_landings} landings")
    if task.every_days is not None:
        parts.append(f"{task.every_days} days")
    joined = " or ".join(parts)
    return f"Life limit {joined}" if task.life_limit else f"Every {joined}"


def tolerance_text(task: MaintenanceTask) -> str:
    parts = []
    if task.tolerance_hours:
        parts.append(f"+{task.tolerance_hours.normalize():f} h")
    if task.tolerance_cycles:
        parts.append(f"+{task.tolerance_cycles} cycles")
    if task.tolerance_landings:
        parts.append(f"+{task.tolerance_landings} landings")
    if task.tolerance_days:
        parts.append(f"+{task.tolerance_days} days")
    return ", ".join(parts)


def due_row(d: TaskDue) -> dict[str, Any]:
    kind, label = DUE_LABELS[d.state]
    return {
        "taskId": str(d.task.id),
        "task": d.task.name,
        "intervals": intervals_text(d.task),
        "lifeLimit": d.task.life_limit,
        "stateKind": kind,
        "stateLabel": label,
        "state": d.state.value,
        "summary": d.summary,
        "lastDone": f"{d.last_done:%d %b %Y}" if d.last_done else "",
        "dueOn": f"{d.due_on:%d %b %Y}" if d.due_on else "",
    }


def _id(raw: Any) -> uuid.UUID | None:
    value = str(raw or "").strip()
    return uuid.UUID(value) if value else None


def _ids(raw: Any) -> list[uuid.UUID]:
    return [uuid.UUID(str(v)) for v in (raw or []) if str(v)]


def _number(raw: Any, label: str, *, whole: bool) -> Any:
    value = "" if raw is None else str(raw).strip()
    if not value:
        return None
    try:
        return int(value) if whole else Decimal(value)
    except (ValueError, InvalidOperation) as exc:
        raise RuleViolation(f"{label} must be a {'whole ' if whole else ''}number.") from exc


class MaintenanceViewModel(QObject):
    changed = Signal()
    orderChanged = Signal()  # noqa: N815
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
        self._error = ""
        self._due: list[dict[str, Any]] = []
        self._defects: list[dict[str, Any]] = []
        self._orders: list[dict[str, Any]] = []
        self._programme: list[dict[str, Any]] = []
        self._order: dict[str, Any] = {}
        self._order_id: WorkOrderId | None = None
        session.signedIn.connect(self._on_signed_in)

    # ------------------------------------------------------------------ properties

    def _error_get(self) -> str:
        return self._error

    def _due_get(self) -> list[dict[str, Any]]:
        return list(self._due)

    def _defects_get(self) -> list[dict[str, Any]]:
        return list(self._defects)

    def _orders_get(self) -> list[dict[str, Any]]:
        return list(self._orders)

    def _programme_get(self) -> list[dict[str, Any]]:
        return list(self._programme)

    def _order_get(self) -> dict[str, Any]:
        return self._order

    def _overdue_get(self) -> int:
        return sum(1 for r in self._due if r["state"] == DueState.OVERDUE.value)

    def _open_defects_get(self) -> int:
        return sum(1 for d in self._defects if d["open"])

    def _open_orders_get(self) -> int:
        return sum(1 for o in self._orders if o["open"])

    def _can_manage_get(self) -> bool:
        return self._session.can("maintenance.manage")

    def _can_certify_get(self) -> bool:
        return self._session.can("maintenance.certify")

    def _can_report_get(self) -> bool:
        return self._session.can("defect.report")

    error = Property(str, _error_get, notify=changed)
    due = Property(list, _due_get, notify=changed)
    defects = Property(list, _defects_get, notify=changed)
    orders = Property(list, _orders_get, notify=changed)
    programme = Property(list, _programme_get, notify=changed)
    order = Property(dict, _order_get, notify=orderChanged)
    overdueCount = Property(int, _overdue_get, notify=changed)  # noqa: N815
    openDefects = Property(int, _open_defects_get, notify=changed)  # noqa: N815
    openOrders = Property(int, _open_orders_get, notify=changed)  # noqa: N815
    canManage = Property(bool, _can_manage_get, notify=changed)  # noqa: N815
    canCertify = Property(bool, _can_certify_get, notify=changed)  # noqa: N815
    canReport = Property(bool, _can_report_get, notify=changed)  # noqa: N815

    # ------------------------------------------------------------------ plumbing

    def _fail(self, exc: BaseException) -> None:
        self._error = describe_error(exc)
        self.changed.emit()

    def _run(self, work: Callable[[], Any], message: str) -> None:
        self._error = ""
        self.changed.emit()

        def done(_: Any) -> None:
            self.saved.emit(message)
            self.refresh()
            if self._order_id is not None:
                self.openOrder(str(self._order_id))

        self._tasks.submit(work, done, self._fail)

    def _on_signed_in(self) -> None:
        if self._session.can("maintenance.manage"):
            # The starting programme (once), then ground anything that is now overdue.
            def setup() -> None:
                self._sv.maintenance.install_default_programme(self._session.context())
                self._sv.maintenance.ground_overdue(self._session.context())

            self._tasks.submit(setup, lambda _: self.refresh(), self._fail)
        else:
            self.refresh()

    # ------------------------------------------------------------------ lists

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("asset.view"):
            return
        actor = self._session.actor()

        def work() -> dict[str, list[dict[str, Any]]]:
            people = {u.id: u.full_name for u in self._sv.users.crew_directory(actor)}
            assets = {s.asset.id: s for s in self._sv.registry.summaries(actor)}
            types = {
                t.id: t for t in self._sv.catalogue.list_item_types(actor, include_inactive=True)
            }

            def item(asset_id: AssetId) -> tuple[str, str]:
                s = assets.get(asset_id)
                return (s.asset.asset_tag, s.item_type.name) if s else ("?", "")

            due = []
            for row in self._sv.maintenance.due_list(actor):
                due.append(
                    {
                        **due_row(row.due),
                        "assetId": str(row.asset.id),
                        "tag": row.asset.asset_tag,
                        "type": row.item_type.name,
                    }
                )
            defects = [
                self._defect_row(d, item, people) for d in self._sv.maintenance.defects(actor)
            ]
            orders = [self._order_row(w, item) for w in self._sv.maintenance.work_orders(actor)]
            grouped: dict[ItemTypeId, list[dict[str, Any]]] = {}
            for t in self._sv.maintenance.tasks(actor, include_inactive=True):
                grouped.setdefault(t.item_type_id, []).append(
                    {
                        "taskId": str(t.id),
                        "version": t.version,
                        "name": t.name,
                        "intervals": intervals_text(t),
                        "tolerance": tolerance_text(t),
                        "lifeLimit": t.life_limit,
                        "active": t.is_active,
                        "instructions": t.instructions,
                        "itemTypeId": str(t.item_type_id),
                        "everyHours": f"{t.every_hours.normalize():f}" if t.every_hours else "",
                        "everyCycles": str(t.every_cycles or ""),
                        "everyLandings": str(t.every_landings or ""),
                        "everyDays": str(t.every_days or ""),
                        "toleranceHours": f"{t.tolerance_hours.normalize():f}"
                        if t.tolerance_hours
                        else "",
                        "toleranceDays": str(t.tolerance_days or ""),
                    }
                )
            programme = [
                {"itemType": types[k].name if k in types else "?", "tasks": v}
                for k, v in sorted(
                    grouped.items(), key=lambda kv: types[kv[0]].name if kv[0] in types else ""
                )
            ]
            return {"due": due, "defects": defects, "orders": orders, "programme": programme}

        def done(result: dict[str, list[dict[str, Any]]]) -> None:
            self._due = result["due"]
            self._defects = result["defects"]
            self._orders = result["orders"]
            self._programme = result["programme"]
            self.changed.emit()

        self._tasks.submit(work, done, self._fail)

    def _defect_row(
        self, d: Defect, item: Callable[[AssetId], tuple[str, str]], people: dict[Any, str]
    ) -> dict[str, Any]:
        kind, label = DEFECT_LABELS[d.state]
        tag, type_name = item(d.asset_id)
        return {
            "defectId": str(d.id),
            "version": d.version,
            "number": d.number,
            "assetId": str(d.asset_id),
            "tag": tag,
            "type": type_name,
            "description": d.description,
            "stateKind": kind,
            "stateLabel": label,
            "state": d.state.value,
            "open": d.is_open,
            "reported": f"{d.found_on:%d %b %Y} · {people.get(d.reported_by, 'Former user')}",
            "limitation": d.limitation,
            "deferredUntil": f"{d.deferred_until:%d %b %Y}" if d.deferred_until else "",
            "note": d.assessment_note,
            "onWorkOrder": d.work_order_id is not None,
            "canAssess": d.state is DefectState.REPORTED
            and self._session.can("maintenance.manage"),
        }

    def _order_row(
        self, w: WorkOrder, item: Callable[[AssetId], tuple[str, str]]
    ) -> dict[str, Any]:
        kind, label = ORDER_LABELS[w.state]
        tag, type_name = item(w.asset_id)
        return {
            "workOrderId": str(w.id),
            "version": w.version,
            "number": w.number,
            "assetId": str(w.asset_id),
            "tag": tag,
            "type": type_name,
            "title": w.title,
            "stateKind": kind,
            "stateLabel": label,
            "state": w.state.value,
            "open": w.is_open,
            "opened": f"{local_time(w.opened_at)}",
        }

    @Slot()
    def checkOverdue(self) -> None:  # noqa: N802
        """Grounds anything that has become overdue (managers), then refreshes."""
        if not self._session.can("maintenance.manage"):
            self.refresh()
            return

        def done(grounded: int) -> None:
            if grounded:
                self.saved.emit(f"{grounded} item(s) grounded: maintenance overdue")
            self.refresh()

        self._tasks.submit(
            lambda: self._sv.maintenance.ground_overdue(self._session.context()), done, self._fail
        )

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    @Slot(result=list)
    def itemTypes(self) -> list[dict[str, str]]:  # noqa: N802
        actor = self._session.actor()
        return [
            {"value": str(t.id), "label": t.name}
            for t in sorted(self._sv.catalogue.list_item_types(actor), key=lambda t: t.name)
            if t.is_individually_tracked
        ]

    # ------------------------------------------------------------------ one work order

    @Slot(str)
    def openOrder(self, work_order_id: str) -> None:  # noqa: N802
        self._order_id = WorkOrderId(uuid.UUID(work_order_id))
        actor = self._session.actor()

        def work() -> dict[str, Any]:
            w = self._sv.maintenance.work_order(actor, WorkOrderId(uuid.UUID(work_order_id)))
            people = {u.id: u.full_name for u in self._sv.users.crew_directory(actor)}
            assets = {s.asset.id: s for s in self._sv.registry.summaries(actor)}
            tasks = {t.id: t for t in self._sv.maintenance.tasks(actor, include_inactive=True)}
            defects = {d.id: d for d in self._sv.maintenance.defects(actor)}
            s = assets.get(w.asset_id)
            kind, label = ORDER_LABELS[w.state]
            reasons = self._sv.maintenance.grounding_reasons(actor, w.asset_id)
            manage = self._session.can("maintenance.manage")
            moves = [
                {"value": state.value, "label": MOVE_LABELS[state]}
                for state in (
                    WorkOrderState.IN_PROGRESS,
                    WorkOrderState.AWAITING_PARTS,
                    WorkOrderState.CANCELLED,
                )
                if state in WORK_ORDER_TRANSITIONS[w.state] and manage
            ]
            if w.state is WorkOrderState.COMPLETED and manage:
                moves = [{"value": "in_progress", "label": "Reopen"}]
            return {
                "workOrderId": str(w.id),
                "version": w.version,
                "number": w.number,
                "title": w.title,
                "tag": s.asset.asset_tag if s else "?",
                "type": s.item_type.name if s else "",
                "stateKind": kind,
                "stateLabel": label,
                "state": w.state.value,
                "tasks": [
                    {"name": tasks[t].name, "intervals": intervals_text(tasks[t])}
                    for t in w.task_ids
                    if t in tasks
                ],
                "defects": [
                    {
                        "number": defects[d].number,
                        "description": defects[d].description,
                        "stateKind": DEFECT_LABELS[defects[d].state][0],
                        "stateLabel": DEFECT_LABELS[defects[d].state][1],
                    }
                    for d in w.defect_ids
                    if d in defects
                ],
                "openedBy": people.get(w.opened_by, ""),
                "opened": local_time(w.opened_at),
                "workDone": w.work_done,
                "parts": w.parts,
                "note": w.note,
                "completedBy": people.get(w.completed_by, "") if w.completed_by else "",
                "certifiedBy": people.get(w.certified_by, "") if w.certified_by else "",
                "moves": moves,
                "canComplete": manage and w.state is WorkOrderState.IN_PROGRESS,
                "canCertify": self._session.can("maintenance.certify")
                and w.state is WorkOrderState.COMPLETED,
                "blockers": reasons if w.state is WorkOrderState.COMPLETED else [],
            }

        def done(detail: dict[str, Any]) -> None:
            self._order = detail
            self.orderChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot()
    def closeOrder(self) -> None:  # noqa: N802
        self._order_id = None
        self._order = {}
        self.orderChanged.emit()

    # ------------------------------------------------------------------ commands

    @Slot(str, str, bool)
    def reportDefect(self, asset_id: str, description: str, unsafe: bool) -> None:  # noqa: N802
        self._run(
            lambda: self._sv.maintenance.report_defect(
                self._session.context(),
                AssetId(uuid.UUID(asset_id)),
                description=description,
                unsafe=unsafe,
            ),
            "Defect reported; the item is grounded" if unsafe else "Defect reported",
        )

    @Slot(str, int, str, str, str, str)
    def assessDefect(  # noqa: N802
        self, defect_id: str, version: int, decision: str, limitation: str, until: str, note: str
    ) -> None:
        state = DefectState(decision)
        self._run(
            lambda: self._sv.maintenance.assess_defect(
                self._session.context(),
                DefectId(uuid.UUID(defect_id)),
                version,
                decision=state,
                limitation=limitation,
                deferred_until=optional_date({"d": until}, "d"),
                note=note,
            ),
            {
                DefectState.GROUNDED: "Defect assessed: grounded",
                DefectState.DEFERRED: "Defect deferred with a limitation",
                DefectState.CANCELLED: "Marked as not a defect",
            }.get(state, "Saved"),
        )

    @Slot(str, str, list, list)
    def openWorkOrder(  # noqa: N802
        self, asset_id: str, title: str, task_ids: list[str], defect_ids: list[str]
    ) -> None:
        def work() -> None:
            order = self._sv.maintenance.open_work_order(
                self._session.context(),
                AssetId(uuid.UUID(asset_id)),
                title=title,
                task_ids=[MaintenanceTaskId(t) for t in _ids(task_ids)],
                defect_ids=[DefectId(d) for d in _ids(defect_ids)],
            )
            self._order_id = order

        self._run(work, "Work order opened")

    @Slot(str, int, str, str)
    def moveOrder(self, work_order_id: str, version: int, state: str, note: str) -> None:  # noqa: N802
        target = WorkOrderState(state)
        self._run(
            lambda: self._sv.maintenance.move_work_order(
                self._session.context(),
                WorkOrderId(uuid.UUID(work_order_id)),
                version,
                target,
                note,
            ),
            ORDER_LABELS[target][1]
            if target is not WorkOrderState.CANCELLED
            else "Work order cancelled",
        )

    @Slot(str, int, str, str)
    def completeOrder(self, work_order_id: str, version: int, work_done: str, parts: str) -> None:  # noqa: N802
        self._run(
            lambda: self._sv.maintenance.complete_work_order(
                self._session.context(),
                WorkOrderId(uuid.UUID(work_order_id)),
                version,
                work_done=work_done,
                parts=parts,
            ),
            "Work completed; waiting for sign-off",
        )

    @Slot(str, int)
    def certify(self, work_order_id: str, version: int) -> None:
        self._run(
            lambda: self._sv.maintenance.certify(
                self._session.context(), WorkOrderId(uuid.UUID(work_order_id)), version
            ),
            "Returned to service",
        )

    @Slot(str, str, str, str)
    def recordDone(self, asset_id: str, task_id: str, done_on: str, notes: str) -> None:  # noqa: N802
        self._run(
            lambda: self._sv.maintenance.record_completion(
                self._session.context(),
                AssetId(uuid.UUID(asset_id)),
                MaintenanceTaskId(uuid.UUID(task_id)),
                done_on=optional_date({"d": done_on}, "d"),
                notes=notes,
            ),
            "Maintenance recorded",
        )

    def _task_fields(self, values: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "name": text(values, "name"),
            "every_hours": _number(values.get("everyHours"), "Hours", whole=False),
            "every_cycles": _number(values.get("everyCycles"), "Cycles", whole=True),
            "every_landings": _number(values.get("everyLandings"), "Landings", whole=True),
            "every_days": _number(values.get("everyDays"), "Days", whole=True),
            "tolerance_hours": _number(values.get("toleranceHours"), "Tolerance", whole=False)
            or Decimal(0),
            "tolerance_days": _number(values.get("toleranceDays"), "Tolerance", whole=True) or 0,
            "life_limit": bool(values.get("lifeLimit")),
            "instructions": text(values, "instructions"),
        }
        if "active" in values:
            fields["is_active"] = bool(values.get("active"))
        return fields

    @Slot(dict)
    def addTask(self, values: dict[str, Any]) -> None:  # noqa: N802
        fields = values.copy()

        def work() -> None:
            type_id = _id(fields.get("itemTypeId"))
            if type_id is None:
                raise RuleViolation("Choose the kind of equipment.")
            self._sv.maintenance.add_task(
                self._session.context(),
                item_type_id=ItemTypeId(type_id),
                **self._task_fields(fields),
            )

        self._run(work, "Task added to the programme")

    @Slot(str, int, dict)
    def updateTask(self, task_id: str, version: int, values: dict[str, Any]) -> None:  # noqa: N802
        fields = values.copy()
        self._run(
            lambda: self._sv.maintenance.update_task(
                self._session.context(),
                MaintenanceTaskId(uuid.UUID(task_id)),
                version,
                **self._task_fields(fields),
            ),
            "Task saved",
        )
