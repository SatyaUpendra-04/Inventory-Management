"""Projects: create, edit, open and close survey jobs, and summarise what happened on them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.common.errors import ConflictError, NotFound, RuleViolation
from ims.domain.common.ids import LocationId, ProjectId, UserId
from ims.domain.identity.roles import Permission
from ims.domain.identity.user import User
from ims.domain.operations.deployment import Deployment, DeploymentState
from ims.domain.operations.field_logs import Sortie, SurveySession
from ims.domain.operations.project import (
    Project,
    ProjectStatus,
    check_project_crew,
    check_transition,
)
from ims.domain.sites.site import Site
from ims.ports.clock import Clock
from ims.ports.repository import Storage

PROJECT_FIELDS = frozenset(
    {"code", "name", "site_id", "client", "starts_on", "ends_on", "chief_pilot_id",
     "surveyor_id", "notes"}
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class ProjectTotals:
    flights: int
    flight_hours: Decimal
    sessions: int
    survey_hours: Decimal
    area_ha: Decimal
    points: int
    gcp_issued: int
    gcp_returned: int
    gcp_consumed: int
    open_deployments: int


@dataclass(frozen=True, slots=True)
class ProjectOverview:
    project: Project
    site: Site | None
    chief_pilot: User | None
    surveyor: User | None
    deployments: list[Deployment]
    sorties: list[Sortie]
    sessions: list[SurveySession]
    totals: ProjectTotals


@dataclass(frozen=True, slots=True)
class MyWork:
    """One person's part in a project: how they are involved and what they logged."""

    roles: tuple[str, ...]  # "Chief pilot", "Lead surveyor", "Crew"
    flights: int
    flight_hours: Decimal
    sessions: int
    survey_hours: Decimal


def project_totals(
    deployments: list[Deployment], sorties: list[Sortie], sessions: list[SurveySession]
) -> ProjectTotals:
    flights = [s for s in sorties if not s.is_void]
    surveys = [s for s in sessions if not s.is_void]
    went_out = [
        d for d in deployments if d.state in {DeploymentState.OUT, DeploymentState.RETURNED}
    ]
    return ProjectTotals(
        flights=len(flights),
        flight_hours=sum((s.hours for s in flights), Decimal(0)),
        sessions=len(surveys),
        survey_hours=sum((s.hours for s in surveys), Decimal(0)),
        area_ha=sum((s.area_ha or Decimal(0) for s in surveys), Decimal(0)),
        points=sum(s.points for s in surveys),
        gcp_issued=sum(d.gcp_quantity for d in went_out),
        gcp_returned=sum(d.gcp_returned for d in went_out),
        gcp_consumed=sum(d.gcp_consumed for d in went_out),
        open_deployments=sum(1 for d in deployments if d.is_open),
    )


