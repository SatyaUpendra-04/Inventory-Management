"""Firmware history for drones, receivers and controllers (append-only)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from pydantic import Field, field_validator

from ims.domain.common.errors import RuleViolation
from ims.domain.common.ids import AssetId, CommandId, EntryId, UserId
from ims.domain.common.model import UtcDateTime, ValueModel

_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+ -]{0,39}$")


class FirmwareRecord(ValueModel):
    id: EntryId
    asset_id: AssetId
    sequence: int = Field(ge=1)
    version: str
    installed_on: date
    recorded_at: UtcDateTime
    recorded_by: UserId
    command_id: CommandId
    note: str = Field(default="", max_length=500)

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        cleaned = value.strip()
        if not _VERSION.match(cleaned):
            raise ValueError(
                "firmware version must be 1-40 letters, digits, '.', '-', '+' or spaces"
            )
        return cleaned


def check_new_firmware(existing: Sequence[FirmwareRecord], record: FirmwareRecord) -> None:
    problems: list[str] = []
    if record.sequence != len(existing) + 1:
        problems.append("firmware was recorded by someone else meanwhile; reload and try again")
    if existing and record.installed_on < existing[-1].installed_on:
        problems.append("firmware dates must not go backwards")
    if existing and record.version == existing[-1].version:
        problems.append(f"version {record.version} is already the current firmware")
    if problems:
        raise RuleViolation(problems)


def current_version(records: Sequence[FirmwareRecord]) -> str | None:
    return records[-1].version if records else None
