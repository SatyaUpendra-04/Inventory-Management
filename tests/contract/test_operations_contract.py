"""Contract for projects, deployments, sorties and survey sessions."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import DEFAULT_CATALOGUE
from ims.domain.common.errors import AlreadyExists, ConflictError, NotFound
from ims.domain.common.ids import (
    AssetId,
    DeploymentId,
    EntryId,
    KitId,
    LocationId,
    ProjectId,
    SortieId,
    SurveySessionId,
    UserId,
    uuid7,
)
from ims.domain.operations.deployment import (
    Deployment,
    DeploymentState,
    ReturnCondition,
    ReturnLine,
)
from ims.domain.operations.field_logs import Sortie, SurveyMode, SurveySession
from ims.domain.operations.project import Project, ProjectStatus
from ims.domain.sites.site import Site, SiteKind
from ims.ports.repository import Storage
from tests.fakes import START

pytestmark = pytest.mark.contract

TYPES = {t.code: t for t in DEFAULT_CATALOGUE}
DAY = date(2026, 11, 8)


def _site(storage: Storage, code: str) -> Site:
    site = Site(id=LocationId(uuid7()), code=code, name=code.title(), kind=SiteKind.MINE_SITE)
    storage.sites.add(site)
    return site


def _asset(storage: Storage, code: str, tag: str) -> Asset:
    item_type = TYPES[code]
    if storage.item_types.get(item_type.id) is None:
        storage.item_types.add(item_type)
    asset = Asset(id=AssetId(uuid7()), item_type_id=item_type.id, asset_tag=tag,
                  serial_number=f"S-{tag}")  # fmt: skip
    storage.assets.add(asset)
    return asset


def _project(storage: Storage, site: Site, code: str, starts_on: date = DAY) -> Project:
    project = Project(
        id=ProjectId(uuid7()), code=code, name=f"Survey {code}", site_id=site.id,
        starts_on=starts_on, chief_pilot_id=UserId(uuid7()),
    )  # fmt: skip
    storage.projects.add(project)
    return project


class TestProjects:
    def test_round_trip_codes_order_and_versions(self, storage: Storage) -> None:
        site = _site(storage, "KJR-MINE")
        older = _project(storage, site, "kjr-2610", DAY - timedelta(days=30))
        newer = _project(storage, site, "kjr-2611")
        assert storage.projects.get(newer.id) == newer
        assert storage.projects.find_by_code("kjr 2611") == newer
        assert storage.projects.find_by_code("PRJ-NOPE") is None
        assert [p.id for p in storage.projects.list()] == [newer.id, older.id]
        with pytest.raises(AlreadyExists):
            storage.projects.add(newer)
        with pytest.raises(ConflictError):
            storage.projects.add(newer.model_copy(update={"id": ProjectId(uuid7())}))
        active = newer.next_version(status=ProjectStatus.ACTIVE, ends_on=DAY + timedelta(days=9))
        storage.projects.update(active)
        assert storage.projects.get(newer.id) == active
        with pytest.raises(ConflictError):
            storage.projects.update(active)
        removed = older.next_version(deleted_at=START)
        storage.projects.update(removed)
        assert [p.id for p in storage.projects.list()] == [newer.id]
        assert len(storage.projects.list(include_deleted=True)) == 2
        with pytest.raises(NotFound):
            storage.projects.update(
                newer.model_copy(update={"id": ProjectId(uuid7()), "code": "PRJ-X9", "version": 2})
            )


class TestDeploymentsAndLogs:
    def test_round_trip(self, storage: Storage) -> None:
        site = _site(storage, "KJR-MINE")
        project = _project(storage, site, "kjr-2611")
        other = _project(storage, site, "kjr-2612")
        drone = _asset(storage, "DRONE_AIRFRAME", "DRN-0001")
        battery = _asset(storage, "DRONE_BATTERY", "BAT-0001")
        receiver = _asset(storage, "GNSS_RECEIVER", "GNS-0001")
        crew = UserId(uuid7())
        first = Deployment(
            id=DeploymentId(uuid7()), project_id=project.id,
            asset_ids=(drone.id, battery.id, receiver.id), kit_ids=(KitId(uuid7()),),
            crew_ids=(crew,), gcp_quantity=20, gcp_site_id=site.id, deployed_on=DAY,
            created_at=START, created_by=crew,
        )  # fmt: skip
        second = first.model_copy(
            update={"id": DeploymentId(uuid7()), "project_id": other.id, "gcp_quantity": 0,
                    "gcp_site_id": None, "created_at": START + timedelta(hours=1)}
        )  # fmt: skip
        storage.deployments.add(first)
        storage.deployments.add(second)
        assert storage.deployments.get(first.id) == first
        assert storage.deployments.for_project(project.id) == [first]
        assert [d.id for d in storage.deployments.list()] == [second.id, first.id]
        with pytest.raises(AlreadyExists):
            storage.deployments.add(first)
        returned = first.next_version(
            state=DeploymentState.RETURNED, returned_on=DAY, returned_by=crew,
            returns=(ReturnLine(asset_id=drone.id),
                     ReturnLine(asset_id=battery.id, condition=ReturnCondition.LIMITED,
                                note="Swelling"),
                     ReturnLine(asset_id=receiver.id)),
            gcp_returned=15, gcp_consumed=5, return_site_id=site.id,
        )  # fmt: skip
        storage.deployments.update(returned)
        assert storage.deployments.get(first.id) == returned
        with pytest.raises(ConflictError):
            storage.deployments.update(returned)

        sortie = Sortie(
            id=SortieId(uuid7()), project_id=project.id, deployment_id=first.id,
            drone_id=drone.id, pilot_id=crew, flown_on=DAY, hours=Decimal("0.75"),
            battery_ids=(battery.id,), media_ids=(), recorded_at=START, recorded_by=crew,
            usage_entries=((drone.id, EntryId(uuid7())), (battery.id, EntryId(uuid7()))),
        )  # fmt: skip
        storage.sorties.add(sortie)
        assert storage.sorties.get(sortie.id) == sortie
        assert storage.sorties.for_project(project.id) == [sortie]
        assert storage.sorties.for_project(other.id) == []
        voided = sortie.next_version(voided_at=START, void_reason="Duplicate")
        storage.sorties.update(voided)
        assert storage.sorties.list() == [voided]

        session = SurveySession(
            id=SurveySessionId(uuid7()), project_id=project.id, deployment_id=first.id,
            surveyor_id=crew, surveyed_on=DAY, hours=Decimal("3"), mode=SurveyMode.PPK,
            base_id=receiver.id, area_ha=Decimal("42.5"), points=380,
            fix_rate=Decimal("97.5"), recorded_at=START, recorded_by=crew,
        )  # fmt: skip
        storage.survey_sessions.add(session)
        assert storage.survey_sessions.get(session.id) == session
        assert storage.survey_sessions.for_project(project.id) == [session]
        assert storage.survey_sessions.list() == [session]
        updated = session.next_version(notes="Checked")
        storage.survey_sessions.update(updated)
        assert storage.survey_sessions.get(session.id) == updated
        with pytest.raises(AlreadyExists):
            storage.survey_sessions.add(session)


class TestReservationsAndBookings:
    def test_round_trip_and_ledger_sequence(self, storage: Storage) -> None:
        from ims.domain.common.ids import CommandId, ReservationId
        from ims.domain.operations.reservation import (
            BookingChange,
            BookingEvent,
            Reservation,
            ReservationStatus,
        )

        site = _site(storage, "KJR-MINE")
        project = _project(storage, site, "kjr-2611")
        drone = _asset(storage, "DRONE_AIRFRAME", "DRN-0001")
        later = Reservation(
            id=ReservationId(uuid7()), project_id=project.id, asset_ids=(drone.id,),
            kit_ids=(KitId(uuid7()),), starts_on=DAY + timedelta(days=5),
            ends_on=DAY + timedelta(days=9), gcp_quantity=10, gcp_site_id=site.id,
            requested_by=UserId(uuid7()), requested_at=START,
        )  # fmt: skip
        sooner = later.model_copy(update={"id": ReservationId(uuid7()), "starts_on": DAY,
                                          "ends_on": DAY + timedelta(days=2)})  # fmt: skip
        storage.reservations.add(later)
        storage.reservations.add(sooner)
        assert storage.reservations.get(later.id) == later
        assert [r.id for r in storage.reservations.list()] == [sooner.id, later.id]
        assert [r.id for r in storage.reservations.for_project(project.id)] == [sooner.id, later.id]
        with pytest.raises(AlreadyExists):
            storage.reservations.add(later)
        approved = later.next_version(status=ReservationStatus.APPROVED, decided_by=UserId(uuid7()),
                                      decided_at=START)  # fmt: skip
        storage.reservations.update(approved)
        assert storage.reservations.get(later.id) == approved
        with pytest.raises(ConflictError):
            storage.reservations.update(approved)

        def event(seq: int, change: BookingChange) -> BookingEvent:
            return BookingEvent(
                id=EntryId(uuid7()), asset_id=drone.id, sequence=seq, change=change,
                reservation_id=later.id, project_id=project.id, starts_on=later.starts_on,
                ends_on=later.ends_on, recorded_at=START, recorded_by=UserId(uuid7()),
                command_id=CommandId(uuid7()),
            )  # fmt: skip

        booked = event(1, BookingChange.BOOKED)
        storage.bookings.append(booked)
        with pytest.raises(ConflictError):  # a second writer at the same sequence loses
            storage.bookings.append(event(1, BookingChange.BOOKED))
        with pytest.raises(AlreadyExists):
            storage.bookings.append(booked)
        released = event(2, BookingChange.RELEASED)
        storage.bookings.append(released)
        assert storage.bookings.for_asset(drone.id) == [booked, released]
        assert storage.bookings.for_asset(AssetId(uuid7())) == []


class TestMaintenanceStorage:
    def test_round_trips_sequences_and_unique_numbers(self, storage: Storage) -> None:
        from decimal import Decimal as Dec

        from ims.domain.assets.catalogue import Meter
        from ims.domain.common.ids import (
            CommandId,
            DefectId,
            MaintenanceTaskId,
            WorkOrderId,
        )
        from ims.domain.maintenance.defects import Defect, DefectState
        from ims.domain.maintenance.programme import MaintenanceTask, TaskCompletion
        from ims.domain.maintenance.work_orders import WorkOrder, WorkOrderState

        drone = _asset(storage, "DRONE_AIRFRAME", "DRN-0001")
        task = MaintenanceTask(
            id=MaintenanceTaskId(uuid7()),
            item_type_id=drone.item_type_id,
            name="Inspection",
            every_hours=Dec("50.5"),
            every_days=90,
            tolerance_hours=Dec(5),
            effective_from=DAY,
        )
        storage.maintenance_tasks.add(task)
        assert storage.maintenance_tasks.get(task.id) == task
        retired = task.next_version(is_active=False)
        storage.maintenance_tasks.update(retired)
        assert storage.maintenance_tasks.list() == []
        assert storage.maintenance_tasks.list(include_inactive=True) == [retired]

        def completion(seq: int) -> TaskCompletion:
            return TaskCompletion(
                id=EntryId(uuid7()),
                asset_id=drone.id,
                sequence=seq,
                task_id=task.id,
                done_on=DAY,
                meters={Meter.HOURS: Dec("12.25")},
                recorded_at=START,
                recorded_by=UserId(uuid7()),
                command_id=CommandId(uuid7()),
            )

        first = completion(1)
        storage.completions.append(first)
        with pytest.raises(ConflictError):
            storage.completions.append(completion(1))
        assert storage.completions.for_asset(drone.id) == [first]

        defect = Defect(
            id=DefectId(uuid7()),
            number="DEF-0001",
            asset_id=drone.id,
            description="Creak",
            reported_by=UserId(uuid7()),
            reported_at=START,
            found_on=DAY,
        )
        storage.defects.add(defect)
        with pytest.raises(ConflictError):
            storage.defects.add(defect.model_copy(update={"id": DefectId(uuid7())}))
        deferred = defect.next_version(
            state=DefectState.DEFERRED, limitation="Max wind 8 m/s", deferred_until=DAY
        )
        storage.defects.update(deferred)
        assert storage.defects.get(defect.id) == deferred
        assert storage.defects.for_asset(drone.id) == [deferred] == storage.defects.list()

        order = WorkOrder(
            id=WorkOrderId(uuid7()),
            number="WO-0001",
            asset_id=drone.id,
            title="Inspection",
            task_ids=(task.id,),
            defect_ids=(defect.id,),
            opened_by=UserId(uuid7()),
            opened_at=START,
        )
        storage.work_orders.add(order)
        with pytest.raises(ConflictError):
            storage.work_orders.add(order.model_copy(update={"id": WorkOrderId(uuid7())}))
        started = order.next_version(state=WorkOrderState.IN_PROGRESS)
        storage.work_orders.update(started)
        assert storage.work_orders.get(order.id) == started
        assert storage.work_orders.for_asset(drone.id) == [started] == storage.work_orders.list()
        with pytest.raises(ConflictError):
            storage.work_orders.update(started)


class TestBatteryAndCalibrationStorage:
    def test_round_trips_and_sequences(self, storage: Storage) -> None:
        from decimal import Decimal as Dec

        from ims.domain.assets.calibration import (
            CalibrationKind,
            CalibrationRecord,
            CalibrationResult,
        )
        from ims.domain.batteries import BatteryCheck, ChargeState, default_policies
        from ims.domain.common.ids import CommandId

        battery = _asset(storage, "DRONE_BATTERY", "BAT-0001")
        receiver = _asset(storage, "GNSS_RECEIVER", "GNS-0001")
        policy = next(p for p in default_policies() if p.item_type_id == battery.item_type_id)
        storage.battery_policies.add(policy)
        with pytest.raises(ConflictError):  # one set of limits per kind of battery
            storage.battery_policies.add(policy.model_copy(update={"id": uuid7()}))
        tighter = policy.next_version(cycle_limit=150)
        storage.battery_policies.update(tighter)
        assert storage.battery_policies.get(policy.id) == tighter
        assert storage.battery_policies.list() == [tighter]

        check = BatteryCheck(
            id=EntryId(uuid7()),
            asset_id=battery.id,
            sequence=1,
            checked_on=DAY,
            health_pct=91,
            internal_resistance_mohm=Dec("4.5"),
            cell_imbalance_mv=7,
            charge_state=ChargeState.STORAGE,
            recorded_at=START,
            recorded_by=UserId(uuid7()),
            command_id=CommandId(uuid7()),
        )
        storage.battery_checks.append(check)
        with pytest.raises(ConflictError):
            storage.battery_checks.append(check.model_copy(update={"id": EntryId(uuid7())}))
        assert storage.battery_checks.for_asset(battery.id) == [check]

        record = CalibrationRecord(
            id=EntryId(uuid7()),
            asset_id=receiver.id,
            sequence=1,
            kind=CalibrationKind.VERIFICATION,
            done_on=DAY,
            method="RTK on control point",
            reference="GCP-07",
            result=CalibrationResult.FAIL,
            horizontal_mm=Dec("12.5"),
            vertical_mm=Dec(70),
            notes="Vertical out",
            recorded_at=START,
            recorded_by=UserId(uuid7()),
            command_id=CommandId(uuid7()),
        )
        storage.calibrations.append(record)
        with pytest.raises(AlreadyExists):
            storage.calibrations.append(record)
        assert storage.calibrations.for_asset(receiver.id) == [record]
