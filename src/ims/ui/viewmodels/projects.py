"""Projects: the list, one project's full record, and the flight and survey logs on it."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.application.projects import MyWork, ProjectOverview, ProjectTotals
from ims.domain.assets.catalogue import Category
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    LocationId,
    ProjectId,
    SortieId,
    SurveySessionId,
    UserId,
)
from ims.domain.identity.user import User
from ims.domain.operations.deployment import Deployment, DeploymentState
from ims.domain.operations.field_logs import SurveyMode
from ims.domain.operations.project import PROJECT_TRANSITIONS, Project, ProjectStatus
from ims.domain.operations.reservation import ReservationStatus, booking_label
from ims.ui.app_services import Services
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import describe_error, local_time, optional_date, text
from ims.ui.viewmodels.session import SessionViewModel

RESERVATION_STATUS = {
    ReservationStatus.REQUESTED: ("warning", "Waiting for approval"),
    ReservationStatus.APPROVED: ("success", "Booked"),
    ReservationStatus.REJECTED: ("danger", "Rejected"),
    ReservationStatus.CANCELLED: ("neutral", "Cancelled"),
    ReservationStatus.FULFILLED: ("info", "Checked out"),
}

PROJECT_STATUS = {
    ProjectStatus.PLANNED: ("info", "Planned"),
    ProjectStatus.ACTIVE: ("success", "Active"),
    ProjectStatus.COMPLETED: ("neutral", "Completed"),
    ProjectStatus.CANCELLED: ("neutral", "Cancelled"),
}
DEPLOYMENT_STATE = {
    DeploymentState.PENDING: ("warning", "Checking out"),
    DeploymentState.OUT: ("info", "Out"),
    DeploymentState.RETURNED: ("success", "Returned"),
    DeploymentState.CANCELLED: ("neutral", "Cancelled"),
}
STATUS_ACTIONS = {
    ProjectStatus.ACTIVE: "Reopen",
    ProjectStatus.COMPLETED: "Mark completed",
    ProjectStatus.CANCELLED: "Cancel project",
    ProjectStatus.PLANNED: "Reinstate",
}
SURVEY_MODES = [
    {"value": SurveyMode.RTK.value, "label": "RTK"},
    {"value": SurveyMode.PPK.value, "label": "PPK"},
    {"value": SurveyMode.STATIC.value, "label": "Static"},
]

_ROLES = (
    "startsOn",
    "mine",
    "myRole",
    "myWork",
    "projectId",
    "version",
    "code",
    "name",
    "site",
    "dates",
    "chiefPilot",
    "flights",
    "statusKind",
    "statusLabel",
    "status",
    "search",
)


_DASH = f" {chr(0x2013)} "  # en dash


def dates_text(starts_on: date, ends_on: date | None) -> str:
    if ends_on is None:
        return f"From {starts_on:%d %b %Y}"
    if starts_on.year == ends_on.year:
        return f"{starts_on:%d %b}{_DASH}{ends_on:%d %b %Y}"
    return f"{starts_on:%d %b %Y}{_DASH}{ends_on:%d %b %Y}"


def hours_text(hours: Decimal) -> str:
    whole = int(hours)
    minutes = int(((hours - whole) * 60).to_integral_value(ROUND_HALF_UP))
    return f"{whole} h {minutes:02d} min" if whole else f"{minutes} min"


def minutes_to_hours(raw: str) -> Decimal:
    """Flight time typed in minutes, stored as hours with two decimals."""
    try:
        minutes = Decimal(str(raw).strip())
    except InvalidOperation as exc:
        raise RuleViolation("Enter the time in minutes, e.g. 45.") from exc
    if minutes <= 0:
        raise RuleViolation("Enter the time in minutes, e.g. 45.")
    return (minutes / 60).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _decimal(raw: str, label: str) -> Decimal | None:
    value = str(raw).strip().replace(",", "")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise RuleViolation(f"{label} must be a number.") from exc


def _int(raw: Any, label: str, default: int = 0) -> int:
    value = "" if raw is None else str(raw).strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuleViolation(f"{label} must be a whole number.") from exc


def _id(raw: Any) -> uuid.UUID | None:
    value = str(raw or "").strip()
    return uuid.UUID(value) if value else None


def _ids(raw: Any) -> list[uuid.UUID]:
    return [uuid.UUID(str(v)) for v in (raw or []) if str(v)]


def my_work_text(mine: MyWork | None) -> str:
    if mine is None:
        return ""
    parts = []
    if mine.flights:
        parts.append(f"{mine.flights} flight{'s' if mine.flights != 1 else ''} · "
                     f"{hours_text(mine.flight_hours)}")  # fmt: skip
    if mine.sessions:
        parts.append(f"{mine.sessions} survey{'s' if mine.sessions != 1 else ''} · "
                     f"{hours_text(mine.survey_hours)}")  # fmt: skip
    return "  ·  ".join(parts)


def licence_text(user: User, day: date) -> str:
    if user.licence is None:
        return "No DGCA certificate"
    state = user.licence.status_on(day)
    if state == "expired":
        return "Certificate expired"
    return f"RPC to {user.licence.expires_on:%d %b %Y}"


class ProjectsViewModel(QObject):
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
        self._search = ""
        self._filter = "open"
        self._error = ""
        self._detail: dict[str, Any] = {}
        self._detail_id: ProjectId | None = None
        self._sites: list[dict[str, str]] = []
        self._people: list[dict[str, Any]] = []
        session.signedIn.connect(self.refresh)

    # ------------------------------------------------------------------ properties

    def _model_get(self) -> DictListModel:
        return self._model

    def _error_get(self) -> str:
        return self._error

    def _count_get(self) -> int:
        return self._model.rowCount()

    def _total_get(self) -> int:
        return len(self._all)

    def _detail_get(self) -> dict[str, Any]:
        return self._detail

    def _can_manage_get(self) -> bool:
        return self._session.can("project.manage")

    def _can_log_get(self) -> bool:
        return self._session.can("usage.record")

    def _can_correct_get(self) -> bool:
        return self._session.can("usage.correct")

    def _filter_get(self) -> str:
        return self._filter

    def _site_options_get(self) -> list[dict[str, str]]:
        return list(self._sites)

    def _pilot_options_get(self) -> list[dict[str, Any]]:
        return [{"value": "", "label": "Not chosen yet"}] + [
            p for p in self._people if p["licensed"]
        ]

    def _surveyor_options_get(self) -> list[dict[str, Any]]:
        return [{"value": "", "label": "Not chosen yet"}, *self._people]

    model = Property(QObject, _model_get, constant=True)
    error = Property(str, _error_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    total = Property(int, _total_get, notify=changed)
    detail = Property(dict, _detail_get, notify=detailChanged)
    canManage = Property(bool, _can_manage_get, notify=changed)  # noqa: N815
    canLog = Property(bool, _can_log_get, notify=changed)  # noqa: N815
    canCorrect = Property(bool, _can_correct_get, notify=changed)  # noqa: N815
    filter = Property(str, _filter_get, notify=changed)
    siteOptions = Property(list, _site_options_get, notify=changed)  # noqa: N815
    pilotOptions = Property(list, _pilot_options_get, notify=changed)  # noqa: N815
    surveyorOptions = Property(list, _surveyor_options_get, notify=changed)  # noqa: N815

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
                self.openProject(str(self._detail_id))

        self._tasks.submit(work, done, self._fail)

    def _is_crew_view(self) -> bool:
        """Pilots and surveyors see their own work first; administrators see everything."""
        return not self._session.can("project.manage")

    def _matches(self, row: dict[str, Any], key: str) -> bool:
        status = str(row["status"])
        if key == "assigned":
            return bool(row["mine"]) and status in {"planned", "active"}
        if key == "completed":
            return status == "completed" and (bool(row["mine"]) or not self._is_crew_view())
        if key == "open":
            return status in {"planned", "active"}
        if key == "cancelled":
            return status == "cancelled"
        return True

    def _apply_filter(self) -> None:
        valid = {o["value"] for o in self.filters()}
        if self._filter not in valid:
            self._filter = "assigned" if self._is_crew_view() else "open"
        needle = self._search.strip().lower()
        rows = [
            r
            for r in self._all
            if self._matches(r, self._filter) and (not needle or needle in r["search"])
        ]
        if self._filter == "assigned":
            # What is happening now first, then what comes next.
            rows.sort(key=lambda r: (r["status"] != "active", r["startsOn"]))
        self._model.reset(rows)
        self.changed.emit()

    # ------------------------------------------------------------------ list

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("project.view"):
            return
        actor = self._session.actor()
        today = self._sv.clock.today()

        def work() -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
            sites = {s.id: s for s in self._sv.sites.list_sites(actor, include_deleted=True)}
            people = {u.id: u for u in self._sv.users.crew_directory(actor)}
            totals = self._sv.projects.totals(actor)
            mine = self._sv.projects.my_work(actor)
            rows = [
                self._row(p, sites, people, totals.get(p.id), mine.get(p.id))
                for p in self._sv.projects.list_projects(actor)
            ]
            site_options = [
                {"value": str(s.id), "label": s.label} for s in sites.values() if not s.is_deleted
            ]
            directory = [
                {
                    "value": str(u.id),
                    "label": f"{u.full_name}  ·  {u.role.value.title()}",
                    "name": u.full_name,
                    "role": u.role.value,
                    "licensed": u.licence is not None and u.licence.is_valid_on(today),
                    "licence": licence_text(u, today),
                }
                for u in sorted(people.values(), key=lambda u: u.full_name)
            ]
            return rows, sorted(site_options, key=lambda o: o["label"]), directory

        def done(
            result: tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]],
        ) -> None:
            self._all, self._sites, self._people = result
            self._apply_filter()

        self._tasks.submit(work, done, self._fail)

    def _row(
        self,
        p: Project,
        sites: dict[Any, Any],
        people: dict[Any, User],
        totals: ProjectTotals | None,
        mine: MyWork | None = None,
    ) -> dict[str, Any]:
        kind, label = PROJECT_STATUS[p.status]
        site = sites.get(p.site_id)
        pilot = people.get(p.chief_pilot_id) if p.chief_pilot_id else None
        flights = ""
        if totals is not None and totals.flights:
            flights = f"{totals.flights} · {hours_text(totals.flight_hours)}"
        return {
            "startsOn": p.starts_on.isoformat(),
            "mine": mine is not None,
            "myRole": ", ".join(mine.roles) if mine else "",
            "myWork": my_work_text(mine),
            "projectId": str(p.id),
            "version": p.version,
            "code": p.code,
            "name": p.name,
            "site": site.label if site else "",
            "dates": dates_text(p.starts_on, p.ends_on),
            "chiefPilot": pilot.full_name if pilot else "",
            "flights": flights,
            "statusKind": kind,
            "statusLabel": label,
            "status": p.status.value,
            "search": " ".join([p.code, p.name, p.client, site.label if site else ""]).lower(),
        }

    @Slot(str)
    def setSearch(self, value: str) -> None:  # noqa: N802
        self._search = value
        self._apply_filter()

    @Slot(str)
    def setFilter(self, value: str) -> None:  # noqa: N802
        self._filter = value
        self._apply_filter()

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    @Slot(result=list)
    def filters(self) -> list[dict[str, str]]:
        """Tabs for the list, with counts. Pilots and surveyors get their own two first."""
        keys = (
            [("assigned", "Assigned"), ("completed", "Completed"), ("all", "All")]
            if self._is_crew_view()
            else [("open", "Open"), ("completed", "Completed"), ("cancelled", "Cancelled"),
                  ("all", "All")]
        )  # fmt: skip
        result = []
        for key, label in keys:
            count = sum(1 for r in self._all if self._matches(r, key))
            shown = f"{label} {count}" if key != "all" and count else label
            result.append({"value": key, "label": shown})
        return result

    def _filter_options_get(self) -> list[dict[str, str]]:
        return self.filters()

    def _crew_view_get(self) -> bool:
        return self._is_crew_view()

    filterOptions = Property(list, _filter_options_get, notify=changed)  # noqa: N815
    crewView = Property(bool, _crew_view_get, notify=changed)  # noqa: N815

    @Slot(result=list)
    def surveyModes(self) -> list[dict[str, str]]:  # noqa: N802
        return list(SURVEY_MODES)

    @Slot(str, str, result=str)
    def suggestCode(self, site_id: str, starts_on: str) -> str:  # noqa: N802
        day = optional_date({"d": starts_on}, "d") or self._sv.clock.today()
        site = _id(site_id)
        return self._sv.projects.suggest_code(
            self._session.actor(), LocationId(site) if site else None, day
        )

    # ------------------------------------------------------------------ project commands

    def _fields(self, values: dict[str, Any]) -> dict[str, Any]:
        site = _id(values.get("siteId"))
        if site is None:
            raise RuleViolation("Choose the site.")
        starts_on = optional_date(values, "startsOn")
        if starts_on is None:
            raise RuleViolation("Choose the start date.")
        pilot, surveyor = _id(values.get("chiefPilotId")), _id(values.get("surveyorId"))
        return {
            "code": text(values, "code"),
            "name": text(values, "name"),
            "site_id": LocationId(site),
            "client": text(values, "client"),
            "starts_on": starts_on,
            "ends_on": optional_date(values, "endsOn"),
            "chief_pilot_id": UserId(pilot) if pilot else None,
            "surveyor_id": UserId(surveyor) if surveyor else None,
            "notes": text(values, "notes"),
        }

    @Slot(dict)
    def create(self, values: dict[str, Any]) -> None:
        fields = values.copy()

        def work() -> None:
            project_id = self._sv.projects.create(self._session.context(), **self._fields(fields))
            self._detail_id = project_id

        self._run(work, f"{text(fields, 'code').upper() or 'Project'} created")

    @Slot(str, int, dict)
    def update(self, project_id: str, version: int, values: dict[str, Any]) -> None:
        fields = values.copy()
        self._run(
            lambda: self._sv.projects.update(
                self._session.context(),
                ProjectId(uuid.UUID(project_id)),
                version,
                **self._fields(fields),
            ),
            "Project saved",
        )

    @Slot(str, int, str)
    def setStatus(self, project_id: str, version: int, status: str) -> None:  # noqa: N802
        new = ProjectStatus(status)
        self._run(
            lambda: self._sv.projects.set_status(
                self._session.context(), ProjectId(uuid.UUID(project_id)), version, new
            ),
            f"Project {PROJECT_STATUS[new][1].lower()}",
        )

    @Slot(str, int)
    def remove(self, project_id: str, version: int) -> None:
        def work() -> None:
            self._sv.projects.remove(
                self._session.context(), ProjectId(uuid.UUID(project_id)), version
            )
            self._detail_id = None

        self._run(work, "Project removed")

    # ------------------------------------------------------------------ detail

    @Slot(str)
    def openProject(self, project_id: str) -> None:  # noqa: N802
        self._detail_id = ProjectId(uuid.UUID(project_id))
        actor = self._session.actor()

        def work() -> dict[str, Any]:
            return self._detail_dict(
                self._sv.projects.overview(actor, ProjectId(uuid.UUID(project_id)))
            )

        def done(detail: dict[str, Any]) -> None:
            self._detail = detail
            self.detailChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot()
    def closeProject(self) -> None:  # noqa: N802
        self._detail_id = None
        self._detail = {}
        self.detailChanged.emit()

    def _detail_dict(self, o: ProjectOverview) -> dict[str, Any]:
        actor = self._session.actor()
        today = self._sv.clock.today()
        p, t = o.project, o.totals
        kind, label = PROJECT_STATUS[p.status]
        summaries = {s.asset.id: s for s in self._sv.registry.summaries(actor)}
        people = {u.id: u for u in self._sv.users.crew_directory(actor)}

        def tag(asset_id: AssetId) -> str:
            s = summaries.get(asset_id)
            return s.asset.asset_tag if s else "?"

        def name(user_id: UserId) -> str:
            u = people.get(user_id)
            return u.full_name if u else "Former user"

        def pick(ids: tuple[AssetId, ...], test: Callable[[Any], bool]) -> list[dict[str, str]]:
            return [
                {"value": str(a), "label": f"{tag(a)} · {summaries[a].item_type.name}"}
                for a in ids
                if a in summaries and test(summaries[a].item_type)
            ]

        def deployment(d: Deployment) -> dict[str, Any]:
            d_kind, d_label = DEPLOYMENT_STATE[d.state]
            loggable = d.state in {DeploymentState.OUT, DeploymentState.RETURNED}
            crew = [people[c] for c in d.crew_ids if c in people]
            return {
                "deploymentId": str(d.id),
                "version": d.version,
                "label": f"Out {d.deployed_on:%d %b %Y}"
                + (f" · back {d.returned_on:%d %b}" if d.returned_on else ""),
                "stateKind": d_kind,
                "stateLabel": d_label,
                "items": ", ".join(tag(a) for a in d.asset_ids),
                "itemCount": len(d.asset_ids),
                "crew": ", ".join(name(c) for c in d.crew_ids),
                "gcp": d.gcp_quantity,
                "failure": d.failure,
                "canReturn": d.state is DeploymentState.OUT,
                "loggable": loggable,
                "drones": pick(d.asset_ids, lambda t: t.category is Category.DRONE),
                "batteries": pick(d.asset_ids, lambda t: t.code == "DRONE_BATTERY"),
                "gnssBatteries": pick(
                    d.asset_ids,
                    lambda t: t.category is Category.BATTERY and t.code != "DRONE_BATTERY",
                ),
                "media": pick(d.asset_ids, lambda t: t.category is Category.DATA_MEDIA),
                "receivers": pick(
                    d.asset_ids, lambda t: t.category is Category.GNSS and bool(t.meters)
                ),
                "controllers": pick(d.asset_ids, lambda t: t.code == "CONTROLLER"),
                "pilots": [
                    {"value": str(u.id), "label": u.full_name}
                    for u in crew
                    if u.licence is not None
                ],
                "crewOptions": [{"value": str(u.id), "label": u.full_name} for u in crew],
            }

        sorties = [
            {
                "sortieId": str(s.id),
                "version": s.version,
                "when": f"{s.flown_on:%d %b %Y}",
                "drone": tag(s.drone_id),
                "pilot": name(s.pilot_id),
                "time": hours_text(s.hours),
                "landings": s.landings,
                "batteries": ", ".join(tag(b) for b in s.battery_ids),
                "media": ", ".join(tag(m) for m in s.media_ids),
                "notes": s.notes,
                "void": s.is_void,
                "voidReason": s.void_reason,
            }
            for s in reversed(o.sorties)
        ]
        sessions = [
            {
                "sessionId": str(v.id),
                "version": v.version,
                "when": f"{v.surveyed_on:%d %b %Y}",
                "surveyor": name(v.surveyor_id),
                "mode": v.mode.value.upper(),
                "base": tag(v.base_id) if v.base_id else "—",
                "rovers": ", ".join(tag(r) for r in v.rover_ids) or "—",
                "time": hours_text(v.hours),
                "area": f"{v.area_ha} ha" if v.area_ha is not None else "",
                "points": v.points,
                "fixRate": f"{v.fix_rate}%" if v.fix_rate is not None else "",
                "void": v.is_void,
                "voidReason": v.void_reason,
            }
            for v in reversed(o.sessions)
        ]
        mine = self._sv.projects.my_work(actor).get(p.id)
        return {
            "myRole": ", ".join(mine.roles) if mine else "",
            "myWork": my_work_text(mine),
            "projectId": str(p.id),
            "version": p.version,
            "code": p.code,
            "name": p.name,
            "client": p.client,
            "siteId": str(p.site_id),
            "site": o.site.label if o.site else "",
            "startsOn": p.starts_on.isoformat(),
            "endsOn": p.ends_on.isoformat() if p.ends_on else "",
            "dates": dates_text(p.starts_on, p.ends_on),
            "chiefPilotId": str(p.chief_pilot_id) if p.chief_pilot_id else "",
            "chiefPilot": o.chief_pilot.full_name if o.chief_pilot else "",
            "chiefPilotLicence": licence_text(o.chief_pilot, today) if o.chief_pilot else "",
            "surveyorId": str(p.surveyor_id) if p.surveyor_id else "",
            "surveyor": o.surveyor.full_name if o.surveyor else "",
            "notes": p.notes,
            "status": p.status.value,
            "statusKind": kind,
            "statusLabel": label,
            "isOpen": p.is_open,
            "statusActions": [
                {"value": s.value, "label": STATUS_ACTIONS[s]}
                for s in sorted(PROJECT_TRANSITIONS[p.status], key=lambda s: s.value)
            ],
            "canRemove": not o.deployments,
            "totals": {
                "flights": t.flights,
                "flightTime": hours_text(t.flight_hours) if t.flights else "—",
                "sessions": t.sessions,
                "surveyTime": hours_text(t.survey_hours) if t.sessions else "—",
                "area": f"{t.area_ha.normalize():f} ha" if t.area_ha else "—",
                "points": t.points,
                "gcpIssued": t.gcp_issued,
                "gcpReturned": t.gcp_returned,
                "gcpConsumed": t.gcp_consumed,
                "openDeployments": t.open_deployments,
            },
            "deployments": [deployment(d) for d in reversed(o.deployments)],
            "loggable": [
                deployment(d)
                for d in reversed(o.deployments)
                if d.state in {DeploymentState.OUT, DeploymentState.RETURNED}
            ],
            "sorties": sorties,
            "sessions": sessions,
            "reservations": [
                {
                    "reservationId": str(r.id),
                    "dates": booking_label("", r.starts_on, r.ends_on).lstrip(", "),
                    "items": ", ".join(tag(a) for a in r.asset_ids) or "GCP banners only",
                    "gcp": r.gcp_quantity,
                    "statusKind": RESERVATION_STATUS[r.status][0],
                    "statusLabel": RESERVATION_STATUS[r.status][1],
                }
                for r in self._sv.reservations.list_reservations(actor)
                if r.project_id == p.id
            ],
            "updatedAt": local_time(self._sv.clock.now()),
        }

    # ------------------------------------------------------------------ field logs

    @Slot(dict)
    def logSortie(self, values: dict[str, Any]) -> None:  # noqa: N802
        fields = values.copy()

        def work() -> None:
            deployment = _id(fields.get("deploymentId"))
            drone = _id(fields.get("droneId"))
            pilot = _id(fields.get("pilotId"))
            if deployment is None or drone is None or pilot is None:
                raise RuleViolation("Choose the deployment, the drone and the pilot.")
            flown_on = optional_date(fields, "flownOn") or self._sv.clock.today()
            base = _id(fields.get("ppkBaseId"))
            self._sv.logs.log_sortie(
                self._session.context(),
                deployment_id=DeploymentId(deployment),
                drone_id=AssetId(drone),
                pilot_id=UserId(pilot),
                flown_on=flown_on,
                hours=minutes_to_hours(text(fields, "minutes")),
                landings=_int(fields.get("landings"), "Landings", 1),
                cycles=_int(fields.get("cycles"), "Cycles", 1),
                battery_ids=[AssetId(b) for b in _ids(fields.get("batteryIds"))],
                ppk_base_id=AssetId(base) if base else None,
                media_ids=[AssetId(m) for m in _ids(fields.get("mediaIds"))],
                notes=text(fields, "notes"),
            )

        self._run(work, "Flight logged")

    @Slot(str, int, str)
    def voidSortie(self, sortie_id: str, version: int, reason: str) -> None:  # noqa: N802
        self._run(
            lambda: self._sv.logs.void_sortie(
                self._session.context(), SortieId(uuid.UUID(sortie_id)), version, reason
            ),
            "Flight log cancelled",
        )

    @Slot(dict)
    def logSession(self, values: dict[str, Any]) -> None:  # noqa: N802
        fields = values.copy()

        def work() -> None:
            deployment = _id(fields.get("deploymentId"))
            surveyor = _id(fields.get("surveyorId"))
            if deployment is None or surveyor is None:
                raise RuleViolation("Choose the deployment and the surveyor.")
            base, controller = _id(fields.get("baseId")), _id(fields.get("controllerId"))
            hours = _decimal(text(fields, "hours"), "Hours")
            if hours is None:
                raise RuleViolation("Enter how many hours the session took.")
            self._sv.logs.log_session(
                self._session.context(),
                deployment_id=DeploymentId(deployment),
                surveyor_id=UserId(surveyor),
                surveyed_on=optional_date(fields, "surveyedOn") or self._sv.clock.today(),
                hours=hours.quantize(Decimal("0.01"), ROUND_HALF_UP),
                mode=SurveyMode(text(fields, "mode") or SurveyMode.RTK.value),
                base_id=AssetId(base) if base else None,
                rover_ids=[AssetId(r) for r in _ids(fields.get("roverIds"))],
                controller_id=AssetId(controller) if controller else None,
                battery_ids=[AssetId(b) for b in _ids(fields.get("batteryIds"))],
                area_ha=_decimal(text(fields, "area"), "Area"),
                points=_int(fields.get("points"), "Points"),
                fix_rate=_decimal(text(fields, "fixRate"), "Fix rate"),
                notes=text(fields, "notes"),
            )

        self._run(work, "Survey session logged")

    @Slot(str, int, str)
    def voidSession(self, session_id: str, version: int, reason: str) -> None:  # noqa: N802
        self._run(
            lambda: self._sv.logs.void_session(
                self._session.context(), SurveySessionId(uuid.UUID(session_id)), version, reason
            ),
            "Survey log cancelled",
        )
