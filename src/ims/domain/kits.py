"""Kits: named sets of equipment deployed together, built from templates (ARCHITECTURE §4.0)."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import Field, field_validator, model_validator

from ims.domain.assets.catalogue import Discipline, ItemType, TrackingMode, default_item_type_id
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, ItemTypeId, KitId, KitTemplateId, LocationId
from ims.domain.common.model import UtcDateTime, ValueModel, VersionedRecord

_KIT_CODE = re.compile(r"^KIT-[A-Z0-9-]{2,16}$")
_TEMPLATE_NAMESPACE = uuid.UUID("5d3c9a1e-7b2f-4c8e-9a61-2f0e4b7c8d93")


class TemplateLine(ValueModel):
    item_type_id: ItemTypeId
    quantity: int = Field(ge=1, le=50)


class KitTemplate(VersionedRecord):
    id: KitTemplateId
    name: str = Field(min_length=1, max_length=60)
    discipline: Discipline
    lines: tuple[TemplateLine, ...]
    notes: str = Field(default="", max_length=500)
    is_active: bool = True

    @model_validator(mode="after")
    def _lines(self) -> KitTemplate:
        if not self.lines:
            raise ValueError("a template needs at least one line")
        types = [line.item_type_id for line in self.lines]
        if len(types) != len(set(types)):
            raise ValueError("each item type may appear only once in a template")
        return self

    def required(self) -> Counter[ItemTypeId]:
        return Counter({line.item_type_id: line.quantity for line in self.lines})


class Kit(VersionedRecord):
    id: KitId
    code: str
    name: str = Field(min_length=1, max_length=80)
    template_id: KitTemplateId | None = None
    members: tuple[AssetId, ...] = ()
    home_site_id: LocationId | None = None
    notes: str = Field(default="", max_length=1000)
    deleted_at: UtcDateTime | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        normalised = value.strip().upper()
        if not normalised.startswith("KIT-"):
            normalised = f"KIT-{normalised}"
        if not _KIT_CODE.match(normalised):
            raise ValueError("kit code must look like KIT-DRONE-01 (letters, digits, '-')")
        return normalised

    @model_validator(mode="after")
    def _unique_members(self) -> Kit:
        if len(self.members) != len(set(self.members)):
            raise ValueError("an asset can appear only once in a kit")
        return self

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@dataclass(frozen=True, slots=True)
class Completeness:
    missing: dict[ItemTypeId, int]
    extra: dict[ItemTypeId, int]

    @property
    def complete(self) -> bool:
        return not self.missing


def completeness(template: KitTemplate, member_types: Mapping[AssetId, ItemTypeId]) -> Completeness:
    """Compares a kit's members (asset -> item type) with what its template asks for."""
    have = Counter(member_types.values())
    need = template.required()
    missing = {t: n - have.get(t, 0) for t, n in need.items() if have.get(t, 0) < n}
    extra = {t: n - need.get(t, 0) for t, n in have.items() if n > need.get(t, 0)}
    return Completeness(missing=missing, extra=extra)


def check_member(item_type: ItemType, other_kit_code: str | None) -> None:
    problems: list[str] = []
    if item_type.tracking is TrackingMode.CONSUMABLE:
        problems.append(f"{item_type.name} is counted stock and cannot be a kit member")
    if other_kit_code is not None:
        problems.append(f"already in {other_kit_code}; remove it from that kit first")
    if problems:
        raise RuleViolation(problems)


def default_template_id(name: str) -> KitTemplateId:
    return KitTemplateId(uuid.uuid5(_TEMPLATE_NAMESPACE, name.lower()))


def _lines(spec: Mapping[str, int]) -> tuple[TemplateLine, ...]:
    return tuple(
        TemplateLine(item_type_id=default_item_type_id(code), quantity=n)
        for code, n in spec.items()
    )


DEFAULT_TEMPLATES: tuple[KitTemplate, ...] = (
    KitTemplate(
        id=default_template_id("Drone kit"),
        name="Drone kit",
        discipline=Discipline.DRONE,
        lines=_lines({
            "DRONE_AIRFRAME": 1, "DRONE_BATTERY": 4, "TELEMETRY_RADIO": 1, "PPK_BASE": 1,
            "LAPTOP": 1, "SD_CARD": 2, "CARD_READER": 1, "HARD_DISK": 1,
            "DRONE_BATTERY_CHARGER": 1, "LIPO_CHECKER": 1, "ANEMOMETER": 1, "POWER_BANK": 1,
        }),
        notes="Standard set for a mapping flight day.",
    ),
    KitTemplate(
        id=default_template_id("DGPS set"),
        name="DGPS set",
        discipline=Discipline.SURVEY,
        lines=_lines({
            "GNSS_RECEIVER": 2, "CONTROLLER": 1, "TRIPOD": 1, "TRIBRACH": 1, "BIPOD": 1,
            "GNSS_BATTERY": 4, "GNSS_BATTERY_CHARGER": 1, "CONTROLLER_CHARGER": 1,
        }),
        notes="Base and rover receivers with their accessories.",
    ),
)  # fmt: skip
