"""Base classes for domain records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ims.domain.common.errors import RuleViolation


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_require_utc)]
"""A timestamp that is always stored in UTC (ADR-0003)."""


class ValueModel(BaseModel):
    """Immutable value object: equality by content, no extra fields allowed."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    @classmethod
    def build(cls, **data: Any) -> Self:
        """Validates ``data`` and raises :class:`RuleViolation` with readable messages."""
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise RuleViolation(_readable_problems(exc)) from exc


def _readable_problems(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors():
        message = str(error["msg"]).removeprefix("Value error, ")
        field = ".".join(str(part) for part in error["loc"])
        problems.append(f"{field}: {message}" if field else message)
    return problems


class VersionedRecord(ValueModel):
    """A mutable-over-time record stored with optimistic concurrency.

    Records are never modified in place: an update produces a new instance with the
    next version, and storage rejects it if the stored version moved on meanwhile.
    """

    version: int = Field(default=1, ge=1)

    def next_version(self, **changes: Any) -> Self:
        """Returns a copy with ``changes`` applied, re-validated, and the version advanced."""
        if "version" in changes:
            raise ValueError("version is managed automatically")
        data = self.model_dump()
        data.update(changes)
        data["version"] = self.version + 1
        return type(self).build(**data)
