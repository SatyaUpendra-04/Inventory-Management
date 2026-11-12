"""Maintenance: programme, due calculation, automatic grounding, defects, work orders and
return to service, and how they block check-out and warn reservations."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from ims.domain.assets.catalogue import Meter
from ims.domain.assets.status import Custody, Serviceability
from ims.domain.common.errors import InvalidTransition, PermissionDenied, RuleViolation
from ims.domain.common.ids import AssetId
from ims.domain.maintenance.defects import DefectState
from ims.domain.maintenance.programme import DueState, MaintenanceTask
from ims.domain.maintenance.work_orders import WorkOrderState
from ims.domain.operations.deployment import ReturnCondition, ReturnLine
from tests.application.conftest import App
from tests.application.test_operations import TODAY, TYPES, Fleet, make_compliant, status

D = timedelta(days=1)


@pytest.fixture
def fleet(app: App) -> Fleet:
    fleet = Fleet(app)
    assert app.maintenance.install_default_programme(app.ctx(app.admin)) == 8
    return fleet


def drone_with_hours(app: App, tag: str, hours: str) -> AssetId:
    drone = app.assets.register(
        app.ctx(app.admin),
        item_type_id=TYPES["DRONE_AIRFRAME"].id,
        asset_tag=tag,
        serial_number=f"SN-{tag}",
        opening_balances={Meter.HOURS: Decimal(hours)},
    )
    make_compliant(app, drone)
    return drone


def task(app: App, name: str, type_code: str = "DRONE_AIRFRAME") -> MaintenanceTask:
    return next(
        t
        for t in app.maintenance.tasks(app.actor(app.admin))
        if t.name == name and t.item_type_id == TYPES[type_code].id
    )


def state_of(app: App, asset: AssetId, name: str) -> Any:
    return next(
        d for d in app.maintenance.asset_due(app.actor(app.pilot), asset) if d.task.name == name
    )


def readiness(app: App, *assets: AssetId) -> list[str]:
    report = app.deployments.readiness(
        app.actor(app.pilot), asset_ids=list(assets), crew_ids=[app.pilot.id]
    )
    return report.readiness.blockers


class TestProgramme:
    def test_defaults_install_once_and_tasks_can_be_edited(self, app: App, fleet: Fleet) -> None:
        assert app.maintenance.install_default_programme(app.ctx(app.admin)) == 0
        inspection = task(app, "Routine inspection")
        assert inspection.every_hours == Decimal(50) and inspection.every_days == 90
        app.maintenance.update_task(app.ctx(app.admin), inspection.id, 1, every_hours=Decimal(40))
        assert task(app, "Routine inspection").every_hours == Decimal(40)
        with pytest.raises(PermissionDenied):
            app.maintenance.update_task(app.ctx(app.pilot), inspection.id, 2, name="X")
        with pytest.raises(RuleViolation, match="cannot be set"):
            app.maintenance.update_task(app.ctx(app.admin), inspection.id, 2, item_type_id=None)
        new = app.maintenance.add_task(
            app.ctx(app.admin),
            item_type_id=TYPES["TRIPOD"].id,
            name="Leg lock check",
            every_days=60,
        )
        assert app.maintenance.asset_due(app.actor(app.pilot), fleet.tripod)[0].task.id == new

    def test_due_states_from_usage(self, app: App, fleet: Fleet) -> None:
        soon = drone_with_hours(app, "DRN-0011", "46")
        due = drone_with_hours(app, "DRN-0012", "52")
        over = drone_with_hours(app, "DRN-0013", "57")
        assert state_of(app, soon, "Routine inspection").state is DueState.DUE_SOON
        assert state_of(app, due, "Routine inspection").state is DueState.DUE  # inside tolerance
        overdue = state_of(app, over, "Routine inspection")
        assert overdue.state is DueState.OVERDUE and overdue.summary == "7 h over"
        assert readiness(app, due) == []
        assert any("Routine inspection overdue (7 h over)" in b for b in readiness(app, over))
        rows = app.maintenance.due_list(app.actor(app.pilot))
        assert [r.asset.asset_tag for r in rows[:3]] == ["DRN-0013", "DRN-0012", "DRN-0011"]

    def test_recording_a_completion_resets_the_count(self, app: App, fleet: Fleet) -> None:
        over = drone_with_hours(app, "DRN-0013", "57")
        inspection = task(app, "Routine inspection")
        with pytest.raises(RuleViolation, match="future"):
            app.maintenance.record_completion(
                app.ctx(app.admin), over, inspection.id, done_on=TODAY + D
            )
        app.maintenance.record_completion(app.ctx(app.admin), over, inspection.id, notes="Done")
        assert state_of(app, over, "Routine inspection").state is DueState.OK
        with pytest.raises(RuleViolation, match="life limit"):
            app.maintenance.record_completion(
                app.ctx(app.admin), fleet.motor, task(app, "Motor life limit", "MOTOR").id
            )
        with pytest.raises(RuleViolation, match="not in this item's"):
            app.maintenance.record_completion(app.ctx(app.admin), fleet.tripod, inspection.id)


class TestAutomaticGrounding:
    def test_a_flight_past_the_limit_grounds_the_drone(self, app: App, fleet: Fleet) -> None:
        drone = drone_with_hours(app, "DRN-0011", "48")
        deployment = app.deployments.deploy(
            app.ctx(app.pilot), project_id=fleet.project, asset_ids=[drone], crew_ids=[app.pilot.id]
        )

        def fly(hours: str) -> None:
            app.logs.log_sortie(
                app.ctx(app.pilot),
                deployment_id=deployment,
                drone_id=drone,
                pilot_id=app.pilot.id,
                flown_on=TODAY,
                hours=Decimal(hours),
            )

        fly("4")  # 52 h: due, inside the 5 h tolerance
        assert status(app, drone)[0] is Serviceability.SERVICEABLE
        fly("4")  # 56 h: overdue
        assert status(app, drone) == (Serviceability.UNSERVICEABLE, Custody.DEPLOYED)
        reason = app.assets.history(app.actor(app.admin), drone)[-1].reason
        assert reason.startswith("Grounded automatically: Routine inspection overdue")

    def test_calendar_tasks_and_the_sweep(self, app: App, fleet: Fleet) -> None:
        assert app.maintenance.ground_overdue(app.ctx(app.admin)) == 0
        app.clock.advance(days=98)  # 90 days + 7 days tolerance, plus one
        assert any("Routine inspection overdue" in b for b in readiness(app, fleet.drone))
        grounded = app.maintenance.ground_overdue(app.ctx(app.admin))
        assert grounded >= 1 and status(app, fleet.drone)[0] is Serviceability.UNSERVICEABLE
        assert app.maintenance.ground_overdue(app.ctx(app.admin)) == 0  # already grounded
        with pytest.raises(PermissionDenied):
            app.maintenance.ground_overdue(app.ctx(app.pilot))

    def test_life_limited_fitted_parts_block_the_airframe(self, app: App, fleet: Fleet) -> None:
        old_motor = app.assets.register(
            app.ctx(app.admin),
            item_type_id=TYPES["MOTOR"].id,
            asset_tag="MOT-0009",
            serial_number="SN-M9",
            opening_balances={Meter.HOURS: Decimal(600)},
        )
        app.registry.install(app.ctx(app.admin), old_motor, fleet.drone, "Motor 2")
        blockers = readiness(app, fleet.drone)
        assert any(
            "fitted motor MOT-0009: Motor life limit life limit reached" in b for b in blockers
        )


class TestDefectsAndWorkOrders:
    def test_report_assess_fix_and_return_to_service(self, app: App, fleet: Fleet) -> None:
        drone = fleet.drone
        defect = app.maintenance.report_defect(
            app.ctx(app.pilot), drone, description="Arm 3 creaks under load"
        )
        d = app.storage.defects.get(defect)
        assert d is not None and d.state is DefectState.REPORTED and d.number == "DEF-0001"
        assert status(app, drone)[0] is Serviceability.SERVICEABLE
        with pytest.raises(PermissionDenied):
            app.maintenance.assess_defect(
                app.ctx(app.pilot), defect, 1, decision=DefectState.DEFERRED
            )
        with pytest.raises(RuleViolation, match="limitation"):
            app.maintenance.assess_defect(
                app.ctx(app.admin), defect, 1, decision=DefectState.DEFERRED
            )
        app.maintenance.assess_defect(
            app.ctx(app.admin),
            defect,
            1,
            decision=DefectState.DEFERRED,
            limitation="Max wind 8 m/s",
            deferred_until=TODAY + 10 * D,
        )
        assert status(app, drone)[0] is Serviceability.LIMITED
        assert readiness(app, drone) == []  # usable with a limitation
        report = app.reservations.check(
            app.actor(app.pilot), starts_on=TODAY + 5 * D, ends_on=TODAY + 12 * D, asset_ids=[drone]
        )
        assert any("DEF-0001 must be fixed by" in w for w in report.conflicts.warnings)

        # The deferral runs out: the drone is grounded.
        app.clock.advance(days=11)
        assert any("DEF-0001 was deferred until" in b for b in readiness(app, drone))
        app.maintenance.ground_overdue(app.ctx(app.admin))
        assert status(app, drone)[0] is Serviceability.UNSERVICEABLE

        # Fix it on a work order, then sign it off.
        inspection = task(app, "Routine inspection")
        order = app.maintenance.open_work_order(
            app.ctx(app.admin),
            drone,
            title="Arm repair",
            defect_ids=[defect],
            task_ids=[inspection.id],
        )
        assert status(app, drone)[1] is Custody.IN_MAINTENANCE
        with pytest.raises(RuleViolation, match="already has an open work order"):
            app.maintenance.open_work_order(app.ctx(app.admin), drone, title="Again")
        with pytest.raises(InvalidTransition):
            app.maintenance.complete_work_order(app.ctx(app.admin), order, 1, work_done="x")
        app.maintenance.move_work_order(app.ctx(app.admin), order, 1, WorkOrderState.IN_PROGRESS)
        app.maintenance.move_work_order(
            app.ctx(app.admin), order, 2, WorkOrderState.AWAITING_PARTS, "Arm on order"
        )
        app.maintenance.move_work_order(app.ctx(app.admin), order, 3, WorkOrderState.IN_PROGRESS)
        with pytest.raises(RuleViolation, match="describe the work"):
            app.maintenance.complete_work_order(app.ctx(app.admin), order, 4, work_done=" ")
        app.maintenance.complete_work_order(
            app.ctx(app.admin),
            order,
            4,
            work_done="Replaced arm 3; inspection done",
            parts="Arm assembly",
        )
        fixed = app.storage.defects.get(defect)
        assert fixed is not None and fixed.state is DefectState.RECTIFIED
        assert state_of(app, drone, "Routine inspection").state is DueState.OK
        with pytest.raises(PermissionDenied):
            app.maintenance.certify(app.ctx(app.pilot), order, 5)
        app.maintenance.certify(app.ctx(app.admin), order, 5)
        assert status(app, drone) == (Serviceability.SERVICEABLE, Custody.IN_STORE)
        done = app.maintenance.work_order(app.actor(app.admin), order)
        assert done.state is WorkOrderState.CERTIFIED and done.number == "WO-0001"

    def test_sign_off_is_refused_while_something_still_grounds_it(
        self, app: App, fleet: Fleet
    ) -> None:
        over = drone_with_hours(app, "DRN-0013", "57")
        defect = app.maintenance.report_defect(
            app.ctx(app.pilot), over, description="Cracked shell", unsafe=True
        )
        assert status(app, over)[0] is Serviceability.UNSERVICEABLE
        order = app.maintenance.open_work_order(
            app.ctx(app.admin), over, title="Shell", defect_ids=[defect]
        )
        app.maintenance.move_work_order(app.ctx(app.admin), order, 1, WorkOrderState.IN_PROGRESS)
        app.maintenance.complete_work_order(app.ctx(app.admin), order, 2, work_done="New shell")
        with pytest.raises(RuleViolation, match="Routine inspection overdue"):
            app.maintenance.certify(app.ctx(app.admin), order, 3)
        app.maintenance.move_work_order(
            app.ctx(app.admin), order, 3, WorkOrderState.IN_PROGRESS, "Inspection still due"
        )
        app.maintenance.move_work_order(
            app.ctx(app.admin), order, 4, WorkOrderState.CANCELLED, "Do it with the inspection"
        )
        assert status(app, over)[1] is Custody.IN_STORE

    def test_life_limits_cannot_be_completed_on_a_work_order(self, app: App, fleet: Fleet) -> None:
        life = task(app, "Motor life limit", "MOTOR")
        order = app.maintenance.open_work_order(
            app.ctx(app.admin), fleet.motor, title="Motor", task_ids=[life.id]
        )
        app.maintenance.move_work_order(app.ctx(app.admin), order, 1, WorkOrderState.IN_PROGRESS)
        with pytest.raises(RuleViolation, match="replace the part"):
            app.maintenance.complete_work_order(app.ctx(app.admin), order, 2, work_done="x")

    def test_returned_damage_files_defects(self, app: App, fleet: Fleet) -> None:
        deployment = app.deployments.deploy(
            app.ctx(app.pilot),
            project_id=fleet.project,
            asset_ids=[fleet.tripod, fleet.sd],
            crew_ids=[app.surveyor.id],
        )
        d = app.deployments.get(app.actor(app.pilot), deployment)
        app.deployments.return_equipment(
            app.ctx(app.pilot),
            deployment,
            d.version,
            lines=[
                ReturnLine(
                    asset_id=fleet.tripod, condition=ReturnCondition.GROUNDED, note="Leg snapped"
                ),
                ReturnLine(
                    asset_id=fleet.sd, condition=ReturnCondition.LIMITED, note="Slow writes"
                ),
            ],
        )
        defects = {x.asset_id: x for x in app.maintenance.defects(app.actor(app.admin))}
        assert defects[fleet.tripod].state is DefectState.GROUNDED
        assert defects[fleet.sd].state is DefectState.REPORTED
        assert defects[fleet.sd].description == "Slow writes"

    def test_rules_for_opening_work_orders(self, app: App, fleet: Fleet) -> None:
        other = app.maintenance.report_defect(
            app.ctx(app.pilot), fleet.tripod, description="Wobbly head"
        )
        with pytest.raises(RuleViolation, match="not an open defect on this item"):
            app.maintenance.open_work_order(
                app.ctx(app.admin), fleet.drone, title="x", defect_ids=[other]
            )
        app.deployments.deploy(
            app.ctx(app.pilot),
            project_id=fleet.project,
            asset_ids=[fleet.tripod],
            crew_ids=[app.surveyor.id],
        )
        with pytest.raises(RuleViolation, match="out on a project"):
            app.maintenance.open_work_order(
                app.ctx(app.admin), fleet.tripod, title="x", defect_ids=[other]
            )
        with pytest.raises(RuleViolation, match="not a defect"):
            app.maintenance.assess_defect(
                app.ctx(app.admin), other, 1, decision=DefectState.CANCELLED
            )
        app.maintenance.assess_defect(
            app.ctx(app.admin),
            other,
            1,
            decision=DefectState.CANCELLED,
            note="Head was loose, tightened",
        )
        with pytest.raises(RuleViolation, match="Ground, defer or cancel"):
            app.maintenance.assess_defect(
                app.ctx(app.admin), other, 2, decision=DefectState.RECTIFIED
            )