class ProjectService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ queries

    def list_projects(self, actor: Actor) -> list[Project]:
        actor.require(Permission.PROJECT_VIEW)
        return self._s.projects.list()

    def get(self, actor: Actor, project_id: ProjectId) -> Project:
        actor.require(Permission.PROJECT_VIEW)
        return self._require(project_id)

    def overview(self, actor: Actor, project_id: ProjectId) -> ProjectOverview:
        actor.require(Permission.PROJECT_VIEW)
        project = self._require(project_id)
        deployments = self._s.deployments.for_project(project_id)
        sorties = self._s.sorties.for_project(project_id)
        sessions = self._s.survey_sessions.for_project(project_id)
        return ProjectOverview(
            project=project,
            site=self._s.sites.get(project.site_id),
            chief_pilot=self._s.users.get(project.chief_pilot_id)
            if project.chief_pilot_id
            else None,
            surveyor=self._s.users.get(project.surveyor_id) if project.surveyor_id else None,
            deployments=deployments,
            sorties=sorties,
            sessions=sessions,
            totals=project_totals(deployments, sorties, sessions),
        )

    def totals(self, actor: Actor) -> dict[ProjectId, ProjectTotals]:
        """Totals for every project, for the list."""
        actor.require(Permission.PROJECT_VIEW)
        deployments: dict[ProjectId, list[Deployment]] = {}
        sorties: dict[ProjectId, list[Sortie]] = {}
        sessions: dict[ProjectId, list[SurveySession]] = {}
        for d in self._s.deployments.list():
            deployments.setdefault(d.project_id, []).append(d)
        for s in self._s.sorties.list():
            sorties.setdefault(s.project_id, []).append(s)
        for v in self._s.survey_sessions.list():
            sessions.setdefault(v.project_id, []).append(v)
        return {
            p.id: project_totals(
                deployments.get(p.id, []), sorties.get(p.id, []), sessions.get(p.id, [])
            )
            for p in self._s.projects.list()
        }

    def my_work(self, actor: Actor) -> dict[ProjectId, MyWork]:
        """Projects the signed-in person is part of: named on the project, in a crew that
        took equipment out, or the pilot or surveyor on a log."""
        actor.require(Permission.PROJECT_VIEW)
        me = actor.user_id
        roles: dict[ProjectId, list[str]] = {}

        def add(project_id: ProjectId, role: str) -> None:
            if role not in roles.setdefault(project_id, []):
                roles[project_id].append(role)

        for p in self._s.projects.list():
            if p.chief_pilot_id == me:
                add(p.id, "Chief pilot")
            if p.surveyor_id == me:
                add(p.id, "Lead surveyor")
        for d in self._s.deployments.list():
            if me in d.crew_ids and d.state is not DeploymentState.CANCELLED:
                add(d.project_id, "Crew")
        flights = [s for s in self._s.sorties.list() if s.pilot_id == me and not s.is_void]
        sessions = [
            v for v in self._s.survey_sessions.list() if v.surveyor_id == me and not v.is_void
        ]
        for f in flights:
            add(f.project_id, "Crew")
        for v in sessions:
            add(v.project_id, "Crew")
        result: dict[ProjectId, MyWork] = {}
        for project_id, names in roles.items():
            mine_f = [f for f in flights if f.project_id == project_id]
            mine_s = [v for v in sessions if v.project_id == project_id]
            named = [n for n in names if n != "Crew"]
            result[project_id] = MyWork(
                roles=tuple(named or names),
                flights=len(mine_f),
                flight_hours=sum((f.hours for f in mine_f), Decimal(0)),
                sessions=len(mine_s),
                survey_hours=sum((v.hours for v in mine_s), Decimal(0)),
            )
        return result

    def suggest_code(self, actor: Actor, site_id: LocationId | None, starts_on: date) -> str:
        """e.g. ``PRJ-KJR-2611`` for a Keonjhar mine project starting in November 2026."""
        actor.require(Permission.PROJECT_VIEW)
        site = self._s.sites.get(site_id) if site_id else None
        stem = (site.code.split("-")[0] if site else "SITE")[:8]
        base = f"PRJ-{stem}-{starts_on:%y%m}"
        if self._s.projects.find_by_code(base) is None:
            return base
        n = 2
        while self._s.projects.find_by_code(f"{base}-{n}") is not None:
            n += 1
        return f"{base}-{n}"

    # ------------------------------------------------------------------ commands

    def create(self, ctx: CommandContext, **fields: Any) -> ProjectId:
        ctx.require_actor().require(Permission.PROJECT_MANAGE)
        _check_fields(fields)
        project_id = ProjectId(ctx.derive("project"))

        def execute() -> Outcome:
            project = Project.build(id=project_id, **fields)
            if self._s.projects.get(project_id) is None:
                self._check(project)
            add_once(self._s.projects.add, project)
            return Outcome("project", str(project_id), None, project.model_dump(mode="json"))

        self._run.run(ctx, "project.create", execute)
        return project_id

    def update(
        self, ctx: CommandContext, project_id: ProjectId, expected_version: int, **changes: Any
    ) -> ProjectId:
        ctx.require_actor().require(Permission.PROJECT_MANAGE)
        _check_fields(changes)

        def execute() -> Outcome:
            stored = self._require(project_id)
            candidate = stored.next_version(**changes)
            if stored.version == expected_version + 1 and _same(stored, candidate):
                return Outcome("project", str(project_id), None, stored.model_dump(mode="json"))
            if stored.version != expected_version:
                raise ConflictError(
                    "This project was changed by someone else. Reload and try again."
                )
            if (
                "site_id" in changes
                and changes["site_id"] != stored.site_id
                and (self._s.deployments.for_project(project_id))
            ):
                raise RuleViolation("The site cannot change once equipment has gone out.")
            self._check(candidate)
            update_once(
                self._s.projects.update, lambda: self._s.projects.get(project_id), candidate
            )
            return Outcome(
                "project", str(project_id), stored.model_dump(mode="json"),
                candidate.model_dump(mode="json"),
            )  # fmt: skip

        self._run.run(ctx, "project.update", execute)
        return project_id

    def set_status(
        self, ctx: CommandContext, project_id: ProjectId, expected_version: int,
        status: ProjectStatus,
    ) -> ProjectId:  # fmt: skip
        """Complete, cancel, reopen or reinstate a project."""
        ctx.require_actor().require(Permission.PROJECT_MANAGE)

        def execute() -> Outcome:
            stored = self._require(project_id)
            if stored.version == expected_version + 1 and stored.status is status:
                return Outcome("project", str(project_id), None, {"status": status.value})
            if stored.version != expected_version:
                raise ConflictError(
                    "This project was changed by someone else. Reload and try again."
                )
            open_count = sum(1 for d in self._s.deployments.for_project(project_id) if d.is_open)
            check_transition(stored, status, open_deployments=open_count)
            after = stored.next_version(status=status)
            update_once(self._s.projects.update, lambda: self._s.projects.get(project_id), after)
            return Outcome(
                "project", str(project_id), {"status": stored.status.value},
                {"status": status.value},
            )  # fmt: skip

        self._run.run(ctx, f"project.{status.value}", execute)
        return project_id

    def remove(self, ctx: CommandContext, project_id: ProjectId, expected_version: int) -> None:
        """Removes a project that never had equipment out (kept for the audit trail)."""
        ctx.require_actor().require(Permission.PROJECT_MANAGE)

        def execute() -> Outcome:
            stored = self._require_any(project_id)
            if stored.is_deleted:
                return Outcome("project", str(project_id), None, None)
            if stored.version != expected_version:
                raise ConflictError(
                    "This project was changed by someone else. Reload and try again."
                )
            if self._s.deployments.for_project(project_id):
                raise RuleViolation(
                    "Equipment has gone out on this project, so it is kept; cancel or "
                    "complete it instead."
                )
            after = stored.next_version(deleted_at=self._clock.now())
            update_once(self._s.projects.update, lambda: self._s.projects.get(project_id), after)
            return Outcome("project", str(project_id), stored.model_dump(mode="json"), None)

        self._run.run(ctx, "project.remove", execute)

    # ------------------------------------------------------------------ helpers

    def _require_any(self, project_id: ProjectId) -> Project:
        project = self._s.projects.get(project_id)
        if project is None:
            raise NotFound("Project not found.")
        return project

    def _require(self, project_id: ProjectId) -> Project:
        project = self._require_any(project_id)
        if project.is_deleted:
            raise NotFound("Project not found.")
        return project

    def _check(self, project: Project) -> None:
        problems: list[str] = []
        other = self._s.projects.find_by_code(project.code)
        if other is not None and other.id != project.id:
            problems.append(f"Project code {project.code} is already in use.")
        site = self._s.sites.get(project.site_id)
        if site is None or site.is_deleted:
            problems.append("Choose an existing site.")
        if problems:
            raise RuleViolation(problems)
        check_project_crew(
            self._user(project.chief_pilot_id), self._user(project.surveyor_id), project.starts_on
        )

    def _user(self, user_id: UserId | None) -> User | None:
        if user_id is None:
            return None
        user = self._s.users.get(user_id)
        if user is None:
            raise NotFound("Person not found.")
        return user


def _check_fields(fields: dict[str, Any]) -> None:
    unknown = set(fields) - PROJECT_FIELDS
    if unknown:
        raise RuleViolation(f"These fields cannot be set here: {', '.join(sorted(unknown))}.")


def _same(a: Project, b: Project) -> bool:
    return a.model_dump(exclude={"version"}) == b.model_dump(exclude={"version"})
