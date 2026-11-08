"""Rules added in Sprint 5: projects, deployment readiness and returns, field logs."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from ims.domain.assets.catalogue import DEFAULT_CATALOGUE, Category, Meter
from ims.domain.assets.status import AssetStatus, Custody, Serviceability
from ims.domain.common.errors import InvalidTransition, RuleViolation
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    LocationId,
    ProjectId,
    SortieId,
    SurveySessionId,
    UserId,
    uuid7,
)
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence
from ims.domain.operations.deployment import (
    AssetReadiness,
    CrewMember,
    Deployment,
    DeploymentState,
    ReturnCondition,
    ReturnLine,
    check_readiness,
    check_return,
    return_status_change,
)
from ims.domain.operations.field_logs import (
    Sortie,
    SurveySession,
    session_usage,
    sortie_usage,
)
from ims.domain.operations.project import (
    Project,
    ProjectStatus,
    check_project_crew,
    check_transition,
)
from tests.fakes import make_user

T = {t.code: t for t in DEFAULT_CATALOGUE}
DAY = date(2026, 11, 8)
NOW = datetime(2026, 11, 8, 6, 30, tzinfo=UTC)
S, C = Serviceability, Custody


def project(**values: Any) -> Project:
    data: dict[str, Any] = {"id": ProjectId(uuid7()), "code": "kjr 2611", "name": "Survey",
                            "site_id": LocationId(uuid7()), "starts_on": DAY}  # fmt: skip
    data.update(values)
    return Project(**data)


class TestProjects:
    def test_codes_and_dates(self) -> None:
        assert project().code == "PRJ-KJR-2611"
        with pytest.raises(ValidationError, match="project code"):
            project(code="no!")
        with pytest.raises(ValidationError, match="end date"):
            project(ends_on=date(2026, 11, 1))
        assert project().is_open and not project(status=ProjectStatus.COMPLETED).is_open

    def test_transitions(self) -> None:
        planned = project()
        check_transition(planned, ProjectStatus.ACTIVE, open_deployments=0)
        with pytest.raises(InvalidTransition, match="already"):
            check_transition(planned, ProjectStatus.PLANNED, open_deployments=0)
        with pytest.raises(InvalidTransition, match="cannot become"):
            check_transition(planned, ProjectStatus.COMPLETED, open_deployments=0)
        active = project(status=ProjectStatus.ACTIVE)
        with pytest.raises(InvalidTransition, match="still out"):
            check_transition(active, ProjectStatus.COMPLETED, open_deployments=2)

    def test_crew(self) -> None:
        pilot = make_user(Role.PILOT)
        check_project_crew(pilot, make_user(Role.SURVEYOR), DAY)
        check_project_crew(None, None, DAY)
        with pytest.raises(RuleViolation) as caught:
            check_project_crew(
                pilot.next_version(is_active=False), make_user(Role.SURVEYOR, is_active=False), DAY
            )
        assert len(caught.value.problems) == 2


def crew(
    role: Role = Role.PILOT, *, active: bool = True, expires: date | None = date(2030, 1, 1)
) -> CrewMember:
    licence = PilotLicence(number="RPC-00001", expires_on=expires) if expires else None
    return CrewMember(user_id=UserId(uuid7()), name=f"{role.value} person", role=role,
                      active=active, licence=licence)  # fmt: skip


def item(category: Category = Category.SURVEY_ACCESSORY, *, s: S = S.SERVICEABLE,
         c: C = C.IN_STORE, **extra: Any) -> AssetReadiness:  # fmt: skip
    return AssetReadiness(asset_id=AssetId(uuid7()), tag="TAG-1", type_name="Thing",
                          category=category, status=AssetStatus(serviceability=s, custody=c),
                          **extra)  # fmt: skip


class TestReadiness:
    def test_every_blocker_and_warning(self) -> None:
        result = check_readiness(
            assets=[
                item(s=S.UNSERVICEABLE), item(s=S.RETIRED, c=C.IN_MAINTENANCE), item(s=S.LIMITED),
                item(c=C.DEPLOYED), item(c=C.IN_TRANSIT), item(c=C.DISPOSED),
                item(compliance=[("danger", "UIN missing"), ("warning", "insurance expiring")]),
                item(Category.DRONE, fitted_problems=["fitted motor grounded"],
                     maintenance_overdue=["50 h service"]),
            ],
            crew=[crew(expires=date(2026, 1, 1)), crew(Role.SURVEYOR, active=False, expires=None)],
            day=DAY, incomplete_kits=["KIT-DGPS-01"], gcp_requested=30, gcp_available=10,
        )  # fmt: skip
        text = " | ".join(result.blockers)
        for fragment in ("grounded", "retired", "already deployed", "in maintenance",
                         "in transit", "disposed of", "UIN missing", "fitted motor grounded",
                         "maintenance overdue", "certificate has expired", "not an active user",
                         "needs a pilot", "Only 10 GCP"):  # fmt: skip
            assert fragment in text, fragment
        assert set(result.warnings) == {
            "TAG-1 (Thing) has a recorded limitation.",
            "TAG-1: insurance expiring",
            "KIT-DGPS-01 is incomplete.",
        }
        assert not result.ok

    def test_ready_with_an_expiring_certificate(self) -> None:
        soon = crew(expires=date(2026, 11, 20))
        result = check_readiness(assets=[item(Category.DRONE)], crew=[soon], day=DAY)
        assert result.ok and "expires on 20 Nov 2026" in result.warnings[0]
        assert check_readiness(assets=[], crew=[], day=DAY).blockers == [
            "Choose the equipment to take.",
            "Choose the crew.",
        ]


def deployment(**values: Any) -> Deployment:
    a, b = AssetId(uuid7()), AssetId(uuid7())
    data: dict[str, Any] = {
        "id": DeploymentId(uuid7()), "project_id": ProjectId(uuid7()), "asset_ids": (a, b),
        "crew_ids": (UserId(uuid7()),), "deployed_on": DAY, "created_at": NOW,
        "created_by": UserId(uuid7()), "state": DeploymentState.OUT, "gcp_quantity": 10,
        "gcp_site_id": LocationId(uuid7()),
    }  # fmt: skip
    data.update(values)
    return Deployment(**data)


class TestDeployments:
    def test_record_rules(self) -> None:
        a = AssetId(uuid7())
        with pytest.raises(ValidationError) as caught:
            Deployment(id=DeploymentId(uuid7()), project_id=ProjectId(uuid7()), asset_ids=(a, a),
                       crew_ids=(), deployed_on=DAY, created_at=NOW, created_by=UserId(uuid7()),
                       gcp_quantity=5)  # fmt: skip
        message = str(caught.value)
        assert "only once" in message and "needs a crew" in message and "store the GCP" in message
        with pytest.raises(ValidationError) as caught:
            deployment(state=DeploymentState.RETURNED, returned_on=date(2026, 11, 1),
                       returned_by=UserId(uuid7()), gcp_returned=1)  # fmt: skip
        message = str(caught.value)
        assert (
            "accounted for" in message and "add up" in message and "before it went out" in message
        )
        with pytest.raises(ValidationError, match="date and the person"):
            deployment(state=DeploymentState.RETURNED, gcp_quantity=0, gcp_site_id=None,
                       returns=())  # fmt: skip
        with pytest.raises(ValidationError, match="at least one"):
            deployment(asset_ids=())
        with pytest.raises(ValidationError, match="describe the defect"):
            ReturnLine(asset_id=AssetId(uuid7()), condition=ReturnCondition.GROUNDED)

    def test_return_status(self) -> None:
        line = ReturnLine(asset_id=AssetId(uuid7()))
        limited = line.model_copy(update={"condition": ReturnCondition.LIMITED, "note": "x"})
        grounded = line.model_copy(update={"condition": ReturnCondition.GROUNDED, "note": "x"})
        ok, lim, bad = (AssetStatus(serviceability=s, custody=C.DEPLOYED)
                        for s in (S.SERVICEABLE, S.LIMITED, S.UNSERVICEABLE))  # fmt: skip
        assert return_status_change(ok, line) == (None, C.IN_STORE)
        assert return_status_change(ok, limited) == (S.LIMITED, C.IN_STORE)
        assert return_status_change(lim, limited) == (None, C.IN_STORE)
        assert return_status_change(ok, grounded) == (S.UNSERVICEABLE, C.IN_MAINTENANCE)
        assert return_status_change(bad, grounded) == (None, C.IN_MAINTENANCE)

    def test_check_return(self) -> None:
        d = deployment()
        lines = [ReturnLine(asset_id=a) for a in d.asset_ids]
        check_return(d, lines, 4, 6)
        with pytest.raises(RuleViolation) as caught:
            check_return(d.model_copy(update={"state": DeploymentState.RETURNED}), lines[:1], 1, 1)
        assert len(caught.value.problems) == 3
        with pytest.raises(RuleViolation, match="negative"):
            check_return(d, lines, -1, 11)


def sortie(**values: Any) -> Sortie:
    data: dict[str, Any] = {
        "id": SortieId(uuid7()), "project_id": ProjectId(uuid7()),
        "deployment_id": DeploymentId(uuid7()), "drone_id": AssetId(uuid7()),
        "pilot_id": UserId(uuid7()), "flown_on": DAY, "hours": Decimal("0.75"),
        "recorded_at": NOW, "recorded_by": UserId(uuid7()),
    }  # fmt: skip
    data.update(values)
    return Sortie(**data)


def session(**values: Any) -> SurveySession:
    data: dict[str, Any] = {
        "id": SurveySessionId(uuid7()), "project_id": ProjectId(uuid7()),
        "deployment_id": DeploymentId(uuid7()), "surveyor_id": UserId(uuid7()),
        "surveyed_on": DAY, "hours": Decimal("3"), "base_id": AssetId(uuid7()),
        "recorded_at": NOW, "recorded_by": UserId(uuid7()),
    }  # fmt: skip
    data.update(values)
    return SurveySession(**data)


class TestFieldLogs:
    def test_sortie_rules(self) -> None:
        b = AssetId(uuid7())
        with pytest.raises(ValidationError) as caught:
            sortie(hours=Decimal("9"), battery_ids=(b, b))
        assert "longer than 8" in str(caught.value) and "each battery once" in str(caught.value)
        drone = AssetId(uuid7())
        with pytest.raises(ValidationError, match="cannot also be"):
            sortie(drone_id=drone, media_ids=(drone,))
        assert not sortie().is_void

    def test_session_rules(self) -> None:
        r = AssetId(uuid7())
        with pytest.raises(ValidationError) as caught:
            session(hours=Decimal("25"), base_id=r, rover_ids=(r, r))
        message = str(caught.value)
        assert (
            "longer than 24" in message
            and "each rover once" in message
            and "base and a rover" in message
        )
        with pytest.raises(ValidationError, match="base or at least one rover"):
            session(base_id=None)

    def test_usage_plans(self) -> None:
        drone, motor, gear, bat, base = (AssetId(uuid7()) for _ in range(5))
        types = {drone: T["DRONE_AIRFRAME"], motor: T["MOTOR"], gear: T["LANDING_GEAR"],
                 bat: T["DRONE_BATTERY"], base: T["PPK_BASE"]}  # fmt: skip
        plan = sortie_usage(sortie(drone_id=drone, battery_ids=(bat,), ppk_base_id=base,
                                   landings=2, cycles=0), [motor, gear], types)  # fmt: skip
        h = Decimal("0.75")
        assert plan == [(drone, Meter.HOURS, h), (drone, Meter.LANDINGS, 2), (bat, Meter.CYCLES, 1),
                        (motor, Meter.HOURS, h), (gear, Meter.HOURS, h), (gear, Meter.LANDINGS, 2),
                        (base, Meter.HOURS, h)]  # fmt: skip
        rover, gbat, tripod = AssetId(uuid7()), AssetId(uuid7()), AssetId(uuid7())
        types = {base: T["GNSS_RECEIVER"], rover: T["GNSS_RECEIVER"], gbat: T["GNSS_BATTERY"],
                 tripod: T["TRIPOD"]}  # fmt: skip
        plan = session_usage(session(base_id=base, rover_ids=(rover,), battery_ids=(gbat,)), types)
        assert plan == [(base, Meter.HOURS, 3), (rover, Meter.HOURS, 3), (gbat, Meter.CYCLES, 1)]
