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
