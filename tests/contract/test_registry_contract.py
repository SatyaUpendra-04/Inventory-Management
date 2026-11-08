"""Contract for configuration, documents, firmware, kits, templates and reorder levels."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from ims.domain.assets.asset import Asset
from ims.domain.assets.catalogue import DEFAULT_CATALOGUE
from ims.domain.assets.configuration import ConfigChange, ConfigEvent
from ims.domain.assets.documents import AssetDocument, DocumentKind
from ims.domain.assets.firmware import FirmwareRecord
from ims.domain.common.errors import AlreadyExists, ConflictError
from ims.domain.common.ids import (
    AssetId,
    CommandId,
    DocumentId,
    EntryId,
    KitId,
    LocationId,
    UserId,
    uuid7,
)
from ims.domain.kits import DEFAULT_TEMPLATES, Kit
from ims.domain.stock.reorder import ReorderLevel, reorder_level_id
from ims.ports.repository import Storage
from tests.fakes import START

pytestmark = pytest.mark.contract

TYPES = {t.code: t for t in DEFAULT_CATALOGUE}


def _asset(storage: Storage, code: str, tag: str, serial: str | None = "S") -> Asset:
    item_type = TYPES[code]
    if storage.item_types.get(item_type.id) is None:
        storage.item_types.add(item_type)
    asset = Asset(
        id=AssetId(uuid7()),
        item_type_id=item_type.id,
        asset_tag=tag,
        serial_number=f"{serial}-{tag}" if serial else None,
        home_site_id=LocationId(uuid7()),
    )
    storage.assets.add(asset)
    return asset


def _event(
    component: Asset, parent: Asset, seq: int, change: ConfigChange, minutes: int
) -> ConfigEvent:
    return ConfigEvent(
        id=EntryId(uuid7()),
        component_id=component.id,
        sequence=seq,
        change=change,
        parent_id=parent.id,
        position="Motor 1",
        recorded_at=START + timedelta(minutes=minutes),
        recorded_by=UserId(uuid7()),
        command_id=CommandId(uuid7()),
        note="swap",
    )


class TestConfiguration:
    def test_streams_and_parent_lookup(self, storage: Storage) -> None:
        drone = _asset(storage, "DRONE_AIRFRAME", "DRN-0001")
        other = _asset(storage, "DRONE_AIRFRAME", "DRN-0002")
        motor = _asset(storage, "MOTOR", "MOT-0001")
        e1 = _event(motor, drone, 1, ConfigChange.INSTALLED, 1)
        e2 = _event(motor, drone, 2, ConfigChange.REMOVED, 2)
        e3 = _event(motor, other, 3, ConfigChange.INSTALLED, 3)
        for e in (e1, e2, e3):
            storage.configuration.append(e)
        assert storage.configuration.for_component(motor.id) == [e1, e2, e3]
        assert storage.configuration.for_parent(drone.id) == [e1, e2]
        assert storage.configuration.for_parent(other.id) == [e3]
        assert storage.assets.get(drone.id) == drone  # home site round-trips
        with pytest.raises(ConflictError):
            storage.configuration.append(_event(motor, other, 3, ConfigChange.REMOVED, 4))
        with pytest.raises(AlreadyExists):
            storage.configuration.append(e3)


class TestDocuments:
    def test_round_trip_and_soft_delete(self, storage: Storage) -> None:
        drone = _asset(storage, "DRONE_AIRFRAME", "DRN-0001")
        insurance = AssetDocument(
            id=DocumentId(uuid7()),
            asset_id=drone.id,
            kind=DocumentKind.INSURANCE,
            reference="POL-778812",
            issuer="Example General",
            issued_on=date(2026, 4, 1),
            valid_until=date(2027, 3, 31),
            file="a" * 64 + ".pdf",
            notes="Third party",
        )
        uin = AssetDocument(id=DocumentId(uuid7()), asset_id=drone.id, kind=DocumentKind.UIN,
                            reference="UA0012345678")  # fmt: skip
        storage.documents.add(insurance)
        storage.documents.add(uin)
        assert storage.documents.get(insurance.id) == insurance
        assert {d.id for d in storage.documents.for_asset(drone.id)} == {insurance.id, uin.id}
        storage.documents.update(uin.next_version(deleted_at=START))
        assert storage.documents.for_asset(drone.id) == [insurance]
        assert len(storage.documents.for_asset(drone.id, include_deleted=True)) == 2
        assert storage.documents.list() == [insurance]
        with pytest.raises(ConflictError):
            storage.documents.update(insurance.next_version(notes="a").next_version(notes="b"))


class TestFirmware:
    def test_append_in_sequence(self, storage: Storage) -> None:
        drone = _asset(storage, "DRONE_AIRFRAME", "DRN-0001")
        records = [
            FirmwareRecord(
                id=EntryId(uuid7()),
                asset_id=drone.id,
                sequence=n,
                version=f"v{n}.0",
                installed_on=date(2026, n, 1),
                recorded_at=START,
                recorded_by=UserId(uuid7()),
                command_id=CommandId(uuid7()),
                note="update",
            )
            for n in (1, 2)
        ]
        for r in records:
            storage.firmware.append(r)
        assert storage.firmware.for_asset(drone.id) == records
        with pytest.raises(ConflictError):
            storage.firmware.append(records[1].model_copy(update={"id": uuid7()}))


class TestKits:
    def test_templates(self, storage: Storage) -> None:
        drone_kit, dgps = DEFAULT_TEMPLATES
        storage.kit_templates.add(drone_kit)
        storage.kit_templates.add(dgps)
        assert storage.kit_templates.get(drone_kit.id) == drone_kit
        assert [t.name for t in storage.kit_templates.list()] == ["DGPS set", "Drone kit"]
        with pytest.raises(ConflictError):  # names are unique regardless of case
            storage.kit_templates.add(
                drone_kit.model_copy(update={"id": uuid7(), "name": "DRONE KIT"})
            )
        storage.kit_templates.update(dgps.next_version(is_active=False))
        assert [t.name for t in storage.kit_templates.list()] == ["Drone kit"]
        assert len(storage.kit_templates.list(include_inactive=True)) == 2

    def test_kits_membership_and_codes(self, storage: Storage) -> None:
        drone = _asset(storage, "DRONE_AIRFRAME", "DRN-0001")
        battery = _asset(storage, "DRONE_BATTERY", "BAT-0001")
        kit = Kit(id=KitId(uuid7()), code="drone-01", name="Drone kit 1",
                  template_id=DEFAULT_TEMPLATES[0].id, members=(drone.id, battery.id),
                  home_site_id=LocationId(uuid7()), notes="Main")  # fmt: skip
        storage.kits.add(kit)
        assert kit.code == "KIT-DRONE-01"
        assert storage.kits.get(kit.id) == kit
        assert storage.kits.find_by_code("drone-01") == kit
        assert storage.kits.find_by_member(battery.id) == kit
        assert storage.kits.find_by_member(AssetId(uuid7())) is None
        with pytest.raises(ConflictError):
            storage.kits.add(Kit(id=KitId(uuid7()), code="KIT-DRONE-01", name="Copy"))
        storage.kits.update(kit.next_version(deleted_at=START))
        assert storage.kits.find_by_member(battery.id) is None
        assert storage.kits.list() == [] and len(storage.kits.list(include_deleted=True)) == 1


class TestReorderLevels:
    def test_one_per_item_type_and_site(self, storage: Storage) -> None:
        banner = TYPES["GCP_BANNER"]
        storage.item_types.add(banner)
        site = LocationId(uuid7())
        level_id = reorder_level_id(banner.id, site)
        level = ReorderLevel(id=level_id, item_type_id=banner.id, location_id=site, level=20)
        storage.reorder_levels.add(level)
        assert storage.reorder_levels.get(level_id) == level
        storage.reorder_levels.update(level.next_version(level=30))
        assert storage.reorder_levels.list()[0].level == 30
        with pytest.raises(ConflictError):
            storage.reorder_levels.add(level.model_copy(update={"id": uuid7()}))
