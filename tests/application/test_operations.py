"""Projects, deployments, field logs and returns: the whole project cycle."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from ims.application.context import CommandContext
from ims.application.deployments import DeploymentService
from ims.application.runner import CommandRunner
from ims.domain.assets.catalogue import DEFAULT_CATALOGUE, Meter
from ims.domain.assets.documents import DocumentKind
from ims.domain.assets.status import Custody, Serviceability, StatusChange
from ims.domain.common.errors import (
    ConflictError,
    InvalidTransition,
    NotFound,
    PermissionDenied,
    RuleViolation,
)
from ims.domain.common.ids import AssetId, LocationId
from ims.domain.identity.user import PilotLicence
from ims.domain.operations.deployment import DeploymentState, ReturnCondition, ReturnLine
from ims.domain.operations.field_logs import SurveyMode
from ims.domain.operations.project import ProjectStatus
from ims.domain.sites.site import SiteKind
from ims.domain.stock.ledger import MovementKind
from ims.domain.usage.ledger import UsageSource
from tests.application.conftest import App

TYPES = {t.code: t for t in DEFAULT_CATALOGUE}
GCP = TYPES["GCP_BANNER"].id
TODAY = date(2026, 11, 8)


def register(app: App, code: str, tag: str) -> AssetId:
    item_type = TYPES[code]
    serial = f"SN-{tag}" if item_type.tracking.value == "serialized" else None
    return app.assets.register(
        app.ctx(app.admin), item_type_id=item_type.id, asset_tag=tag, serial_number=serial
    )


def make_compliant(app: App, drone: AssetId) -> None:
    app.registry.add_document(app.ctx(app.admin), drone, kind=DocumentKind.UIN, reference="UA-1")
    app.registry.add_document(
        app.ctx(app.admin),
        drone,
        kind=DocumentKind.INSURANCE,
        reference="POL-1",
        valid_until=TODAY + timedelta(days=200),
    )


class Fleet:
    """A store, a mine site, a drone kit's worth of equipment and some GCP banners."""

    def __init__(self, app: App) -> None:
        self.store = app.sites.create(
            app.ctx(app.admin), code="MAIN-STORE", name="Main store", kind=SiteKind.STORE
        )
        self.mine = app.sites.create(
            app.ctx(app.admin), code="KJR-MINE", name="Keonjhar mine", kind=SiteKind.MINE_SITE
        )
        self.drone = register(app, "DRONE_AIRFRAME", "DRN-0001")
        self.motor = register(app, "MOTOR", "MOT-0001")
        app.registry.install(app.ctx(app.admin), self.motor, self.drone, "Motor 1")
        self.bat1 = register(app, "DRONE_BATTERY", "BAT-0001")
        self.bat2 = register(app, "DRONE_BATTERY", "BAT-0002")
        self.sd = register(app, "SD_CARD", "SDC-0001")
        self.base = register(app, "GNSS_RECEIVER", "GNS-0001")
        self.rover = register(app, "GNSS_RECEIVER", "GNS-0002")
        self.tripod = register(app, "TRIPOD", "TRP-0001")
        make_compliant(app, self.drone)
        for receiver in (self.base, self.rover):
            app.registry.add_document(
                app.ctx(app.admin),
                receiver,
                kind=DocumentKind.CALIBRATION,
                reference="CAL-1",
                valid_until=TODAY + timedelta(days=300),
            )
        app.stock.record(
            app.ctx(app.admin),
            item_type_id=GCP,
            location_id=self.store,
            kind=MovementKind.RECEIVED,
            quantity=50,
            reason="PO-1",
        )
        self.project = app.projects.create(
            app.ctx(app.admin),
            code="kjr-2611",
            name="Keonjhar pit survey",
            site_id=self.mine,
            starts_on=TODAY,
            chief_pilot_id=app.pilot.id,
            surveyor_id=app.surveyor.id,
        )

    @property
    def equipment(self) -> list[AssetId]:
        return [self.drone, self.bat1, self.bat2, self.sd, self.base, self.rover, self.tripod]


@pytest.fixture
def fleet(app: App) -> Fleet:
    return Fleet(app)


