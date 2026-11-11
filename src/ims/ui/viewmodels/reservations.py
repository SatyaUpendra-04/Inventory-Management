"""Reservations: requests and approvals, a conflict check as you choose, and the calendar."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, KitId, LocationId, ProjectId, ReservationId
from ims.domain.operations.reservation import Reservation, ReservationStatus, booking_label
from ims.ui.app_services import Services
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.equipment import SERVICEABILITY
from ims.ui.viewmodels.forms import describe_error, optional_date, text
from ims.ui.viewmodels.projects import RESERVATION_STATUS
from ims.ui.viewmodels.session import SessionViewModel

CALENDAR_DAYS = 28

_ROLES = (
    "reservationId", "version", "projectId", "project", "dates", "startsOn", "items",
    "itemCount", "gcp", "requestedBy", "mine", "statusKind", "statusLabel", "status", "search",
)  # fmt: skip


def _id(raw: Any) -> uuid.UUID | None:
    value = str(raw or "").strip()
    return uuid.UUID(value) if value else None


def _ids(raw: Any) -> list[uuid.UUID]:
    return [uuid.UUID(str(v)) for v in (raw or []) if str(v)]


def _count(raw: Any) -> int:
    value = "" if raw is None else str(raw).strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError as exc:
        raise RuleViolation("GCP banners must be a whole number.") from exc


class ReservationsViewModel(QObject):
    changed = Signal()
    conflictsChanged = Signal()  # noqa: N815
    detailChanged = Signal()  # noqa: N815
    calendarChanged = Signal()  # noqa: N815
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
        self._filter = "pending"
        self._error = ""
        self._conflicts: dict[str, Any] = {}
        self._detail: dict[str, Any] = {}
        self._detail_id: ReservationId | None = None
        self._calendar: dict[str, Any] = {}
        self._calendar_start: date | None = None
        self._serial = 0
        session.signedIn.connect(self.refresh)

    # ------------------------------------------------------------------ properties

    def _model_get(self) -> DictListModel:
        return self._model

    def _error_get(self) -> str:
        return self._error

    def _count_get(self) -> int:
        return self._model.rowCount()

    def _filter_get(self) -> str:
        return self._filter

    def _pending_get(self) -> int:
        return sum(1 for r in self._all if r["status"] == ReservationStatus.REQUESTED.value)

    def _can_request_get(self) -> bool:
        return self._session.can("reservation.create")

    def _can_approve_get(self) -> bool:
        return self._session.can("reservation.approve")

    def _conflicts_get(self) -> dict[str, Any]:
        return self._conflicts

    def _detail_get(self) -> dict[str, Any]:
        return self._detail

    def _calendar_get(self) -> dict[str, Any]:
        return self._calendar

    def _filter_options_get(self) -> list[dict[str, str]]:
        options = [("pending", "Waiting"), ("upcoming", "Booked"), ("all", "All")]
        result = []
        for key, label in options:
            n = sum(1 for r in self._all if self._matches(r, key))
            result.append({"value": key, "label": f"{label} {n}" if key != "all" and n else label})
        return result

    model = Property(QObject, _model_get, constant=True)
    error = Property(str, _error_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    filter = Property(str, _filter_get, notify=changed)
    pendingCount = Property(int, _pending_get, notify=changed)  # noqa: N815
    canRequest = Property(bool, _can_request_get, notify=changed)  # noqa: N815
    canApprove = Property(bool, _can_approve_get, notify=changed)  # noqa: N815
    conflicts = Property(dict, _conflicts_get, notify=conflictsChanged)
    detail = Property(dict, _detail_get, notify=detailChanged)
    calendar = Property(dict, _calendar_get, notify=calendarChanged)
    filterOptions = Property(list, _filter_options_get, notify=changed)  # noqa: N815

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
            if self._detail_id is not None:
                self.openReservation(str(self._detail_id))

        self._tasks.submit(work, done, self._fail)

    def _matches(self, row: dict[str, Any], key: str) -> bool:
        if key == "pending":
            return bool(row["status"] == ReservationStatus.REQUESTED.value)
        if key == "upcoming":
            return bool(row["status"] == ReservationStatus.APPROVED.value)
        return True

    def _apply_filter(self) -> None:
        rows = [r for r in self._all if self._matches(r, self._filter)]
        self._model.reset(rows)
        self.changed.emit()

    def _labels(self) -> tuple[dict[Any, Any], dict[Any, str], dict[Any, str]]:
        actor = self._session.actor()
        projects = {p.id: p for p in self._sv.projects.list_projects(actor)}
        people = {u.id: u.full_name for u in self._sv.users.crew_directory(actor)}
        tags = {s.asset.id: s.asset.asset_tag for s in self._sv.registry.summaries(actor)}
        return projects, people, tags

    # ------------------------------------------------------------------ list

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("project.view"):
            return
        actor = self._session.actor()
        me = actor.user_id

        def work() -> list[dict[str, Any]]:
            projects, people, tags = self._labels()
            rows = []
            for r in self._sv.reservations.list_reservations(actor):
                project = projects.get(r.project_id)
                code = project.code if project else "Removed project"
                kind, label = RESERVATION_STATUS[r.status]
                items = ", ".join(tags.get(a, "?") for a in r.asset_ids)
                rows.append({
                    "reservationId": str(r.id), "version": r.version,
                    "projectId": str(r.project_id),
                    "project": f"{code} · {project.name}" if project else code,
                    "dates": booking_label("", r.starts_on, r.ends_on).lstrip(", "),
                    "startsOn": r.starts_on.isoformat(),
                    "items": items or "GCP banners only", "itemCount": len(r.asset_ids),
                    "gcp": r.gcp_quantity,
                    "requestedBy": people.get(r.requested_by, "Former user"),
                    "mine": r.requested_by == me, "statusKind": kind, "statusLabel": label,
                    "status": r.status.value,
                    "search": f"{code} {items}".lower(),
                })  # fmt: skip
            return rows

        def done(rows: list[dict[str, Any]]) -> None:
            self._all = rows
            self._apply_filter()

        self._tasks.submit(work, done, self._fail)
        self.loadCalendar("")

    @Slot(str)
    def setFilter(self, value: str) -> None:  # noqa: N802
        self._filter = value
        self._apply_filter()

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    # ------------------------------------------------------------------ request

    def _draft(self, values: dict[str, Any]) -> dict[str, Any]:
        starts_on = optional_date(values, "startsOn")
        ends_on = optional_date(values, "endsOn")
        if starts_on is None or ends_on is None:
            raise RuleViolation("Choose the first and last day.")
        site = _id(values.get("gcpSiteId"))
        return {
            "starts_on": starts_on,
            "ends_on": ends_on,
            "asset_ids": [AssetId(a) for a in _ids(values.get("assetIds"))],
            "kit_ids": [KitId(k) for k in _ids(values.get("kitIds"))],
            "gcp_quantity": _count(values.get("gcpQuantity")),
            "gcp_site_id": LocationId(site) if site else None,
        }

    @Slot(dict)
    def check(self, values: dict[str, Any]) -> None:
        """Conflict check for the request sheet; the newest request wins."""
        fields = values.copy()
        actor = self._session.actor()
        self._serial += 1
        serial = self._serial

        def work() -> dict[str, Any]:
            try:
                draft = self._draft(fields)
            except RuleViolation as exc:
                return {"blockers": list(exc.problems), "warnings": [], "items": 0, "ready": False}
            existing = _id(fields.get("reservationId"))
            report = self._sv.reservations.check(
                actor, reservation_id=ReservationId(existing) if existing else None, **draft
            )
            return {
                "blockers": list(report.conflicts.blockers),
                "warnings": list(report.conflicts.warnings),
                "items": len(report.asset_ids),
                "ready": report.conflicts.ok,
            }

        def done(result: dict[str, Any]) -> None:
            if serial == self._serial:
                self._conflicts = result
                self.conflictsChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot(dict)
    def request(self, values: dict[str, Any]) -> None:
        fields = values.copy()
        approver = self._session.can("reservation.approve")

        def work() -> None:
            project = _id(fields.get("projectId"))
            if project is None:
                raise RuleViolation("Choose the project.")
            self._sv.reservations.request(
                self._session.context(), project_id=ProjectId(project), notes=text(fields, "notes"),
                **self._draft(fields),
            )  # fmt: skip

        self._run(work, "Equipment booked" if approver else "Request sent for approval")

    # ------------------------------------------------------------------ decisions

    @Slot(str, int, str)
    def approve(self, reservation_id: str, version: int, note: str) -> None:
        self._run(
            lambda: self._sv.reservations.approve(
                self._session.context(), ReservationId(uuid.UUID(reservation_id)), version, note
            ),
            "Reservation approved and booked",
        )

    @Slot(str, int, str)
    def reject(self, reservation_id: str, version: int, note: str) -> None:
        self._run(
            lambda: self._sv.reservations.reject(
                self._session.context(), ReservationId(uuid.UUID(reservation_id)), version, note
            ),
            "Reservation rejected",
        )

    @Slot(str, int, str)
    def cancel(self, reservation_id: str, version: int, note: str) -> None:
        self._run(
            lambda: self._sv.reservations.cancel(
                self._session.context(), ReservationId(uuid.UUID(reservation_id)), version, note
            ),
            "Reservation cancelled",
        )

    # ------------------------------------------------------------------ detail

    @Slot(str)
    def openReservation(self, reservation_id: str) -> None:  # noqa: N802
        self._detail_id = ReservationId(uuid.UUID(reservation_id))
        actor = self._session.actor()
        me = actor.user_id

        def work() -> dict[str, Any]:
            r = self._sv.reservations.get(actor, ReservationId(uuid.UUID(reservation_id)))
            return self._detail_dict(r, me)

        def done(detail: dict[str, Any]) -> None:
            self._detail = detail
            self.detailChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot()
    def closeReservation(self) -> None:  # noqa: N802
        self._detail_id = None
        self._detail = {}
        self.detailChanged.emit()

    def _detail_dict(self, r: Reservation, me: Any) -> dict[str, Any]:
        actor = self._session.actor()
        projects, people, _ = self._labels()
        summaries = {s.asset.id: s for s in self._sv.registry.summaries(actor)}
        kits = {k.kit.id: k.kit for k in self._sv.kits.list_kits(actor)}
        sites = {s.id: s.label for s in self._sv.sites.list_sites(actor, include_deleted=True)}
        project = projects.get(r.project_id)
        kind, label = RESERVATION_STATUS[r.status]
        in_kits = {m for k in r.kit_ids if k in kits for m in kits[k].members}
        conflicts: dict[str, Any] = {}
        if r.is_live:
            report = self._sv.reservations.check(
                actor, starts_on=r.starts_on, ends_on=r.ends_on, asset_ids=r.asset_ids,
                gcp_quantity=r.gcp_quantity, gcp_site_id=r.gcp_site_id, reservation_id=r.id,
            )  # fmt: skip
            conflicts = {"blockers": list(report.conflicts.blockers),
                         "warnings": list(report.conflicts.warnings)}  # fmt: skip
        items = []
        for asset_id in r.asset_ids:
            s = summaries.get(asset_id)
            items.append({
                "assetId": str(asset_id),
                "tag": s.asset.asset_tag if s else "?",
                "type": s.item_type.name if s else "",
                "serviceKind": SERVICEABILITY[s.status.serviceability][0] if s else "neutral",
                "serviceLabel": SERVICEABILITY[s.status.serviceability][1] if s else "",
            })  # fmt: skip
        return {
            "reservationId": str(r.id),
            "version": r.version,
            "projectId": str(r.project_id),
            "project": f"{project.code} · {project.name}" if project else "Removed project",
            "dates": booking_label("", r.starts_on, r.ends_on).lstrip(", "),
            "days": (r.ends_on - r.starts_on).days + 1,
            "status": r.status.value,
            "statusKind": kind,
            "statusLabel": label,
            "items": items,
            "kits": ", ".join(kits[k].code for k in r.kit_ids if k in kits),
            "kitIds": [str(k) for k in r.kit_ids],
            "extraAssetIds": [str(a) for a in r.asset_ids if a not in in_kits],
            "gcp": r.gcp_quantity,
            "gcpSiteId": str(r.gcp_site_id) if r.gcp_site_id else "",
            "gcpFrom": sites.get(r.gcp_site_id, "") if r.gcp_site_id else "",
            "notes": r.notes,
            "requestedBy": people.get(r.requested_by, "Former user"),
            "decidedBy": people.get(r.decided_by, "") if r.decided_by else "",
            "decisionNote": r.decision_note,
            "conflicts": conflicts,
            "canApprove": r.status is ReservationStatus.REQUESTED
            and self._session.can("reservation.approve"),
            "canCancel": r.is_live
            and (r.requested_by == me or self._session.can("reservation.approve")),
            "canCheckOut": r.status is ReservationStatus.APPROVED
            and self._session.can("deployment.create"),
        }

    # ------------------------------------------------------------------ calendar

    @Slot(str)
    def loadCalendar(self, start_iso: str) -> None:  # noqa: N802
        """Four weeks from ``start_iso`` (or from the start of this week)."""
        if not self._session.can("project.view"):
            return
        today = self._sv.clock.today()
        start = optional_date({"d": start_iso}, "d") or self._calendar_start
        if start is None:
            start = today - timedelta(days=today.weekday())
        self._calendar_start = start
        end = start + timedelta(days=CALENDAR_DAYS - 1)
        actor = self._session.actor()

        def work() -> dict[str, Any]:
            projects, _, tags = self._labels()
            summaries = {s.asset.id: s for s in self._sv.registry.summaries(actor)}
            entries = self._sv.reservations.schedule(actor, start, end)

            def bar(e: Any, label: str) -> dict[str, Any]:
                first = max(e.starts_on, start)
                last = min(e.ends_on, end)
                return {
                    "start": (first - start).days,
                    "span": (last - first).days + 1,
                    "kind": e.kind,
                    "label": label,
                    "reservationId": str(e.reservation_id) if e.reservation_id else "",
                    "deploymentId": str(e.deployment_id) if e.deployment_id else "",
                    "tip": f"{label}: {booking_label('', e.starts_on, e.ends_on).lstrip(', ')}",
                }

            by_asset: dict[Any, list[dict[str, Any]]] = {}
            by_project: dict[Any, dict[tuple[Any, str], dict[str, Any]]] = {}
            for e in entries:
                project = projects.get(e.project_id)
                code = project.code if project else "?"
                if e.asset_id is not None:
                    by_asset.setdefault(e.asset_id, []).append(bar(e, code))
                key = (e.reservation_id or e.deployment_id, e.kind)
                group = by_project.setdefault(e.project_id, {})
                if key not in group:
                    group[key] = bar(e, {"out": "Out", "approved": "Booked",
                                         "requested": "Requested"}[e.kind])  # fmt: skip
                    group[key]["count"] = 0
                if e.asset_id is not None:
                    group[key]["count"] += 1
            for group in by_project.values():
                for b in group.values():
                    if b["count"]:
                        b["label"] = (
                            f"{b['label']} · {b['count']} item{'s' if b['count'] != 1 else ''}"
                        )

            def code_of(project_id: Any) -> str:
                return str(projects[project_id].code) if project_id in projects else ""

            asset_rows: list[dict[str, Any]] = []
            for asset_id, bars in sorted(by_asset.items(), key=lambda kv: tags.get(kv[0], "")):
                summary = summaries.get(asset_id)
                asset_rows.append({
                    "label": tags.get(asset_id, "?"),
                    "detail": summary.item_type.name if summary else "",
                    "bars": sorted(bars, key=lambda b: int(b["start"])),
                })  # fmt: skip
            project_rows: list[dict[str, Any]] = []
            for project_id, group in sorted(by_project.items(), key=lambda kv: code_of(kv[0])):
                project = projects.get(project_id)
                project_rows.append({
                    "label": project.code if project else "?",
                    "detail": project.name if project else "",
                    "bars": sorted(group.values(), key=lambda b: int(b["start"])),
                })  # fmt: skip
            days = [
                {
                    "label": f"{d:%d}",
                    "weekday": f"{d:%a}"[0],
                    "month": f"{d:%b}" if d.day == 1 or i == 0 else "",
                    "today": d == today,
                    "weekend": d.weekday() >= 5,
                }
                for i, d in enumerate(start + timedelta(days=n) for n in range(CALENDAR_DAYS))
            ]
            title = f"{start:%d %b} {chr(0x2013)} {end:%d %b %Y}"
            return {"days": days, "assets": asset_rows, "projects": project_rows,
                    "title": title, "start": start.isoformat()}  # fmt: skip

        def done(result: dict[str, Any]) -> None:
            self._calendar = result
            self.calendarChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot(int)
    def shiftCalendar(self, weeks: int) -> None:  # noqa: N802
        base = self._calendar_start or self._sv.clock.today()
        self.loadCalendar((base + timedelta(weeks=weeks)).isoformat())

    @Slot()
    def calendarToday(self) -> None:  # noqa: N802
        today = self._sv.clock.today()
        self.loadCalendar((today - timedelta(days=today.weekday())).isoformat())
