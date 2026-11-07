"""Equipment catalogue: item types and how each one is tracked (ARCHITECTURE.md §4.0).

Admins can add item types later; the defaults below cover the company's current drone
and survey equipment. Default item-type IDs are derived from their codes, so every
installation (and every backend) gives the same item type the same ID.
"""

from __future__ import annotations

import re
import uuid
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from ims.domain.common.ids import ItemTypeId
from ims.domain.common.model import VersionedRecord

_CATALOGUE_NAMESPACE = uuid.UUID("0b6f3b9e-6f7a-4d43-9a8e-3f1d2c5b7a10")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")
_PREFIX = re.compile(r"^[A-Z]{2,4}$")


class TrackingMode(StrEnum):
    SERIALIZED = "serialized"  # individual unit, usage meters and full lifecycle
    TAGGED = "tagged"  # individual unit by asset tag, custody and condition only
    CONSUMABLE = "consumable"  # counted stock, every movement in the stock ledger


class Category(StrEnum):
    DRONE = "drone"
    DRONE_COMPONENT = "drone_component"
    BATTERY = "battery"
    GNSS = "gnss"
    FIELD_ELECTRONICS = "field_electronics"
    SURVEY_ACCESSORY = "survey_accessory"
    DATA_MEDIA = "data_media"
    CONSUMABLE = "consumable"


class Discipline(StrEnum):
    """Which crew normally takes the item into the field."""

    DRONE = "drone"  # Pilots
    SURVEY = "survey"  # Surveyors
    SHARED = "shared"  # either


class Meter(StrEnum):
    HOURS = "hours"
    CYCLES = "cycles"
    LANDINGS = "landings"


