"""Compliance documents held for an asset, with expiry status (ARCHITECTURE §4.6).

Under India's Drone Rules (2021, amended 2022) each drone has a Unique Identification
Number on the Digital Sky platform, issued against the manufacturer's Type Certificate,
and non-nano drones need third-party insurance. Survey instruments carry calibration
certificates. The exact rules must be confirmed against current DGCA guidance; they are
modelled here as document kinds and checks that are easy to change.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.assets.catalogue import Category, ItemType
from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, DocumentId
from ims.domain.common.model import UtcDateTime, VersionedRecord

EXPIRY_WARNING_DAYS = 30


class DocumentKind(StrEnum):
    UIN = "uin"  # Digital Sky Unique Identification Number
    TYPE_CERTIFICATE = "type_certificate"
    INSURANCE = "insurance"  # third-party insurance
    CALIBRATION = "calibration"
    OTHER = "other"


DOCUMENT_LABELS = {
    DocumentKind.UIN: "UIN (Digital Sky)",
    DocumentKind.TYPE_CERTIFICATE: "Type certificate",
    DocumentKind.INSURANCE: "Third-party insurance",
    DocumentKind.CALIBRATION: "Calibration certificate",
    DocumentKind.OTHER: "Other document",
}

_DRONE_ONLY = frozenset({DocumentKind.UIN, DocumentKind.TYPE_CERTIFICATE, DocumentKind.INSURANCE})
_MUST_EXPIRE = frozenset({DocumentKind.INSURANCE, DocumentKind.CALIBRATION})


class AssetDocument(VersionedRecord):
    id: DocumentId
    asset_id: AssetId
    kind: DocumentKind
    reference: str = Field(min_length=1, max_length=80)  # number on the document
    issuer: str = Field(default="", max_length=100)
    issued_on: date | None = None
    valid_until: date | None = None
    file: str | None = None  # FileStore reference to a scan
    notes: str = Field(default="", max_length=1000)
    deleted_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def _dates(self) -> AssetDocument:
        problems: list[str] = []
        if self.kind in _MUST_EXPIRE and self.valid_until is None:
            problems.append(f"{DOCUMENT_LABELS[self.kind]} needs a valid-until date")
        if self.issued_on and self.valid_until and self.valid_until < self.issued_on:
            problems.append("valid-until cannot be before the issue date")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def status_on(self, day: date) -> str:
        """``valid``, ``expiring`` (within 30 days), ``expired``, or ``permanent``."""
        if self.valid_until is None:
            return "permanent"
        remaining = (self.valid_until - day).days
        if remaining < 0:
            return "expired"
        return "expiring" if remaining <= EXPIRY_WARNING_DAYS else "valid"


def allowed_kinds(item_type: ItemType) -> list[DocumentKind]:
    """The document kinds an asset of this type can hold, in display order."""
    return [
        kind
        for kind in DocumentKind
        if (kind not in _DRONE_ONLY or item_type.category is Category.DRONE)
        and (kind is not DocumentKind.CALIBRATION or item_type.tracks_calibration)
    ]


def check_document_for_type(document: AssetDocument, item_type: ItemType) -> None:
    if document.kind in _DRONE_ONLY and item_type.category is not Category.DRONE:
        raise RuleViolation(f"{DOCUMENT_LABELS[document.kind]} applies to drone airframes only.")
    if document.kind is DocumentKind.CALIBRATION and not item_type.tracks_calibration:
        raise RuleViolation(f"{item_type.name} does not track calibration.")


def compliance_problems(
    item_type: ItemType, documents: Iterable[AssetDocument], today: date
) -> list[tuple[str, str]]:
    """What stops this asset being compliant, as (severity, message) pairs.

    Severity is ``danger`` (missing or expired) or ``warning`` (expiring soon).
    """
    current = [d for d in documents if not d.is_deleted]

    def best(kind: DocumentKind) -> AssetDocument | None:
        matches = [d for d in current if d.kind is kind]
        return max(matches, key=lambda d: d.valid_until or date.max, default=None)

    required: list[DocumentKind] = []
    if item_type.category is Category.DRONE:
        required += [DocumentKind.UIN, DocumentKind.INSURANCE]
    if item_type.tracks_calibration:
        required.append(DocumentKind.CALIBRATION)

    problems: list[tuple[str, str]] = []
    for kind in required:
        label = DOCUMENT_LABELS[kind]
        document = best(kind)
        if document is None:
            problems.append(("danger", f"{label} missing"))
            continue
        status = document.status_on(today)
        if status == "expired":
            problems.append(("danger", f"{label} expired {document.valid_until:%d %b %Y}"))
        elif status == "expiring":
            problems.append(("warning", f"{label} expires {document.valid_until:%d %b %Y}"))
    return problems