def status(app: App, asset: AssetId) -> tuple[Serviceability, Custody]:
    s = app.assets.status(app.actor(app.admin), asset)
    return s.serviceability, s.custody


def deploy(app: App, fleet: Fleet, ctx: CommandContext | None = None, **extra: Any) -> Any:
    values: dict[str, Any] = {
        "project_id": fleet.project,
        "asset_ids": fleet.equipment,
        "crew_ids": [app.pilot.id, app.surveyor.id],
        "gcp_quantity": 20,
        "gcp_site_id": fleet.store,
    }
    values.update(extra)
    return app.deployments.deploy(ctx or app.ctx(app.pilot), **values)


# ---------------------------------------------------------------------- projects


class TestProjects:
    def test_create_edit_and_codes(self, app: App, fleet: Fleet) -> None:
        project = app.projects.get(app.actor(app.surveyor), fleet.project)
        assert project.code == "PRJ-KJR-2611" and project.status is ProjectStatus.PLANNED
        assert (
            app.projects.suggest_code(app.actor(app.admin), fleet.mine, TODAY) == "PRJ-KJR-2611-2"
        )
        assert app.projects.suggest_code(app.actor(app.admin), None, TODAY) == "PRJ-SITE-2611"
        with pytest.raises(RuleViolation, match="already in use"):
            app.projects.create(
                app.ctx(app.admin),
                code="PRJ-KJR-2611",
                name="Again",
                site_id=fleet.mine,
                starts_on=TODAY,
            )
        with pytest.raises(RuleViolation, match="end date"):
            app.projects.create(
                app.ctx(app.admin),
                code="X1",
                name="Bad",
                site_id=fleet.mine,
                starts_on=TODAY,
                ends_on=TODAY - timedelta(days=1),
            )
        with pytest.raises(RuleViolation, match="cannot be set"):
            app.projects.create(
                app.ctx(app.admin),
                code="X2",
                name="Bad",
                site_id=fleet.mine,
                starts_on=TODAY,
                status="active",
            )
        with pytest.raises(PermissionDenied):
            app.projects.create(
                app.ctx(app.pilot), code="X3", name="No", site_id=fleet.mine, starts_on=TODAY
            )
        app.projects.update(app.ctx(app.admin), fleet.project, 1, client="Odisha Mining Corp")
        with pytest.raises(ConflictError):
            app.projects.update(app.ctx(app.admin), fleet.project, 1, client="Stale")
        assert app.projects.get(app.actor(app.admin), fleet.project).client == "Odisha Mining Corp"

    def test_chief_pilot_needs_a_valid_certificate(self, app: App, fleet: Fleet) -> None:
        with pytest.raises(RuleViolation, match="no DGCA pilot certificate"):
            app.projects.create(
                app.ctx(app.admin),
                code="X4",
                name="No pilot",
                site_id=fleet.mine,
                starts_on=TODAY,
                chief_pilot_id=app.surveyor.id,
            )
        with pytest.raises(RuleViolation, match="expired"):
            app.projects.create(
                app.ctx(app.admin),
                code="X5",
                name="Late",
                site_id=fleet.mine,
                starts_on=date(2031, 1, 1),
                chief_pilot_id=app.pilot.id,
            )
        with pytest.raises(RuleViolation, match="existing site"):
            app.projects.create(
                app.ctx(app.admin),
                code="X6",
                name="Nowhere",
                site_id=LocationId(fleet.project),
                starts_on=TODAY,
            )

    def test_status_changes_and_removal(self, app: App, fleet: Fleet) -> None:
        empty = app.projects.create(
            app.ctx(app.admin), code="X7", name="Empty", site_id=fleet.mine, starts_on=TODAY
        )
        app.projects.set_status(app.ctx(app.admin), empty, 1, ProjectStatus.CANCELLED)
        with pytest.raises(InvalidTransition):
            app.projects.set_status(app.ctx(app.admin), empty, 2, ProjectStatus.COMPLETED)
        app.projects.set_status(app.ctx(app.admin), empty, 2, ProjectStatus.PLANNED)
        app.projects.remove(app.ctx(app.admin), empty, 3)
        with pytest.raises(NotFound):
            app.projects.get(app.actor(app.admin), empty)
        assert [p.code for p in app.projects.list_projects(app.actor(app.pilot))] == [
            "PRJ-KJR-2611"
        ]


