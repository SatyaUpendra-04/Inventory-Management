"""Sites (rules catalogue L1, L2).

A site is any place equipment or stock can be: a store, a mine site, a workshop or an
office. Site IDs are the ``LocationId`` used by the stock ledger.
"""

from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from ims.domain.common.ids import LocationId
from ims.domain.common.model import UtcDateTime, VersionedRecord

_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,19}$")


class SiteKind(StrEnum):
    STORE = "store"
    MINE_SITE = "mine_site"
    WORKSHOP = "workshop"
    OFFICE = "office"


class SiteStatus(StrEnum):
    ACTIVE = "active"
    PLANNED = "planned"
    INACTIVE = "inactive"


class Site(VersionedRecord):
    id: LocationId
    code: str
    name: str = Field(min_length=1, max_length=100)
    kind: SiteKind
    region: str = Field(default="", max_length=100)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    area_hectares: Decimal | None = None
    mineral: str = Field(default="", max_length=60)
    status: SiteStatus = SiteStatus.ACTIVE
    notes: str = Field(default="", max_length=2000)
    deleted_at: UtcDateTime | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        normalised = value.strip().upper()
        if not _CODE.match(normalised):
            raise ValueError("site code must be 2-20 capital letters, digits or '-'")
        return normalised

    @model_validator(mode="after")
    def _rules(self) -> Site:
        problems: list[str] = []
        if (self.latitude is None) != (self.longitude is None):
            problems.append("enter both latitude and longitude, or neither")
        if self.latitude is not None and not Decimal(-90) <= self.latitude <= Decimal(90):
            problems.append("latitude must be between -90 and 90")
        if self.longitude is not None and not Decimal(-180) <= self.longitude <= Decimal(180):
            problems.append("longitude must be between -180 and 180")
        if self.area_hectares is not None and self.area_hectares < 0:
            problems.append("area cannot be negative")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def label(self) -> str:
        return f"{self.code} · {self.name}"
