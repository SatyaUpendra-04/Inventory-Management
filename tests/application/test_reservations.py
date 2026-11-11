"""Reservations: requests, conflicts, approval (booking), double-booking, hand-over to a
deployment, GCP forecasts, and stocktakes."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest

from ims.application.reservations import ReservationService
from ims.application.runner import CommandRunner
from ims.domain.assets.status import Custody, Serviceability, StatusChange
from ims.domain.common.errors import (
    ConflictError,
    InvalidTransition,
    PermissionDenied,
    RuleViolation,
)
from ims.domain.common.ids import AssetId, ProjectId
from ims.domain.operations.deployment import DeploymentState
from ims.domain.operations.reservation import ReservationStatus, active_bookings
from ims.domain.stock.ledger import MovementKind
from tests.application.conftest import App
from tests.application.test_operations import GCP, TODAY, Fleet, register, status

D = timedelta(days=1)


@pytest.fixture
def fleet(app: App) -> Fleet:
    return Fleet(app)


def second_project(app: App, fleet: Fleet) -> ProjectId:
    return app.projects.create(app.ctx(app.admin), code="JSP-2612", name="Jajpur stockpiles",
                               site_id=fleet.mine, starts_on=TODAY)  # fmt: skip


def ask(app: App, fleet: Fleet, *, who: Any = None, project: ProjectId | None = None,
        start: date = TODAY + 2 * D, end: date = TODAY + 6 * D, **extra: Any) -> Any:  # fmt: skip
    values: dict[str, Any] = {"project_id": project or fleet.project, "starts_on": start,
                              "ends_on": end, "asset_ids": [fleet.drone, fleet.bat1]}  # fmt: skip
    values.update(extra)
    return app.reservations.request(app.ctx(who or app.pilot), **values)


def booked(app: App, asset: AssetId) -> list[Any]:
    return active_bookings(app.storage.bookings.for_asset(asset))


class TestRequestAndApprove:
    def test_crew_request_waits_then_admin_books_it(self, app: App, fleet: Fleet) -> None:
        rid = ask(app, fleet)
        r = app.reservations.get(app.actor(app.pilot), rid)
        assert r.status is ReservationStatus.REQUESTED and booked(app, fleet.drone) == []
        with pytest.raises(PermissionDenied):
            app.reservations.approve(app.ctx(app.pilot), rid, 1)
        app.reservations.approve(app.ctx(app.admin), rid, 1, "OK")
        r = app.reservations.get(app.actor(app.pilot), rid)
        assert r.status is ReservationStatus.APPROVED and r.decision_note == "OK"
        assert [b.reservation_id for b in booked(app, fleet.drone)] == [rid]
        with pytest.raises(InvalidTransition):
            app.reservations.approve(app.ctx(app.admin), rid, 2)

    def test_admins_book_straight_away(self, app: App, fleet: Fleet) -> None:
        rid = ask(app, fleet, who=app.admin)
        assert app.reservations.get(app.actor(app.admin), rid).status is ReservationStatus.APPROVED
        assert len(booked(app, fleet.bat1)) == 1

    def test_double_booking_is_impossible(self, app: App, fleet: Fleet) -> None:
        other = second_project(app, fleet)
        ask(app, fleet, who=app.admin)
        with pytest.raises(RuleViolation, match="already booked for PRJ-KJR-2611"):
            ask(app, fleet, project=other, start=TODAY + 5 * D, end=TODAY + 9 * D)
        later = ask(app, fleet, project=other, start=TODAY + 7 * D, end=TODAY + 9 * D)
        app.reservations.approve(app.ctx(app.admin), later, 1)
        assert len(booked(app, fleet.drone)) == 2

    def test_competing_requests_only_one_can_be_approved(self, app: App, fleet: Fleet) -> None:
        other = second_project(app, fleet)
        first = ask(app, fleet)
        report = app.reservations.check(
            app.actor(app.pilot), starts_on=TODAY + 3 * D, ends_on=TODAY + 4 * D,
            asset_ids=[fleet.drone],
        )  # fmt: skip
        assert report.conflicts.ok and any("also requested" in w for w in report.conflicts.warnings)
        second = ask(app, fleet, project=other, start=TODAY + 3 * D, end=TODAY + 4 * D)
        app.reservations.approve(app.ctx(app.admin), second, 1)
        with pytest.raises(RuleViolation, match="already booked for PRJ-JSP-2612"):
            app.reservations.approve(app.ctx(app.admin), first, 1)
        assert (
            app.reservations.get(app.actor(app.admin), first).status is ReservationStatus.REQUESTED
        )

    def test_a_refused_booking_releases_what_was_booked(self, app: App, fleet: Fleet) -> None:
        rid = ask(app, fleet)

        class RaceLost:
            def __init__(self, inner: Any) -> None:
                self._inner, self._count = inner, 0

            def for_asset(self, asset_id: AssetId) -> Any:
                return self._inner.for_asset(asset_id)

            def append(self, event: Any) -> None:
                self._count += 1
                if self._count == 2:  # the battery: someone else booked it a moment ago
                    raise ConflictError("Someone else recorded a change first.")
                self._inner.append(event)

        racing = replace(app.storage, bookings=RaceLost(app.storage.bookings))
        service = ReservationService(racing, CommandRunner(racing, app.clock), app.clock)
        with pytest.raises(RuleViolation, match="Nothing was booked: Someone else"):
            service.approve(app.ctx(app.admin), rid, 1)
        assert booked(app, fleet.drone) == [] and booked(app, fleet.bat1) == []
        assert app.reservations.get(app.actor(app.admin), rid).status is ReservationStatus.REQUESTED
        app.reservations.approve(app.ctx(app.admin), rid, 1)  # a fresh attempt succeeds
        assert len(booked(app, fleet.bat1)) == 1

    def test_reject_and_cancel(self, app: App, fleet: Fleet) -> None:
        rid = ask(app, fleet)
        with pytest.raises(RuleViolation, match="reason"):
            app.reservations.reject(app.ctx(app.admin), rid, 1, " ")
        app.reservations.reject(app.ctx(app.admin), rid, 1, "Drone needed elsewhere")
        assert app.reservations.get(app.actor(app.admin), rid).status is ReservationStatus.REJECTED
        mine = ask(app, fleet, who=app.admin)
        with pytest.raises(PermissionDenied):
            app.reservations.cancel(app.ctx(app.surveyor), mine, 2)
        app.reservations.cancel(app.ctx(app.admin), mine, 2, "Job moved")
        assert booked(app, fleet.drone) == []
        own = ask(app, fleet)
        app.reservations.cancel(app.ctx(app.pilot), own, 1)
        assert app.reservations.get(app.actor(app.pilot), own).status is ReservationStatus.CANCELLED


class TestConflicts:
    def check(self, app: App, fleet: Fleet, **values: Any) -> Any:
        data: dict[str, Any] = {"starts_on": TODAY + 2 * D, "ends_on": TODAY + 6 * D}
        data.update(values)
        return app.reservations.check(app.actor(app.pilot), **data).conflicts

    def test_warnings_and_blockers(self, app: App, fleet: Fleet) -> None:
        app.assets.change_status(app.ctx(app.admin), fleet.bat1, StatusChange(
            serviceability=Serviceability.UNSERVICEABLE, reason="Puffed"))  # fmt: skip
        undocumented = register(app, "DRONE_AIRFRAME", "DRN-0002")
        old = register(app, "TRIPOD", "TRP-0002")
        app.assets.change_status(app.ctx(app.admin), old, StatusChange(
            serviceability=Serviceability.RETIRED, reason="Bent"))  # fmt: skip
        other = second_project(app, fleet)
        app.deployments.deploy(app.ctx(app.pilot), project_id=other, asset_ids=[fleet.tripod],
                               crew_ids=[app.surveyor.id])  # fmt: skip
        result = self.check(app, fleet, asset_ids=[fleet.bat1, undocumented, old, fleet.tripod])
        assert result.blockers == ["TRP-0002 (Tripod) is retired."]
        text = " | ".join(result.warnings)
        assert "BAT-0001 (Drone flight battery) is grounded" in text
        assert "DRN-0002: UIN (Digital Sky) missing" in text
        assert "TRP-0001 (Tripod) is out with PRJ-JSP-2612" in text
        assert self.check(app, fleet, starts_on=TODAY - D).blockers == [
            "The booking cannot start in the past.",
            "Choose equipment or GCP banners to reserve.",
        ]

    def test_documents_are_checked_for_the_end_of_the_job(self, app: App, fleet: Fleet) -> None:
        # The fleet drone's insurance runs 200 days; a job ending after that is warned about.
        late = self.check(app, fleet, starts_on=TODAY + 190 * D, ends_on=TODAY + 205 * D,
                          asset_ids=[fleet.drone])  # fmt: skip
        assert any("insurance" in w.lower() for w in late.warnings)
        assert self.check(app, fleet, asset_ids=[fleet.drone]).warnings == []

    def test_gcp_forecast(self, app: App, fleet: Fleet) -> None:
        app.stock.set_reorder_level(app.ctx(app.admin), GCP, fleet.store, 30)
        first = self.check(app, fleet, gcp_quantity=20, gcp_site_id=fleet.store)
        assert (
            first.ok
            and "would leave 30 in that store, at or below its reorder level of 30"
            in first.warnings[0]
        )
        ask(app, fleet, who=app.admin, asset_ids=[], gcp_quantity=40, gcp_site_id=fleet.store)
        short = self.check(app, fleet, gcp_quantity=20, gcp_site_id=fleet.store)
        assert "this booking is 10 short" in short.warnings[0]
        assert app.reservations.gcp_booked(app.actor(app.pilot)) == {fleet.store: 40}
        assert "Choose the store" in self.check(app, fleet, gcp_quantity=5).blockers[0]


class TestHandOver:
    def test_bookings_block_other_projects_and_flow_into_a_deployment(
        self, app: App, fleet: Fleet
    ) -> None:
        rid = ask(app, fleet, who=app.admin, start=TODAY, end=TODAY + 3 * D)
        other = second_project(app, fleet)
        report = app.deployments.readiness(
            app.actor(app.pilot), asset_ids=[fleet.drone], crew_ids=[app.pilot.id],
            project_id=other,
        )  # fmt: skip
        assert "DRN-0001 is booked for PRJ-KJR-2611" in report.readiness.blockers[0]
        own = app.deployments.readiness(
            app.actor(app.pilot), asset_ids=[fleet.drone], crew_ids=[app.pilot.id],
            project_id=fleet.project,
        )  # fmt: skip
        assert own.readiness.ok
        with pytest.raises(RuleViolation, match="another project"):
            app.deployments.deploy(app.ctx(app.pilot), project_id=other, asset_ids=[fleet.tripod],
                                   crew_ids=[app.surveyor.id], reservation_id=rid)  # fmt: skip
        deployment = app.deployments.deploy(
            app.ctx(app.pilot), project_id=fleet.project, asset_ids=[fleet.drone, fleet.bat1],
            crew_ids=[app.pilot.id], reservation_id=rid,
        )  # fmt: skip
        d = app.deployments.get(app.actor(app.pilot), deployment)
        assert d.state is DeploymentState.OUT and d.reservation_id == rid
        r = app.reservations.get(app.actor(app.pilot), rid)
        assert r.status is ReservationStatus.FULFILLED and r.deployment_id == deployment
        assert booked(app, fleet.drone) == [] and status(app, fleet.drone)[1] is Custody.DEPLOYED
        with pytest.raises(RuleViolation, match="fulfilled"):
            app.deployments.deploy(app.ctx(app.pilot), project_id=fleet.project,
                                   asset_ids=[fleet.tripod], crew_ids=[app.surveyor.id],
                                   reservation_id=rid)  # fmt: skip

    def test_schedule(self, app: App, fleet: Fleet) -> None:
        rid = ask(app, fleet)
        app.deployments.deploy(app.ctx(app.pilot), project_id=fleet.project,
                               asset_ids=[fleet.tripod], crew_ids=[app.surveyor.id])  # fmt: skip
        entries = app.reservations.schedule(app.actor(app.pilot), TODAY, TODAY + 13 * D)
        kinds = {(e.asset_id, e.kind) for e in entries}
        assert (fleet.drone, "requested") in kinds and (fleet.tripod, "out") in kinds
        assert {e.reservation_id for e in entries if e.reservation_id} == {rid}
        assert app.reservations.schedule(app.actor(app.pilot), TODAY + 30 * D, TODAY + 40 * D) == [
            e for e in entries if e.kind == "out" and e.ends_on >= TODAY + 30 * D
        ]


class TestStocktake:
    def test_variance_report_and_retry(self, app: App, fleet: Fleet) -> None:
        app.stock.record(app.ctx(app.admin), item_type_id=GCP, location_id=fleet.mine,
                         kind=MovementKind.RECEIVED, quantity=12, reason="Transfer")  # fmt: skip
        ctx = app.ctx(app.admin)
        report = app.stock.stocktake(ctx, GCP, {fleet.store: 47, fleet.mine: 12}, "Monthly count")
        lines = {r.location_id: (r.expected, r.counted, r.variance) for r in report}
        assert lines == {fleet.store: (50, 47, -3), fleet.mine: (12, 12, 0)}
        again = app.stock.stocktake(ctx, GCP, {fleet.store: 47, fleet.mine: 12}, "Monthly count")
        assert [(r.expected, r.variance) for r in again] == [
            (r.expected, r.variance) for r in report
        ]
        assert app.stock.position(app.actor(app.admin), GCP).on_hand_at(fleet.store) == 47
        latest = app.stock.movements(app.actor(app.admin), GCP)[-1]
        assert latest.kind is MovementKind.ADJUSTED and "records said 50" in latest.reason
        with pytest.raises(RuleViolation):
            app.stock.stocktake(app.ctx(app.admin), GCP, {})
        with pytest.raises(RuleViolation, match="negative"):
            app.stock.stocktake(app.ctx(app.admin), GCP, {fleet.store: -1})
        with pytest.raises(PermissionDenied):
            app.stock.stocktake(app.ctx(app.pilot), GCP, {fleet.store: 1})