# ---------------------------------------------------------------------- full cycle


class TestProjectCycle:
    def test_deploy_fly_survey_return_complete(self, app: App, fleet: Fleet) -> None:
        deployment_id = deploy(app, fleet)
        deployment = app.deployments.get(app.actor(app.pilot), deployment_id)
        assert deployment.state is DeploymentState.OUT
        assert all(status(app, a)[1] is Custody.DEPLOYED for a in fleet.equipment)
        assert app.projects.get(app.actor(app.admin), fleet.project).status is ProjectStatus.ACTIVE
        stock = app.stock.position(app.actor(app.admin), GCP)
        assert stock.on_hand_at(fleet.store) == 30 and stock.outstanding_with(fleet.project) == 20

        # Two flights: usage lands on the drone, its fitted motor, batteries and the PPK base.
        sortie = app.logs.log_sortie(
            app.ctx(app.pilot),
            deployment_id=deployment_id,
            drone_id=fleet.drone,
            pilot_id=app.pilot.id,
            flown_on=TODAY,
            hours=Decimal("0.75"),
            landings=1,
            battery_ids=[fleet.bat1, fleet.bat2],
            media_ids=[fleet.sd],
        )
        app.logs.log_sortie(
            app.ctx(app.pilot),
            deployment_id=deployment_id,
            drone_id=fleet.drone,
            pilot_id=app.pilot.id,
            flown_on=TODAY,
            hours=Decimal("0.5"),
            battery_ids=[fleet.bat1],
            ppk_base_id=fleet.base,
        )
        meters = app.usage.totals(app.actor(app.admin), fleet.drone)
        assert meters == {Meter.HOURS: Decimal("1.25"), Meter.LANDINGS: 2, Meter.CYCLES: 2}
        assert app.usage.totals(app.actor(app.admin), fleet.motor)[Meter.HOURS] == Decimal("1.25")
        assert app.usage.totals(app.actor(app.admin), fleet.bat1)[Meter.CYCLES] == 2
        assert app.usage.totals(app.actor(app.admin), fleet.bat2)[Meter.CYCLES] == 1
        assert app.usage.totals(app.actor(app.admin), fleet.base)[Meter.HOURS] == Decimal("0.5")
        assert [s.id for s in app.logs.flights_with_media(app.actor(app.pilot), fleet.sd)] == [
            sortie
        ]

        # A survey session: base and rover each gain the session's hours.
        app.logs.log_session(
            app.ctx(app.surveyor),
            deployment_id=deployment_id,
            surveyor_id=app.surveyor.id,
            surveyed_on=TODAY,
            hours=Decimal("3"),
            mode=SurveyMode.PPK,
            base_id=fleet.base,
            rover_ids=[fleet.rover],
            area_ha=Decimal("42.5"),
            points=380,
            fix_rate=Decimal("97.5"),
        )
        assert app.usage.totals(app.actor(app.admin), fleet.base)[Meter.HOURS] == Decimal("3.5")
        assert app.usage.totals(app.actor(app.admin), fleet.rover)[Meter.HOURS] == Decimal("3")

        # A wrong flight is voided: its usage is reversed exactly.
        wrong = app.storage.sorties.get(sortie)
        assert wrong is not None
        with pytest.raises(PermissionDenied):
            app.logs.void_sortie(app.ctx(app.pilot), sortie, 1, "Duplicate")
        with pytest.raises(RuleViolation, match="reason"):
            app.logs.void_sortie(app.ctx(app.admin), sortie, 1, " ")
        app.logs.void_sortie(app.ctx(app.admin), sortie, 1, "Logged twice")
        assert app.usage.totals(app.actor(app.admin), fleet.drone)[Meter.HOURS] == Decimal("0.5")
        assert app.usage.totals(app.actor(app.admin), fleet.bat2)[Meter.CYCLES] == 0
        assert app.logs.flights_with_media(app.actor(app.pilot), fleet.sd) == []
        app.logs.void_sortie(app.ctx(app.admin), sortie, 1, "Again")  # already void: no-op

        overview = app.projects.overview(app.actor(app.admin), fleet.project)
        assert overview.totals.flights == 1 and overview.totals.flight_hours == Decimal("0.5")
        assert overview.totals.sessions == 1 and overview.totals.area_ha == Decimal("42.5")
        assert overview.totals.open_deployments == 1 and overview.totals.gcp_issued == 20
        assert overview.chief_pilot == app.pilot and overview.site is not None

        # The project cannot close while equipment is out.
        with pytest.raises(InvalidTransition, match="Return all equipment"):
            app.projects.set_status(app.ctx(app.admin), fleet.project, 2, ProjectStatus.COMPLETED)

        # Return: the battery has a deferred defect, the rover is damaged.
        lines = [
            ReturnLine(asset_id=a) for a in fleet.equipment if a not in {fleet.bat2, fleet.rover}
        ]
        lines += [
            ReturnLine(
                asset_id=fleet.bat2, condition=ReturnCondition.LIMITED, note="Slight swelling"
            ),
            ReturnLine(
                asset_id=fleet.rover, condition=ReturnCondition.GROUNDED, note="Cracked housing"
            ),
        ]
        with pytest.raises(RuleViolation, match="add up"):
            app.deployments.return_equipment(
                app.ctx(app.pilot),
                deployment_id,
                deployment.version,
                lines=lines,
                gcp_returned=10,
                gcp_consumed=5,
                return_site_id=fleet.store,
            )
        with pytest.raises(RuleViolation, match="every item"):
            app.deployments.return_equipment(
                app.ctx(app.pilot),
                deployment_id,
                deployment.version,
                lines=lines[1:],
                gcp_returned=15,
                gcp_consumed=5,
                return_site_id=fleet.store,
            )
        ctx = app.ctx(app.pilot)
        app.deployments.return_equipment(
            ctx,
            deployment_id,
            deployment.version,
            lines=lines,
            gcp_returned=15,
            gcp_consumed=5,
            return_site_id=fleet.store,
        )
        app.deployments.return_equipment(
            ctx,
            deployment_id,
            deployment.version,
            lines=lines,
            gcp_returned=15,
            gcp_consumed=5,
            return_site_id=fleet.store,
        )
        assert status(app, fleet.drone) == (Serviceability.SERVICEABLE, Custody.IN_STORE)
        assert status(app, fleet.bat2) == (Serviceability.LIMITED, Custody.IN_STORE)
        assert status(app, fleet.rover) == (Serviceability.UNSERVICEABLE, Custody.IN_MAINTENANCE)
        stock = app.stock.position(app.actor(app.admin), GCP)
        assert stock.on_hand_at(fleet.store) == 45 and stock.outstanding_with(fleet.project) == 0
        returned = app.deployments.get(app.actor(app.admin), deployment_id)
        assert returned.state is DeploymentState.RETURNED and returned.gcp_consumed == 5

        # Logs can still be added after the return (dated within the deployment).
        app.logs.log_sortie(
            app.ctx(app.pilot),
            deployment_id=deployment_id,
            drone_id=fleet.drone,
            pilot_id=app.pilot.id,
            flown_on=TODAY,
            hours=Decimal("0.25"),
        )
        project = app.projects.get(app.actor(app.admin), fleet.project)
        app.projects.set_status(
            app.ctx(app.admin), fleet.project, project.version, ProjectStatus.COMPLETED
        )
        with pytest.raises(RuleViolation, match="is completed"):
            deploy(app, fleet, asset_ids=[fleet.tripod], gcp_quantity=0)

    def test_retrying_a_deployment_is_safe(self, app: App, fleet: Fleet) -> None:
        ctx = app.ctx(app.pilot)
        first = deploy(app, fleet, ctx)
        assert deploy(app, fleet, ctx) == first
        assert app.stock.position(app.actor(app.admin), GCP).on_hand_at(fleet.store) == 30


