"""Battery lifecycle, GNSS calibration records and the alert centre."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from ims.domain.assets.calibration import CalibrationKind, CalibrationResult
from ims.domain.assets.catalogue import Meter
from ims.domain.assets.status import Serviceability, StatusChange
from ims.domain.batteries import BatteryCondition, ChargeState, policy_id
from ims.domain.common.errors import PermissionDenied, RuleViolation
from ims.domain.common.ids import AssetId
from ims.domain.maintenance.work_orders import WorkOrderState
from tests.application.conftest import App
from tests.application.test_operations import TODAY, TYPES, Fleet, register, status

D = timedelta(days=1)
PDF = b"%PDF-1.7\n" + b"\x00" * 32


@pytest.fixture
def fleet(app: App) -> Fleet:
    fleet = Fleet(app)
    assert app.batteries.install_default_policies(app.ctx(app.admin)) == 3
    app.maintenance.install_default_programme(app.ctx(app.admin))
    return fleet


def battery_with_cycles(app: App, tag: str, cycles: int, code: str = "DRONE_BATTERY") -> AssetId:
    return app.assets.register(
        app.ctx(app.admin),
        item_type_id=TYPES[code].id,
        asset_tag=tag,
        serial_number=f"SN-{tag}",
        opening_balances={Meter.CYCLES: Decimal(cycles)} if cycles else None,
    )


def state(app: App, battery: AssetId):  # type: ignore[no-untyped-def]
    return app.batteries.battery(app.actor(app.pilot), battery).row.state


class TestBatteryLifecycle:
    def test_cycles_health_and_limits(self, app: App, fleet: Fleet) -> None:
        assert app.batteries.install_default_policies(app.ctx(app.admin)) == 0
        fresh = state(app, fleet.bat1)
        assert fresh.cycles == 0 and fresh.condition is BatteryCondition.OK
        assert fresh.health_text == "~100% (estimated)" and fresh.cycle_limit == 200
        worn = battery_with_cycles(app, "BAT-0011", 185)
        near = state(app, worn)
        assert near.condition is BatteryCondition.NEAR_LIMIT
        assert near.warnings == ["15 cycles left before retirement"]
        assert near.health == Decimal("67.625")  # estimate only: does not ground it
        spent = battery_with_cycles(app, "BAT-0012", 200)
        assert state(app, spent).condition is BatteryCondition.RETIRE
        blockers = app.deployments.readiness(
            app.actor(app.pilot), asset_ids=[spent], crew_ids=[app.pilot.id]
        ).readiness.blockers
        assert any("Battery cycle limit reached (200 of 200)" in b for b in blockers)

    def test_a_flight_that_reaches_the_limit_grounds_the_battery(
        self, app: App, fleet: Fleet
    ) -> None:
        last_one = battery_with_cycles(app, "BAT-0013", 199)
        deployment = app.deployments.deploy(
            app.ctx(app.pilot),
            project_id=fleet.project,
            asset_ids=[fleet.drone, last_one],
            crew_ids=[app.pilot.id],
        )
        assert status(app, last_one)[0] is Serviceability.SERVICEABLE
        app.logs.log_sortie(
            app.ctx(app.pilot),
            deployment_id=deployment,
            drone_id=fleet.drone,
            pilot_id=app.pilot.id,
            flown_on=TODAY,
            hours=Decimal("0.5"),
            battery_ids=[last_one],
        )
        assert status(app, last_one)[0] is Serviceability.UNSERVICEABLE

    def test_checks_measured_health_and_safety(self, app: App, fleet: Fleet) -> None:
        app.batteries.record_check(
            app.ctx(app.pilot),
            fleet.bat1,
            health_pct=92,
            internal_resistance_mohm=Decimal("4.5"),
            cell_imbalance_mv=8,
            charge_state=ChargeState.STORAGE,
        )
        assert state(app, fleet.bat1).health_text == "92%"
        app.batteries.record_check(app.ctx(app.pilot), fleet.bat1, health_pct=65)
        assert "health 65% is below the 70% limit" in state(app, fleet.bat1).reasons
        assert status(app, fleet.bat1)[0] is Serviceability.UNSERVICEABLE
        with pytest.raises(RuleViolation, match="describe"):
            app.batteries.record_check(app.ctx(app.pilot), fleet.bat2, swelling=True)
        app.batteries.record_check(
            app.ctx(app.pilot), fleet.bat2, swelling=True, notes="Pack puffed after the last flight"
        )
        puffed = state(app, fleet.bat2)
        assert puffed.condition is BatteryCondition.UNSAFE and "swelling" in puffed.reasons[0]
        assert status(app, fleet.bat2)[0] is Serviceability.UNSERVICEABLE
        with pytest.raises(RuleViolation, match="future"):
            app.batteries.record_check(app.ctx(app.pilot), fleet.bat1, checked_on=TODAY + D)
        with pytest.raises(RuleViolation, match="not a battery"):
            app.batteries.record_check(app.ctx(app.pilot), fleet.drone)

    def test_storage_charge_reminder(self, app: App, fleet: Fleet) -> None:
        app.batteries.record_check(app.ctx(app.pilot), fleet.bat1, charge_state=ChargeState.FULL)
        app.clock.advance(days=15)
        idle = state(app, fleet.bat1)
        assert idle.condition is BatteryCondition.STORAGE_DUE
        assert idle.warnings == ["idle 15 days: put it at storage charge"]
        app.batteries.record_check(app.ctx(app.pilot), fleet.bat1, charge_state=ChargeState.STORAGE)
        assert state(app, fleet.bat1).condition is BatteryCondition.OK

    def test_servicing_never_resets_cycles_or_health(self, app: App, fleet: Fleet) -> None:
        worn = battery_with_cycles(app, "BAT-0011", 150)
        app.batteries.record_check(app.ctx(app.admin), worn, health_pct=80)
        defect = app.maintenance.report_defect(app.ctx(app.pilot), worn, description="Loose lead")
        order = app.maintenance.open_work_order(
            app.ctx(app.admin), worn, title="Lead", defect_ids=[defect]
        )
        app.maintenance.move_work_order(app.ctx(app.admin), order, 1, WorkOrderState.IN_PROGRESS)
        app.maintenance.complete_work_order(app.ctx(app.admin), order, 2, work_done="Resoldered")
        app.maintenance.certify(app.ctx(app.admin), order, 3)
        after = state(app, worn)
        assert after.cycles == 150 and after.health_text == "80%"

    def test_charge_cycles_limits_and_chargers(self, app: App, fleet: Fleet) -> None:
        receiver_battery = battery_with_cycles(app, "GBT-0001", 0, "GNSS_BATTERY")
        app.batteries.log_charge_cycles(app.ctx(app.surveyor), receiver_battery, 3)
        detail = app.batteries.battery(app.actor(app.surveyor), receiver_battery)
        assert detail.row.state.cycles == 3 and detail.row.state.cycle_limit == 500
        assert [e.amount for e in detail.cycles] == [3]
        with pytest.raises(RuleViolation, match="how many"):
            app.batteries.log_charge_cycles(app.ctx(app.surveyor), receiver_battery, 0)
        with pytest.raises(RuleViolation, match="future"):
            app.batteries.log_charge_cycles(
                app.ctx(app.surveyor), receiver_battery, 1, on=TODAY + D
            )
        policy = app.storage.battery_policies.get(policy_id(TYPES["GNSS_BATTERY"].id))
        assert policy is not None
        with pytest.raises(PermissionDenied):
            app.batteries.update_policy(
                app.ctx(app.pilot), policy.id, 1, cycle_limit=3, health_floor=70, idle_days=30
            )
        app.batteries.update_policy(
            app.ctx(app.admin), policy.id, 1, cycle_limit=3, health_floor=70, idle_days=30
        )
        assert state(app, receiver_battery).condition is BatteryCondition.RETIRE
        charger = register(app, "DRONE_BATTERY_CHARGER", "DCH-0001")
        row = next(
            r for r in app.batteries.batteries(app.actor(app.pilot)) if r.asset.id == fleet.bat1
        )
        assert [c.id for c in row.chargers] == [charger]


class TestCalibration:
    def test_calibration_files_the_certificate(self, app: App, fleet: Fleet) -> None:
        receiver = register(app, "GNSS_RECEIVER", "GNS-0009")
        before = app.deployments.readiness(
            app.actor(app.pilot), asset_ids=[receiver], crew_ids=[app.surveyor.id]
        ).readiness.blockers
        assert any("Calibration certificate missing" in b for b in before)
        with pytest.raises(PermissionDenied):
            app.calibration.record(
                app.ctx(app.surveyor),
                receiver,
                kind=CalibrationKind.CALIBRATION,
                done_on=TODAY,
                method="Lab",
                reference="Trimble service centre",
                result=CalibrationResult.PASS,
                valid_until=TODAY + 365 * D,
            )
        app.calibration.record(
            app.ctx(app.admin),
            receiver,
            kind=CalibrationKind.CALIBRATION,
            done_on=TODAY,
            method="Lab calibration",
            reference="Trimble service centre, Kolkata",
            result=CalibrationResult.PASS,
            valid_until=TODAY + 365 * D,
            certificate=PDF,
        )
        documents = app.storage.documents.for_asset(receiver)
        assert len(documents) == 1 and documents[0].file is not None
        assert app.deployments.readiness(
            app.actor(app.pilot), asset_ids=[receiver], crew_ids=[app.surveyor.id]
        ).readiness.ok

    def test_failed_checks_ground_the_receiver(self, app: App, fleet: Fleet) -> None:
        with pytest.raises(RuleViolation, match="differences"):
            app.calibration.record(
                app.ctx(app.surveyor),
                fleet.base,
                kind=CalibrationKind.VERIFICATION,
                done_on=TODAY,
                method="RTK on control point",
                reference="GCP-KJR-07",
                result=CalibrationResult.PASS,
            )
        app.calibration.record(
            app.ctx(app.surveyor),
            fleet.base,
            kind=CalibrationKind.VERIFICATION,
            done_on=TODAY,
            method="RTK on control point",
            reference="GCP-KJR-07",
            result=CalibrationResult.FAIL,
            horizontal_mm=Decimal("85"),
            vertical_mm=Decimal("120"),
            notes="Vertical off by 12 cm",
        )
        assert status(app, fleet.base)[0] is Serviceability.UNSERVICEABLE
        reasons = app.maintenance.grounding_reasons(app.actor(app.admin), fleet.base)
        assert reasons == [
            "Calibration: last verification on 08 Nov 2026 failed: Vertical off by 12 cm"
        ]
        # The status button cannot return it to service while the failure stands.
        with pytest.raises(RuleViolation, match="cannot return to service yet"):
            app.assets.change_status(
                app.ctx(app.admin),
                fleet.base,
                StatusChange(serviceability=Serviceability.SERVICEABLE),
            )
        app.calibration.record(
            app.ctx(app.admin),
            fleet.base,
            kind=CalibrationKind.CALIBRATION,
            done_on=TODAY,
            method="Lab",
            reference="Service centre",
            result=CalibrationResult.ADJUSTED,
            valid_until=TODAY + 300 * D,
        )
        assert app.maintenance.grounding_reasons(app.actor(app.admin), fleet.base) == []
        assert len(app.calibration.records(app.actor(app.pilot), fleet.base)) == 2
        with pytest.raises(RuleViolation, match="does not track calibration"):
            app.calibration.record(
                app.ctx(app.admin),
                fleet.tripod,
                kind=CalibrationKind.VERIFICATION,
                done_on=TODAY,
                method="x",
                reference="y",
                result=CalibrationResult.PASS,
                horizontal_mm=Decimal(1),
            )


class TestAlerts:
    def test_one_list_of_everything(self, app: App, fleet: Fleet) -> None:
        battery_with_cycles(app, "BAT-0012", 200)
        app.maintenance.report_defect(app.ctx(app.pilot), fleet.tripod, description="Wobbles")
        app.stock.set_reorder_level(app.ctx(app.admin), TYPES["GCP_BANNER"].id, fleet.store, 60)
        app.storage.users.update(
            app.pilot.next_version(
                licence=app.pilot.licence.model_copy(update={"expires_on": TODAY + 20 * D})
            )
        )  # type: ignore[union-attr]
        register(app, "DRONE_AIRFRAME", "DRN-0099")  # no documents
        app.reservations.request(
            app.ctx(app.pilot),
            project_id=fleet.project,
            starts_on=TODAY + D,
            ends_on=TODAY + 2 * D,
            asset_ids=[fleet.tripod],
        )
        admin = app.alerts.alerts(app.actor(app.admin))
        categories = {a.category for a in admin}
        assert {"battery", "defect", "stock", "licence", "document", "reservation"} <= categories
        assert admin[0].severity == "danger"
        assert [a.severity for a in admin] == sorted(
            (a.severity for a in admin), key=lambda s: {"danger": 0, "warning": 1, "info": 2}[s]
        )
        pilot = app.alerts.alerts(app.actor(app.pilot))
        assert any(a.message.startswith("Your DGCA pilot certificate expires") for a in pilot)
        assert not any(a.category == "reservation" for a in pilot)  # only approvers
        assert not any("Waiting for assessment" in a.message for a in pilot)
