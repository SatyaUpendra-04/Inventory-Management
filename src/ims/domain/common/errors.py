"""Domain errors. Messages are written for end users; details go in attributes."""

from __future__ import annotations

from collections.abc import Sequence


class DomainError(Exception):
    """Base class for every rule violation the user can act on."""


class RuleViolation(DomainError):
    """One or more business rules were broken. ``problems`` lists each one."""

    def __init__(self, problems: str | Sequence[str]) -> None:
        self.problems: tuple[str, ...] = (
            (problems,) if isinstance(problems, str) else tuple(problems)
        )
        if not self.problems:
            raise ValueError("RuleViolation needs at least one problem")
        super().__init__(" ".join(self.problems))


class InvalidTransition(DomainError):
    """A status change that the state machine does not allow."""


class PermissionDenied(DomainError):
    """The acting user lacks a required permission or is inactive."""


class NotFound(DomainError):
    """A referenced record does not exist."""


class ConflictError(DomainError):
    """The record changed since it was read, or a unique value is already taken."""


class AlreadyExists(ConflictError):
    """A record with the same ID already exists (used to detect replayed commands)."""


class LastAdminError(RuleViolation):
    """The change would leave the system without an active administrator."""

    def __init__(self) -> None:
        super().__init__("At least one active administrator must remain.")
