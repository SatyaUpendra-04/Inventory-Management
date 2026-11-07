"""Audit trail: one immutable entry per executed command."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ims.domain.common.ids import CommandId, EntryId, UserId
from ims.domain.common.model import UtcDateTime, ValueModel


class AuditEntry(ValueModel):
    id: EntryId
    command_id: CommandId
    at: UtcDateTime
    actor_id: UserId | None  # None only for first-run setup, before any user exists
    action: str = Field(min_length=1, max_length=80)
    entity: str = Field(min_length=1, max_length=80)
    entity_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
