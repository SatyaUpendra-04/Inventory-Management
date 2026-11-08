"""Deployments: check equipment and crew out to a project (with a live readiness check),
and bring everything back with its condition."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.domain.assets.status import Custody
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    KitId,
    LocationId,
    ProjectId,
    UserId,
)
from ims.domain.operations.deployment import DeploymentState, ReturnCondition, ReturnLine
from ims.domain.stock.ledger import position
from ims.ui.app_services import Services
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.equipment import SERVICEABILITY
from ims.ui.viewmodels.forms import describe_error, optional_date, text
from ims.ui.viewmodels.projects import DEPLOYMENT_STATE, licence_text
from ims.ui.viewmodels.session import SessionViewModel

_ROLES = (
    "deploymentId", "version", "projectId", "project", "deployedOn", "items", "crew", "gcp",
    "stateKind", "stateLabel", "state", "search",
)  # fmt: skip

CONDITIONS = [
    {"value": ReturnCondition.OK.value, "label": "OK"},
    {"value": ReturnCondition.LIMITED.value, "label": "Usable, with a defect"},
    {"value": ReturnCondition.GROUNDED.value, "label": "Damaged: ground it"},
]


def _id(raw: Any) -> uuid.UUID | None:
    value = str(raw or "").strip()
    return uuid.UUID(value) if value else None


def _ids(raw: Any) -> list[uuid.UUID]:
    return [uuid.UUID(str(v)) for v in (raw or []) if str(v)]


def _count(raw: Any, label: str) -> int:
    value = str(raw if raw is not None else "").strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError as exc:
        raise RuleViolation(f"{label} must be a whole number.") from exc


class DeploymentsViewModel(QObject):
    changed = Signal()
    choicesChanged = Signal()  # noqa: N815
    readinessChanged = Signal()  # noqa: N815
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
        self._filter = "out"
        self._error = ""
        self._choices: dict[str, list[dict[str, Any]]] = {}
        self._readiness: dict[str, Any] = {}
        self._detail: dict[str, Any] = {}
        self._check_serial = 0
        session.signedIn.connect(self.refresh)

    # ------------------------------------------------------------------ properties

    def _model_get(self) -> DictListModel:
        return self._model

    def _error_get(self) -> str:
        return self._error

    def _count_get(self) -> int:
        return self._model.rowCount()

    def _out_get(self) -> int:
        return sum(1 for r in self._all if r["state"] == DeploymentState.OUT.value)

    def _filter_get(self) -> str:
        return self._filter

    def _can_deploy_get(self) -> bool:
        return self._session.can("deployment.create")

    def _can_return_get(self) -> bool:
        return self._session.can("deployment.return")

    def _choices_get(self) -> dict[str, Any]:
        return dict(self._choices)

    def _readiness_get(self) -> dict[str, Any]:
        return self._readiness

    def _detail_get(self) -> dict[str, Any]:
        return self._detail

    def _conditions_get(self) -> list[dict[str, str]]:
        return list(CONDITIONS)

    model = Property(QObject, _model_get, constant=True)
    error = Property(str, _error_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    outCount = Property(int, _out_get, notify=changed)  # noqa: N815
    filter = Property(str, _filter_get, notify=changed)
    canDeploy = Property(bool, _can_deploy_get, notify=changed)  # noqa: N815
    canReturn = Property(bool, _can_return_get, notify=changed)  # noqa: N815
    choices = Property(dict, _choices_get, notify=choicesChanged)
    readiness = Property(dict, _readiness_get, notify=readinessChanged)
    detail = Property(dict, _detail_get, notify=detailChanged)
    conditions = Property(list, _conditions_get, constant=True)

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

        self._tasks.submit(work, done, self._fail)

    def _apply_filter(self) -> None:
        rows = [r for r in self._all if self._filter == "all" or r["state"] in {"out", "pending"}]
        self._model.reset(rows)
        self.changed.emit()

    # ------------------------------------------------------------------ list

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("project.view"):
            return
        actor = self._session.actor()

        def work() -> list[dict[str, Any]]:
            projects = {p.id: p for p in self._sv.projects.list_projects(actor)}
            people = {u.id: u.full_name for u in self._sv.users.crew_directory(actor)}
            tags = {s.asset.id: s.asset.asset_tag for s in self._sv.registry.summaries(actor)}
            rows = []
            for d in self._sv.deployments.list_deployments(actor):
                project = projects.get(d.project_id)
                kind, label = DEPLOYMENT_STATE[d.state]
                items = ", ".join(tags.get(a, "?") for a in d.asset_ids)
                rows.append(
                    {
                        "deploymentId": str(d.id),
                        "version": d.version,
                        "projectId": str(d.project_id),
                        "project": f"{project.code} · {project.name}" if project else "Removed",
                        "deployedOn": f"{d.deployed_on:%d %b %Y}",
                        "items": f"{len(d.asset_ids)} items: {items}",
                        "crew": ", ".join(people.get(c, "Former user") for c in d.crew_ids),
                        "gcp": d.gcp_quantity,
                        "stateKind": kind,
                        "stateLabel": label,
                        "state": d.state.value,
                        "search": f"{project.code if project else ''} {items}".lower(),
                    }
                )
            return rows

        def done(rows: list[dict[str, Any]]) -> None:
            self._all = rows
            self._apply_filter()

        self._tasks.submit(work, done, self._fail)

    @Slot(str)
    def setFilter(self, value: str) -> None:  # noqa: N802
        self._filter = value
        self._apply_filter()

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    # ------------------------------------------------------------------ checkout

    @Slot()
    def loadChoices(self) -> None:  # noqa: N802
        """Everything the checkout sheet offers: projects, kits, equipment, crew, stores."""
        actor = self._session.actor()
        today = self._sv.clock.today()

        def work() -> dict[str, list[dict[str, Any]]]:
            projects = [
                {"value": str(p.id), "label": f"{p.code} · {p.name}"}
                for p in self._sv.projects.list_projects(actor)
                if p.is_open
            ]
            summaries = self._sv.registry.summaries(actor)
            in_kit = {s.asset.id for s in summaries if s.kit_code}
            equipment = [
                {
                    "value": str(s.asset.id),
                    "label": s.asset.asset_tag,
                    "detail": s.item_type.name,
                    "kind": SERVICEABILITY[s.status.serviceability][0],
                    "status": SERVICEABILITY[s.status.serviceability][1],
                    "kit": s.kit_code or "",
                }
                for s in sorted(summaries, key=lambda s: s.asset.asset_tag)
                if s.status.custody in {Custody.IN_STORE, Custody.RESERVED}
                and not s.item_type.is_component
                and s.asset.id not in in_kit
            ]
            kits = []
            for overview in self._sv.kits.list_kits(actor):
                missing = (
                    sum(overview.completeness.missing.values()) if overview.completeness else 0
                )
                kits.append(
                    {
                        "value": str(overview.kit.id),
                        "label": overview.kit.code,
                        "detail": f"{overview.kit.name} · {len(overview.members)} items"
                        + (f" · {missing} missing" if missing else ""),
                    }
                )
            crew = [
                {
                    "value": str(u.id),
                    "label": u.full_name,
                    "detail": f"{u.role.value.title()} · {licence_text(u, today)}",
                }
                for u in sorted(self._sv.users.crew_directory(actor), key=lambda u: u.full_name)
            ]
            gcp = next(
                (
                    t
                    for t in self._sv.catalogue.list_item_types(actor)
                    if not t.is_individually_tracked
                ),
                None,
            )
            stock = position(self._sv.stock.movements(actor, gcp.id)) if gcp else None
            stores = [
                {
                    "value": str(s.id),
                    "label": f"{s.label} ({stock.on_hand_at(s.id) if stock else 0} on hand)",
                }
                for s in self._sv.sites.list_sites(actor)
                if stock and stock.on_hand_at(s.id) > 0
            ]
            return {
                "projects": projects,
                "kits": kits,
                "equipment": equipment,
                "crew": crew,
                "stores": [{"value": "", "label": "No GCP banners"}, *stores],
                "sites": [
                    {"value": str(s.id), "label": s.label} for s in self._sv.sites.list_sites(actor)
                ],
            }

        def done(choices: dict[str, list[dict[str, Any]]]) -> None:
            self._choices = choices
            self.choicesChanged.emit()

        self._tasks.submit(work, done, self._fail)

    def _draft(self, values: dict[str, Any]) -> dict[str, Any]:
        return {
            "asset_ids": [AssetId(a) for a in _ids(values.get("assetIds"))],
            "kit_ids": [KitId(k) for k in _ids(values.get("kitIds"))],
            "crew_ids": [UserId(u) for u in _ids(values.get("crewIds"))],
            "gcp_quantity": _count(values.get("gcpQuantity"), "GCP banners"),
            "gcp_site_id": LocationId(s) if (s := _id(values.get("gcpSiteId"))) else None,
        }

    @Slot(dict)
    def check(self, values: dict[str, Any]) -> None:
        """Runs the readiness check for the checkout sheet; the newest request wins."""
        fields = values.copy()
        actor = self._session.actor()
        self._check_serial += 1
        serial = self._check_serial

        def work() -> dict[str, Any]:
            try:
                draft = self._draft(fields)
            except RuleViolation as exc:
                return {"blockers": list(exc.problems), "warnings": [], "items": 0, "ready": False}
            day = optional_date(fields, "deployedOn")
            report = self._sv.deployments.readiness(actor, day=day, **draft)
            return {
                "blockers": list(report.readiness.blockers),
                "warnings": list(report.readiness.warnings),
                "items": len(report.asset_ids),
                "gcpAvailable": report.gcp_available,
                "ready": report.readiness.ok,
            }

        def done(result: dict[str, Any]) -> None:
            if serial == self._check_serial:
                self._readiness = result
                self.readinessChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot(dict)
    def deploy(self, values: dict[str, Any]) -> None:
        fields = values.copy()

        def work() -> None:
            project = _id(fields.get("projectId"))
            if project is None:
                raise RuleViolation("Choose the project.")
            self._sv.deployments.deploy(
                self._session.context(),
                project_id=ProjectId(project),
                deployed_on=optional_date(fields, "deployedOn"),
                notes=text(fields, "notes"),
                **self._draft(fields),
            )

        self._run(work, "Equipment checked out")

    # ------------------------------------------------------------------ return

    @Slot(str)
    def openDeployment(self, deployment_id: str) -> None:  # noqa: N802
        actor = self._session.actor()

        def work() -> dict[str, Any]:
            d = self._sv.deployments.get(actor, DeploymentId(uuid.UUID(deployment_id)))
            project = self._sv.projects.get(actor, d.project_id)
            summaries = {s.asset.id: s for s in self._sv.registry.summaries(actor)}
            people = {u.id: u.full_name for u in self._sv.users.crew_directory(actor)}
            returns = {r.asset_id: r for r in d.returns}
            kind, label = DEPLOYMENT_STATE[d.state]
            items = []
            for asset_id in d.asset_ids:
                s = summaries.get(asset_id)
                back = returns.get(asset_id)
                items.append(
                    {
                        "assetId": str(asset_id),
                        "tag": s.asset.asset_tag if s else "?",
                        "type": s.item_type.name if s else "",
                        "serviceKind": SERVICEABILITY[s.status.serviceability][0]
                        if s
                        else "neutral",
                        "serviceLabel": SERVICEABILITY[s.status.serviceability][1] if s else "",
                        "returned": back.condition.value if back else "",
                        "returnNote": back.note if back else "",
                    }
                )
            sites = {s.id: s.label for s in self._sv.sites.list_sites(actor, include_deleted=True)}
            return {
                "deploymentId": str(d.id),
                "version": d.version,
                "project": f"{project.code} · {project.name}",
                "deployedOn": f"{d.deployed_on:%d %b %Y}",
                "returnedOn": f"{d.returned_on:%d %b %Y}" if d.returned_on else "",
                "state": d.state.value,
                "stateKind": kind,
                "stateLabel": label,
                "crew": ", ".join(people.get(c, "Former user") for c in d.crew_ids),
                "items": items,
                "gcp": d.gcp_quantity,
                "gcpFrom": sites.get(d.gcp_site_id, "") if d.gcp_site_id else "",
                "gcpSiteId": str(d.gcp_site_id) if d.gcp_site_id else "",
                "gcpReturned": d.gcp_returned,
                "gcpConsumed": d.gcp_consumed,
                "failure": d.failure,
                "notes": d.notes,
                "canReturn": d.state is DeploymentState.OUT,
            }

        def done(detail: dict[str, Any]) -> None:
            self._detail = detail
            self.detailChanged.emit()

        self._tasks.submit(work, done, self._fail)

    @Slot(str, int, dict)
    def returnEquipment(self, deployment_id: str, version: int, values: dict[str, Any]) -> None:  # noqa: N802
        fields = values.copy()

        def work() -> None:
            lines = [
                ReturnLine.build(
                    asset_id=AssetId(uuid.UUID(str(line["assetId"]))),
                    condition=ReturnCondition(str(line.get("condition") or "ok")),
                    note=str(line.get("note") or ""),
                )
                for line in fields.get("lines") or []
            ]
            issued = _count(fields.get("gcpIssued"), "GCP banners")
            returned = _count(fields.get("gcpReturned"), "GCP banners returned")
            site = _id(fields.get("returnSiteId"))
            self._sv.deployments.return_equipment(
                self._session.context(),
                DeploymentId(uuid.UUID(deployment_id)),
                version,
                lines=lines,
                gcp_returned=returned,
                gcp_consumed=max(0, issued - returned),
                return_site_id=LocationId(site) if site else None,
                returned_on=optional_date(fields, "returnedOn"),
            )
            self._detail = {}

        self._run(work, "Equipment returned")
