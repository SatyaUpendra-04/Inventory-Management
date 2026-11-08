"""Reorder levels: alert when stock at a site falls to this many or fewer."""

from __future__ import annotations

import uuid

from pydantic import Field

from ims.domain.common.ids import ItemTypeId, LocationId
from ims.domain.common.model import VersionedRecord

_NAMESPACE = uuid.UUID("a1f0c2d4-3b5e-4f67-8a9b-0c1d2e3f4a5b")


class ReorderLevel(VersionedRecord):
    id: uuid.UUID
    item_type_id: ItemTypeId
    location_id: LocationId
    level: int = Field(ge=0, le=100_000)


def reorder_level_id(item_type_id: ItemTypeId, location_id: LocationId) -> uuid.UUID:
    """One reorder level per item type and site, with a stable ID."""
    return uuid.uuid5(_NAMESPACE, f"{item_type_id}:{location_id}")
