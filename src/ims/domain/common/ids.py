"""Identifiers (ADR-0003).

Records use UUIDv7 (RFC 9562): time-ordered, safe to generate offline on any machine.
IDs for records created by a command are *derived* from the command ID, so replaying
the same command produces the same IDs and is recognised as already applied.
"""

from __future__ import annotations

import secrets
import time
import uuid
from typing import NewType

UserId = NewType("UserId", uuid.UUID)
ItemTypeId = NewType("ItemTypeId", uuid.UUID)
AssetId = NewType("AssetId", uuid.UUID)
LocationId = NewType("LocationId", uuid.UUID)
ProjectId = NewType("ProjectId", uuid.UUID)
CommandId = NewType("CommandId", uuid.UUID)
EntryId = NewType("EntryId", uuid.UUID)

_VERSION_7 = 0x7
_VARIANT_RFC = 0b10


def uuid7(unix_ms: int | None = None) -> uuid.UUID:
    """Returns a version-7 UUID: 48-bit millisecond timestamp followed by 74 random bits."""
    ms = time.time_ns() // 1_000_000 if unix_ms is None else unix_ms
    if not 0 <= ms < 1 << 48:
        raise ValueError("timestamp out of range for UUIDv7")
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (ms << 80) | (_VERSION_7 << 76) | (rand_a << 64) | (_VARIANT_RFC << 62) | rand_b
    return uuid.UUID(int=value)


def uuid7_timestamp_ms(value: uuid.UUID) -> int:
    """Extracts the millisecond timestamp from a UUIDv7."""
    if value.version != _VERSION_7:
        raise ValueError("not a version-7 UUID")
    return value.int >> 80


def derive_id(command_id: uuid.UUID, purpose: str) -> uuid.UUID:
    """Deterministic ID for a record created by a command (stable across retries)."""
    if not purpose:
        raise ValueError("purpose must not be empty")
    return uuid.uuid5(command_id, purpose)


def new_command_id() -> CommandId:
    return CommandId(uuid7())