# ---------------------------------------------------------------------- readiness


class TestReadiness:
    def check(self, app: App, fleet: Fleet, **values: Any) -> list[str]:
        report = app.deployments.readiness(app.actor(app.pilot), **values)
        return report.readiness.blockers

    def test_a_ready_deployment(self, app: App, fleet: Fleet) -> None:
        report = app.deployments.readiness(
            app.actor(app.pilot),
            asset_ids=fleet.equipment,
            crew_ids=[app.pilot.id],
            gcp_quantity=10,
            gcp_site_id=fleet.store,
        )
        assert report.readiness.ok and report.gcp_available == 50

    def test_blockers(self, app: App, fleet: Fleet) -> None:
        app.assets.change_status(
            app.ctx(app.admin),
            fleet.bat1,
            StatusChange(serviceability=Serviceability.UNSERVICEABLE, reason="Puffed"),
        )
        app.assets.change_status(
            app.ctx(app.admin),
            fleet.motor,
            StatusChange(serviceability=Serviceability.UNSERVICEABLE, reason="Bearing"),
        )
        undocumented = register(app, "DRONE_AIRFRAME", "DRN-0002")
        blockers = self.check(
            app,
            fleet,
            asset_ids=[fleet.drone, fleet.bat1, undocumented],
            crew_ids=[app.surveyor.id],
            gcp_quantity=80,
            gcp_site_id=fleet.store,
        )
        text = " | ".join(blockers)
        assert "BAT-0001 (Drone flight battery) is grounded" in text
        assert "fitted motor MOT-0001 is grounded" in text
        assert "DRN-0002: UIN (Digital Sky) missing" in text
        assert "needs a pilot with a valid DGCA certificate" in text
        assert "Only 50 GCP banners" in text
        assert self.check(app, fleet) == ["Choose the equipment to take.", "Choose the crew."]
        assert "Choose the store" in " ".join(
            self.check(
                app,
                fleet,
                asset_ids=[fleet.tripod],
                crew_ids=[app.surveyor.id],
                gcp_quantity=5,
            )
        )

    def test_expired_pilot_and_already_deployed(self, app: App, fleet: Fleet) -> None:
        expired = app.pilot.next_version(
            licence=PilotLicence(number="RPC-OLD-1", expires_on=TODAY - timedelta(days=1))
        )
        app.storage.users.update(expired)
        blockers = self.check(app, fleet, asset_ids=[fleet.drone], crew_ids=[app.pilot.id])
        assert any("certificate has expired" in b for b in blockers)
        app.storage.users.update(
            expired.next_version(
                licence=PilotLicence(number="RPC-NEW-1", expires_on=TODAY + timedelta(days=10))
            )
        )
        report = app.deployments.readiness(
            app.actor(app.admin), asset_ids=[fleet.drone], crew_ids=[app.pilot.id]
        )
        assert report.readiness.ok and any("expires on" in w for w in report.readiness.warnings)
        deploy(app, fleet, asset_ids=[fleet.tripod], gcp_quantity=0)
        assert any(
            "already deployed" in b
            for b in self.check(app, fleet, asset_ids=[fleet.tripod], crew_ids=[app.surveyor.id])
        )
        with pytest.raises(RuleViolation, match="already deployed"):
            deploy(app, fleet, asset_ids=[fleet.tripod], gcp_quantity=0)
        with pytest.raises(RuleViolation, match="future"):
            deploy(
                app,
                fleet,
                asset_ids=[fleet.sd],
                gcp_quantity=0,
                deployed_on=TODAY + timedelta(days=1),
            )

    def test_kits_are_expanded_and_checked(self, app: App, fleet: Fleet) -> None:
        app.kits.install_default_templates(app.ctx(app.admin))
        template = next(t for t in app.kits.templates(app.actor(app.admin)) if t.name == "DGPS set")
        kit = app.kits.create(
            app.ctx(app.admin), code="dgps-01", name="DGPS 1", template_id=template.id
        )
        stored = app.storage.kits.get(kit)
        assert stored is not None
        app.kits.add_member(app.ctx(app.admin), kit, stored.version, fleet.base)
        report = app.deployments.readiness(
            app.actor(app.pilot),
            kit_ids=[kit],
            asset_ids=[fleet.tripod],
            crew_ids=[app.surveyor.id],
        )
        assert report.asset_ids == [fleet.base, fleet.tripod]
        assert report.readiness.ok and report.readiness.warnings == ["KIT-DGPS-01 is incomplete."]


