"""Individually tracked assets (serialized and tagged items)."""

from __future__ import annotations

import re
from datetime import date

from pydantic import Field, field_validator

from ims.domain.assets.catalogue import ItemType, TrackingMode
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, ItemTypeId
from ims.domain.common.model import UtcDateTime, VersionedRecord

_ASSET_TAG = re.compile(r"^[A-Z]{2,4}-[A-Z0-9]{3,12}$")
_SERIAL = re.compile(r"^[A-Z0-9][A-Z0-9 ._/-]{0,63}$")


class Asset(VersionedRecord):
    """Master data for one physical unit. Its status lives in the status history."""

    id: AssetId
    item_type_id: ItemTypeId
    asset_tag: str
    serial_number: str | None = None
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    acquired_on: date | None = None
    warranty_until: date | None = None
    notes: str = Field(default="", max_length=2000)
    deleted_at: UtcDateTime | None = None

    @field_validator("asset_tag")
    @classmethod
    def _tag(cls, value: str) -> str:
        normalised = value.strip().upper()
        if not _ASSET_TAG.match(normalised):
            raise ValueError(
                "asset tag must look like PRE-1234 (2-4 letters, '-', 3-12 characters)"
            )
        return normalised

    @field_validator("serial_number")
    @classmethod
    def _serial(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalised = value.strip().upper()
        if not _SERIAL.match(normalised):
            raise ValueError("serial number contains characters that are not allowed")
        return normalised

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def check_asset_against_type(asset: Asset, item_type: ItemType) -> None:
    """Rules that depend on the item type (raises :class:`RuleViolation`)."""
    problems: list[str] = []
    if asset.item_type_id != item_type.id:
        problems.append("asset does not belong to this item type")
    if item_type.tracking is TrackingMode.CONSUMABLE:
        problems.append(f"{item_type.name} is counted stock and cannot be registered as an asset")
    if item_type.tracking is TrackingMode.SERIALIZED and asset.serial_number is None:
        problems.append(f"{item_type.name} must have a serial number")
    if item_type.tag_prefix and not asset.asset_tag.startswith(f"{item_type.tag_prefix}-"):
        problems.append(f"asset tag must start with {item_type.tag_prefix}-")
    if asset.warranty_until is not None and not item_type.tracks_warranty:
        problems.append(f"{item_type.name} does not track warranty")
    if (
        asset.warranty_until is not None
        and asset.acquired_on is not None
        and asset.warranty_until < asset.acquired_on
    ):
        problems.append("warranty cannot end before the acquisition date")
    if not item_type.is_active:
        problems.append(f"{item_type.name} is no longer in use")
    if problems:
        raise RuleViolation(problems)
