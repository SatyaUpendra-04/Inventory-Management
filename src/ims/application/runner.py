"""Runs commands safely without multi-record transactions (ADR-0002, ADR-0003).

Every command:

1. Returns the earlier result immediately if its ID was already completed.
2. Creates records with IDs derived from the command ID, so a retry after a crash
   finds its own earlier writes (``AlreadyExists``) and carries on instead of
   duplicating them.
3. Writes one audit entry, then marks the command complete.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ims.application.context import CommandContext
from ims.domain.audit import AuditEntry
from ims.domain.common.errors import AlreadyExists, ConflictError
from ims.domain.common.ids import EntryId
from ims.ports.clock import Clock
from ims.ports.repository import CommandRecord, Storage


@dataclass(frozen=True, slots=True)
class Outcome:
    entity: str
    entity_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class _Versioned(Protocol):
    @property
    def version(self) -> int: ...


def add_once[R](add: Callable[[R], None], record: R) -> None:
    """Adds ``record``; if this command already added it, that is fine."""
    with contextlib.suppress(AlreadyExists):
        add(record)


def update_once[R: _Versioned](
    update: Callable[[R], None], get_current: Callable[[], R | None], record: R
) -> None:
    """Saves a new version; if a retry finds it already saved identically, that is fine."""
    try:
        update(record)
    except ConflictError:
        if get_current() != record:
            raise


class CommandRunner:
    def __init__(self, storage: Storage, clock: Clock) -> None:
        self._storage = storage
        self._clock = clock

    def run(self, ctx: CommandContext, action: str, execute: Callable[[], Outcome]) -> str:
        previous = self._storage.commands.get(ctx.command_id)
        if previous is not None:
            if previous.action != action:
                raise ConflictError("This command ID was already used for a different action.")
            return previous.result_id

        outcome = execute()
        actor_id = ctx.actor.user_id if ctx.actor else None
        now = self._clock.now()
        add_once(
            self._storage.audit.append,
            AuditEntry(
                id=EntryId(ctx.derive("audit")),
                command_id=ctx.command_id,
                at=now,
                actor_id=actor_id,
                action=action,
                entity=outcome.entity,
                entity_id=outcome.entity_id,
                before=outcome.before,
                after=outcome.after,
            ),
        )
        add_once(
            self._storage.commands.record,
            CommandRecord(
                command_id=ctx.command_id,
                action=action,
                actor_id=actor_id,
                completed_at=now,
                result_id=outcome.entity_id,
            ),
        )
        return outcome.entity_id