# ---------------------------------------------------------------------- compensation


class _FailingStatusEvents:
    """Refuses the n-th status event, as if someone else changed that asset first."""

    def __init__(self, inner: Any, fail_on: int) -> None:
        self._inner, self._fail_on, self._count = inner, fail_on, 0

    def for_asset(self, asset_id: AssetId) -> Any:
        return self._inner.for_asset(asset_id)

    def append(self, event: Any) -> None:
        self._count += 1
        if self._count == self._fail_on:
            raise ConflictError("Someone else recorded a change first. Reload and try again.")
        self._inner.append(event)


class TestCompensation:
    def test_a_refused_step_undoes_the_whole_deployment(self, app: App, fleet: Fleet) -> None:
        failing = replace(
            app.storage, status_events=_FailingStatusEvents(app.storage.status_events, 3)
        )
        service = DeploymentService(failing, CommandRunner(failing, app.clock), app.clock)
        before = {a: status(app, a) for a in fleet.equipment}
        with pytest.raises(RuleViolation, match="nothing was deployed: Someone else"):
            service.deploy(
                app.ctx(app.pilot),
                project_id=fleet.project,
                asset_ids=fleet.equipment,
                crew_ids=[app.pilot.id],
                gcp_quantity=0,
            )
        assert {a: status(app, a) for a in fleet.equipment} == before
        (cancelled,) = app.storage.deployments.for_project(fleet.project)
        assert cancelled.state is DeploymentState.CANCELLED and "Someone else" in cancelled.failure
        audit = app.storage.audit.for_entity("deployment", str(cancelled.id))
        assert [a.action for a in audit] == ["deployment.create"]
        # The equipment can go out on a fresh attempt.
        assert deploy(app, fleet, gcp_quantity=0)

    def test_gcp_issue_is_undone_too(self, app: App, fleet: Fleet) -> None:
        failing = replace(
            app.storage, status_events=_FailingStatusEvents(app.storage.status_events, 0)
        )

        class FailingProjects:
            def __init__(self, inner: Any) -> None:
                self._inner = inner

            def __getattr__(self, name: str) -> Any:
                return getattr(self._inner, name)

            def update(self, project: Any) -> None:
                raise ConflictError("Project changed meanwhile.")

        failing = replace(failing, projects=FailingProjects(app.storage.projects))
        service = DeploymentService(failing, CommandRunner(failing, app.clock), app.clock)
        with pytest.raises(RuleViolation, match="Project changed"):
            service.deploy(
                app.ctx(app.pilot),
                project_id=fleet.project,
                asset_ids=[fleet.tripod],
                crew_ids=[app.surveyor.id],
                gcp_quantity=10,
                gcp_site_id=fleet.store,
            )
        stock = app.stock.position(app.actor(app.admin), GCP)
        assert stock.on_hand_at(fleet.store) == 50 and stock.outstanding_with(fleet.project) == 0
        assert status(app, fleet.tripod)[1] is Custody.IN_STORE


