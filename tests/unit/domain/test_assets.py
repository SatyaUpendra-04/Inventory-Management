from datetime import date

import pytest

from ims.domain.assets.asset import Asset, check_asset_against_type
from ims.domain.assets.catalogue import (
    DEFAULT_CATALOGUE,
    Category,
    Discipline,
    ItemType,
    Meter,
    TrackingMode,
    default_item_type_id,
)
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, uuid7

BY_CODE = {t.code: t for t in DEFAULT_CATALOGUE}


class TestDefaultCatalogue:
    def test_covers_the_company_equipment(self) -> None:
        expected = {
            "DRONE_AIRFRAME", "MOTOR", "PROPELLER_SET", "LANDING_GEAR", "HELIX_ANTENNA",
            "CAMERA", "LOGGER", "TELEMETRY_RADIO", "DRONE_BATTERY", "GNSS_BATTERY",
            "CONTROLLER_BATTERY", "GNSS_RECEIVER", "PPK_BASE", "CONTROLLER", "LAPTOP",
            "CARD_READER", "POWER_BANK", "DRONE_BATTERY_CHARGER", "GNSS_BATTERY_CHARGER",
            "CONTROLLER_CHARGER", "LIPO_CHECKER", "ANEMOMETER", "SD_CARD", "HARD_DISK",
            "TRIPOD", "BIPOD", "MONOPOD", "TRIBRACH", "GCP_BANNER",
        }  # fmt: skip
        assert set(BY_CODE) == expected

    def test_codes_ids_and_tag_prefixes_are_unique(self) -> None:
        assert len({t.id for t in DEFAULT_CATALOGUE}) == len(DEFAULT_CATALOGUE)
        prefixes = [t.tag_prefix for t in DEFAULT_CATALOGUE if t.tag_prefix]
        assert len(prefixes) == len(set(prefixes))

    def test_ids_are_stable_across_installations(self) -> None:
        assert BY_CODE["MOTOR"].id == default_item_type_id("motor")

    def test_tracking_modes(self) -> None:
        assert BY_CODE["GCP_BANNER"].tracking is TrackingMode.CONSUMABLE
        assert not BY_CODE["GCP_BANNER"].is_individually_tracked
        assert BY_CODE["TRIPOD"].tracking is TrackingMode.TAGGED
        assert BY_CODE["DRONE_BATTERY"].meters == frozenset({Meter.CYCLES})
        assert BY_CODE["MOTOR"].is_component
        assert BY_CODE["ANEMOMETER"].tracks_calibration
        assert BY_CODE["DRONE_BATTERY_CHARGER"].battery_family == "drone_flight"


def _type(**overrides: object) -> ItemType:
    data: dict[str, object] = {
        "id": default_item_type_id("TEST"),
        "code": "test",
        "name": "Test",
        "category": Category.FIELD_ELECTRONICS,
        "discipline": Discipline.SHARED,
        "tracking": TrackingMode.TAGGED,
        "tag_prefix": "tst",
    }
    data.update(overrides)
    return ItemType.build(**data)


class TestItemTypeRules:
    def test_normalises_code_and_prefix(self) -> None:
        item_type = _type()
        assert (item_type.code, item_type.tag_prefix) == ("TEST", "TST")

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"meters": frozenset({Meter.HOURS})}, "only serialized items can have usage meters"),
            ({"tracking": TrackingMode.CONSUMABLE}, "consumables are counted, not tagged"),
            (
                {"tracking": TrackingMode.CONSUMABLE, "tag_prefix": None, "tracks_warranty": True},
                "consumables cannot be components",
            ),
            ({"tag_prefix": None}, "need a tag prefix"),
            ({"is_component": True}, "components must be serialized"),
            ({"category": Category.BATTERY}, "batteries need a battery family"),
            ({"code": "1bad"}, "code must be"),
            ({"tag_prefix": "TOOLONG"}, "tag prefix must be"),
        ],
    )
    def test_inconsistent_definitions_are_rejected(
        self, overrides: dict[str, object], message: str
    ) -> None:
        with pytest.raises(RuleViolation, match=message):
            _type(**overrides)


def _asset(item_type: ItemType, **overrides: object) -> Asset:
    data: dict[str, object] = {
        "id": AssetId(uuid7()),
        "item_type_id": item_type.id,
        "asset_tag": f"{item_type.tag_prefix or 'XX'}-0001",
        "serial_number": "SN-1",
    }
    data.update(overrides)
    return Asset.build(**data)


class TestAssets:
    def test_tag_and_serial_are_normalised(self) -> None:
        asset = _asset(BY_CODE["MOTOR"], asset_tag=" mot-a12 ", serial_number=" ab 12/c ")
        assert (asset.asset_tag, asset.serial_number) == ("MOT-A12", "AB 12/C")
        assert _asset(BY_CODE["TRIPOD"], serial_number="  ").serial_number is None

    @pytest.mark.parametrize("tag", ["MOT1234", "M-1234", "MOT-12", "MOT-12#4"])
    def test_bad_tags_are_rejected(self, tag: str) -> None:
        with pytest.raises(RuleViolation, match="asset tag"):
            _asset(BY_CODE["MOTOR"], asset_tag=tag)

    def test_bad_serial_is_rejected(self) -> None:
        with pytest.raises(RuleViolation, match="serial number"):
            _asset(BY_CODE["MOTOR"], serial_number="#bad")

    def test_valid_asset_passes_type_checks(self) -> None:
        item_type = BY_CODE["LAPTOP"]
        asset = _asset(item_type, acquired_on=date(2025, 1, 1), warranty_until=date(2027, 1, 1))
        check_asset_against_type(asset, item_type)
        assert not asset.is_deleted

    def test_type_rules_report_all_problems(self) -> None:
        motor = BY_CODE["MOTOR"]
        asset = _asset(
            motor,
            asset_tag="ABC-0001",
            serial_number=None,
            acquired_on=date(2026, 1, 1),
            warranty_until=date(2025, 1, 1),
        )
        with pytest.raises(RuleViolation) as caught:
            check_asset_against_type(asset, motor)
        assert caught.value.problems == (
            "Motor must have a serial number",
            "asset tag must start with MOT-",
            "Motor does not track warranty",
            "warranty cannot end before the acquisition date",
        )

    def test_consumables_and_wrong_or_retired_types_are_rejected(self) -> None:
        motor = BY_CODE["MOTOR"]
        asset = _asset(motor)
        with pytest.raises(RuleViolation, match="does not belong"):
            check_asset_against_type(asset, BY_CODE["CAMERA"])
        with pytest.raises(RuleViolation, match="no longer in use"):
            check_asset_against_type(asset, motor.next_version(is_active=False))
        banner = BY_CODE["GCP_BANNER"]
        with pytest.raises(RuleViolation, match="counted stock"):
            check_asset_against_type(_asset(banner), banner)
