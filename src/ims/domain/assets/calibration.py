"""GNSS calibration and verification records (ARCHITECTURE §4.5).

* A **calibration** is done by a lab or service centre and comes with a certificate and a
  valid-until date. Recording one also files the certificate as the item's calibration
  document, so the compliance checks from Sprint 4 keep a single source of truth.
* A **verification** is a field check against a known control point: the receiver's
  position is compared with the published coordinates and the differences recorded.

The latest result counts: if it failed, the receiver is grounded until a later record
passes. Records are append-only (sequenced per item); a mistake is corrected with a new
record, never by editing the old one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, CommandId, DocumentId, EntryId, UserId
from ims.domain.common.model import UtcDateTime, ValueModel


class CalibrationKind(StrEnum):
    CALIBRATION = "calibration"
    VERIFICATION = "verification"


class CalibrationResult(StrEnum):
    PASS = "pass"  # noqa: S105 - a calibration result, not a password
    ADJUSTED = "adjusted"  # out of tolerance, adjusted, now within it
    FAIL = "fail"


class CalibrationRecord(ValueModel):
    id: EntryId
    asset_id: AssetId
    sequence: int = Field(ge=1)
    kind: CalibrationKind
    done_on: date
    # e.g. "Lab calibration", "RTK on control point"
    method: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=200)  # lab name or control point ID
    result: CalibrationResult
    horizontal_mm: Decimal | None = Field(default=None, ge=0, le=100_000, decimal_places=1)
    vertical_mm: Decimal | None = Field(default=None, ge=0, le=100_000, decimal_places=1)
    valid_until: date | None = None
    document_id: DocumentId | None = None  # the certificate filed for a calibration
    notes: str = Field(default="", max_length=1000)
    recorded_at: UtcDateTime
    recorded_by: UserId
    command_id: CommandId

    @model_validator(mode="after")
    def _rules(self) -> CalibrationRecord:
        problems: list[str] = []
        if self.kind is CalibrationKind.CALIBRATION:
            if self.result is not CalibrationResult.FAIL and self.valid_until is None:
                problems.append("a calibration needs the date its certificate runs to")
        elif self.horizontal_mm is None and self.vertical_mm is None:
            problems.append("a verification records the differences found (mm)")
        if self.valid_until is not None and self.valid_until < self.done_on:
            problems.append("valid-until cannot be before the calibration")
        if self.result is CalibrationResult.FAIL and not self.notes.strip():
            problems.append("say what failed")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def check_new_record(
    existing: Sequence[CalibrationRecord], record: CalibrationRecord, today: date
) -> None:
    problems: list[str] = []
    if record.sequence != len(existing) + 1:
        problems.append("a record was added by someone else meanwhile; reload and try again")
    if record.done_on > today:
        problems.append("a calibration cannot be dated in the future")
    if problems:
        raise RuleViolation(problems)


def failed_reason(records: Sequence[CalibrationRecord]) -> str | None:
    """Why the receiver is grounded by its records, if it is."""
    if not records:
        return None
    latest = max(records, key=lambda r: (r.done_on, r.sequence))
    if latest.result is CalibrationResult.FAIL:
        return f"last {latest.kind.value} on {latest.done_on:%d %b %Y} failed: {latest.notes}"
    return None