# ---------------------------------------------------------------------- field log rules


class TestFieldLogRules:
    def test_flight_rules(self, app: App, fleet: Fleet) -> None:
        deployment = deploy(app, fleet, gcp_quantity=0)
        outsider = register(app, "DRONE_BATTERY", "BAT-0009")

        def fly(**values: Any) -> None:
            data: dict[str, Any] = {
                "deployment_id": deployment,
                "drone_id": fleet.drone,
                "pilot_id": app.pilot.id,
                "flown_on": TODAY,
                "hours": Decimal("0.5"),
            }
            data.update(values)
            app.logs.log_sortie(app.ctx(app.pilot), **data)

        cases = [
            ({"battery_ids": [outsider]}, "Only equipment from this deployment"),
            ({"pilot_id": app.admin.id}, "not in this deployment's crew"),
            ({"pilot_id": app.surveyor.id}, "no valid DGCA pilot certificate"),
            ({"drone_id": fleet.tripod}, "Choose a drone airframe"),
            ({"battery_ids": [fleet.sd]}, "Only drone flight batteries"),
            ({"media_ids": [fleet.bat1]}, "Only SD cards"),
            ({"ppk_base_id": fleet.tripod}, "PPK base"),
            ({"flown_on": TODAY + timedelta(days=1)}, "future"),
            ({"flown_on": TODAY - timedelta(days=1)}, "before the equipment went out"),
            ({"hours": Decimal("9")}, "longer than 8 hours"),
        ]
        for values, message in cases:
            with pytest.raises(RuleViolation, match=message):
                fly(**values)
        with pytest.raises(NotFound):
            fly(deployment_id=fleet.project)

    def test_survey_rules(self, app: App, fleet: Fleet) -> None:
        deployment = deploy(app, fleet, gcp_quantity=0)

        def survey(**values: Any) -> None:
            data: dict[str, Any] = {
                "deployment_id": deployment,
                "surveyor_id": app.surveyor.id,
                "surveyed_on": TODAY,
                "hours": Decimal("2"),
                "base_id": fleet.base,
            }
            data.update(values)
            app.logs.log_session(app.ctx(app.surveyor), **data)

        with pytest.raises(RuleViolation, match="GNSS receivers"):
            survey(base_id=fleet.tripod)
        with pytest.raises(RuleViolation, match="base and a rover"):
            survey(rover_ids=[fleet.base])
        with pytest.raises(RuleViolation, match="survey controller"):
            survey(controller_id=fleet.tripod)
        with pytest.raises(RuleViolation, match="Only batteries"):
            survey(battery_ids=[fleet.tripod])
        with pytest.raises(RuleViolation, match="not in this deployment's crew"):
            survey(surveyor_id=app.admin.id)
        session = app.logs.log_session(
            app.ctx(app.surveyor),
            deployment_id=deployment,
            surveyor_id=app.surveyor.id,
            surveyed_on=TODAY,
            hours=Decimal("2"),
            rover_ids=[fleet.rover],
            battery_ids=[fleet.bat1],
        )
        assert app.usage.totals(app.actor(app.admin), fleet.bat1)[Meter.CYCLES] == 1
        app.logs.void_session(app.ctx(app.admin), session, 1, "Wrong day")
        assert app.usage.totals(app.actor(app.admin), fleet.rover)[Meter.HOURS] == 0
        entries = app.usage.entries(app.actor(app.admin), fleet.rover)
        assert [e.source for e in entries] == [UsageSource.SORTIE, UsageSource.REVERSAL]