class ItemType(VersionedRecord):
    id: ItemTypeId
    code: str
    name: str = Field(min_length=1, max_length=80)
    category: Category
    discipline: Discipline
    tracking: TrackingMode
    meters: frozenset[Meter] = frozenset()
    is_component: bool = False  # can be installed on a drone airframe
    tag_prefix: str | None = None
    tracks_warranty: bool = False
    tracks_calibration: bool = False
    battery_family: str | None = None  # for batteries: their family; chargers: what they charge
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        normalised = value.strip().upper()
        if not _CODE.match(normalised):
            raise ValueError("code must be 2-40 capital letters, digits or '_'")
        return normalised

    @field_validator("tag_prefix")
    @classmethod
    def _prefix(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip().upper()
        if not _PREFIX.match(normalised):
            raise ValueError("tag prefix must be 2-4 capital letters")
        return normalised

    @model_validator(mode="after")
    def _consistent(self) -> ItemType:
        problems: list[str] = []
        if self.tracking is not TrackingMode.SERIALIZED and self.meters:
            problems.append("only serialized items can have usage meters")
        if self.tracking is TrackingMode.CONSUMABLE:
            if self.is_component or self.tracks_warranty or self.tracks_calibration:
                problems.append("consumables cannot be components or track warranty or calibration")
            if self.tag_prefix is not None:
                problems.append("consumables are counted, not tagged")
        elif self.tag_prefix is None:
            problems.append("individually tracked items need a tag prefix")
        if self.is_component and self.tracking is not TrackingMode.SERIALIZED:
            problems.append("components must be serialized")
        if self.category is Category.BATTERY and self.battery_family is None:
            problems.append("batteries need a battery family")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_individually_tracked(self) -> bool:
        return self.tracking is not TrackingMode.CONSUMABLE


def default_item_type_id(code: str) -> ItemTypeId:
    return ItemTypeId(uuid.uuid5(_CATALOGUE_NAMESPACE, code.upper()))


def _t(code: str, name: str, category: Category, discipline: Discipline, tracking: TrackingMode,
       *, meters: tuple[Meter, ...] = (), component: bool = False, prefix: str | None = None,
       warranty: bool = False, calibration: bool = False,
       family: str | None = None) -> ItemType:  # fmt: skip
    return ItemType.build(
        id=default_item_type_id(code), code=code, name=name, category=category,
        discipline=discipline, tracking=tracking, meters=frozenset(meters),
        is_component=component, tag_prefix=prefix, tracks_warranty=warranty,
        tracks_calibration=calibration, battery_family=family,
    )  # fmt: skip


_S, _T, _C = TrackingMode.SERIALIZED, TrackingMode.TAGGED, TrackingMode.CONSUMABLE
_DR, _SV, _SH = Discipline.DRONE, Discipline.SURVEY, Discipline.SHARED
_H, _CY, _L = Meter.HOURS, Meter.CYCLES, Meter.LANDINGS

DEFAULT_CATALOGUE: tuple[ItemType, ...] = (
    # Drone and installable components (serialized, with meters)
    _t("DRONE_AIRFRAME", "Drone airframe", Category.DRONE, _DR, _S,
       meters=(_H, _CY, _L), prefix="DRN", warranty=True),
    _t("MOTOR", "Motor", Category.DRONE_COMPONENT, _DR, _S,
       meters=(_H,), component=True, prefix="MOT"),
    _t("PROPELLER_SET", "Propeller set", Category.DRONE_COMPONENT, _DR, _S,
       meters=(_H,), component=True, prefix="PRP"),
    _t("LANDING_GEAR", "Landing gear (legs)", Category.DRONE_COMPONENT, _DR, _S,
       meters=(_H, _L), component=True, prefix="LDG"),
    _t("HELIX_ANTENNA", "Helix GPS antenna", Category.DRONE_COMPONENT, _DR, _S,
       meters=(_H,), component=True, prefix="HLX"),
    _t("CAMERA", "Camera / payload", Category.DRONE_COMPONENT, _DR, _S,
       meters=(_H,), component=True, prefix="CAM", warranty=True),
    _t("LOGGER", "Logger", Category.DRONE_COMPONENT, _DR, _S,
       meters=(_H,), component=True, prefix="LOG"),
    _t("TELEMETRY_RADIO", "Telemetry radio", Category.DRONE_COMPONENT, _DR, _S,
       meters=(_H,), component=True, prefix="TEL"),
    # Batteries (own lifecycle)
    _t("DRONE_BATTERY", "Drone flight battery", Category.BATTERY, _DR, _S,
       meters=(_CY,), prefix="BAT", family="drone_flight"),
    _t("GNSS_BATTERY", "DGPS receiver battery", Category.BATTERY, _SV, _S,
       meters=(_CY,), prefix="GBT", family="gnss_receiver"),
    _t("CONTROLLER_BATTERY", "Controller battery", Category.BATTERY, _SV, _S,
       meters=(_CY,), prefix="CBT", family="controller"),
    # GNSS
    _t("GNSS_RECEIVER", "DGPS receiver (base / rover)", Category.GNSS, _SV, _S,
       meters=(_H,), prefix="GNS", warranty=True, calibration=True),
    _t("PPK_BASE", "PPK base station", Category.GNSS, _DR, _S,
       meters=(_H,), prefix="PPK", warranty=True, calibration=True),
    _t("CONTROLLER", "Survey controller", Category.GNSS, _SV, _S,
       prefix="CTL", warranty=True),
    # Field electronics and tools (tagged)
    _t("LAPTOP", "Laptop", Category.FIELD_ELECTRONICS, _DR, _T, prefix="LAP", warranty=True),
    _t("CARD_READER", "Card reader", Category.FIELD_ELECTRONICS, _DR, _T, prefix="CRD"),
    _t("POWER_BANK", "Power bank", Category.FIELD_ELECTRONICS, _SH, _T, prefix="PWB"),
    _t("DRONE_BATTERY_CHARGER", "Drone battery charger", Category.FIELD_ELECTRONICS, _DR, _T,
       prefix="DCH", family="drone_flight"),
    _t("GNSS_BATTERY_CHARGER", "DGPS battery charger", Category.FIELD_ELECTRONICS, _SV, _T,
       prefix="GCH", family="gnss_receiver"),
    _t("CONTROLLER_CHARGER", "Controller charger", Category.FIELD_ELECTRONICS, _SV, _T,
       prefix="CCH", family="controller"),
    _t("LIPO_CHECKER", "LiPo checker", Category.FIELD_ELECTRONICS, _DR, _T, prefix="LPC"),
    _t("ANEMOMETER", "Anemometer", Category.FIELD_ELECTRONICS, _DR, _T,
       prefix="ANM", calibration=True),
    # Data media (tagged, traced to projects)
    _t("SD_CARD", "SD card", Category.DATA_MEDIA, _DR, _T, prefix="SDC"),
    _t("HARD_DISK", "Hard disk", Category.DATA_MEDIA, _SH, _T, prefix="HDD", warranty=True),
    # Survey accessories (tagged)
    _t("TRIPOD", "Tripod", Category.SURVEY_ACCESSORY, _SV, _T, prefix="TRP"),
    _t("BIPOD", "Bipod", Category.SURVEY_ACCESSORY, _SV, _T, prefix="BIP"),
    _t("MONOPOD", "Monopod", Category.SURVEY_ACCESSORY, _SV, _T, prefix="MNP"),
    _t("TRIBRACH", "Tribrach", Category.SURVEY_ACCESSORY, _SV, _T, prefix="TBR"),
    # Consumables (counted stock)
    _t("GCP_BANNER", "GCP banner", Category.CONSUMABLE, _SH, _C),
)  # fmt: skip
