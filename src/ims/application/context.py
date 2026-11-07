"""Who is acting, and the command they are running."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from ims.domain.common.errors import PermissionDenied
from ims.domain.common.ids import CommandId, UserId, derive_id
from ims.domain.identity.roles import Permission, Role
from ims.domain.identity.user import User


@dataclass(frozen=True, slots=True)
class Actor:
    """The signed-in user, as far as permission checks are concerned."""

    user_id: UserId
    role: Role
    permissions: frozenset[Permission]

    @classmethod
    def from_user(cls, user: User) -> Actor:
        if not user.is_active or user.is_deleted:
            raise PermissionDenied("This account is deactivated.")
        return cls(user_id=user.id, role=user.role, permissions=user.permissions)

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, *permissions: Permission) -> None:
        missing = [p.value for p in permissions if p not in self.permissions]
        if missing:
            raise PermissionDenied(
                f"Your role ({self.role.value}) is not allowed to do this "
                f"(needs {', '.join(sorted(missing))})."
            )


@dataclass(frozen=True, slots=True)
class CommandContext:
    """One user action. Retrying with the same ``command_id`` is always safe."""

    command_id: CommandId
    actor: Actor | None  # None only during first-run setup

    def derive(self, purpose: str) -> uuid.UUID:
        """Stable ID for a record this command creates (same on every retry)."""
        return derive_id(self.command_id, purpose)

    def require_actor(self) -> Actor:
        if self.actor is None:
            raise PermissionDenied("You must be signed in to do this.")
        return self.actor