class TestMyWork:
    def test_crew_named_deployed_and_logging(self, app: App, fleet: Fleet) -> None:
        assert app.projects.my_work(app.actor(app.admin)) == {}
        mine = app.projects.my_work(app.actor(app.pilot))[fleet.project]
        assert mine.roles == ("Chief pilot",) and mine.flights == 0
        other = app.projects.create(app.ctx(app.admin), code="X9", name="Other",
                                    site_id=fleet.mine, starts_on=TODAY)  # fmt: skip
        deployment = deploy(app, fleet, project_id=other, gcp_quantity=0,
                            crew_ids=[app.pilot.id, app.admin.id])  # fmt: skip
        for minutes in ("0.5", "0.25"):
            app.logs.log_sortie(app.ctx(app.pilot), deployment_id=deployment,
                                drone_id=fleet.drone, pilot_id=app.pilot.id, flown_on=TODAY,
                                hours=Decimal(minutes))  # fmt: skip
        work = app.projects.my_work(app.actor(app.pilot))[other]
        assert work.roles == ("Crew",) and work.flights == 2
        assert work.flight_hours == Decimal("0.75")
        assert app.projects.my_work(app.actor(app.admin))[other].flights == 0
        assert fleet.project not in app.projects.my_work(app.actor(app.admin))
