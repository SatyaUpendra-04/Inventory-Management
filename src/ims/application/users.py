"""User administration use cases (rules catalogue U1-U13)."""

from __future__ import annotations

import uuid
from typing import Any

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome, add_once, update_once
from ims.domain.common.errors import ConflictError, NotFound, PermissionDenied, RuleViolation
from ims.domain.common.ids import UserId
from ims.domain.identity.roles import Permission, Role
from ims.domain.identity.user import PilotLicence, User, ensure_admin_remains
from ims.ports.clock import Clock
from ims.ports.repository import Storage

SELF_SERVICE_FIELDS = frozenset({"phone", "profile_picture"})
"""Fields people may change on their own profile without the user.manage permission."""

EDITABLE_FIELDS = frozenset(
    {
        "username",
        "full_name",
        "role",
        "employee_id",
        "email",
        "phone",
        "licence",
        "profile_picture",
        "is_active",
        "must_change_password",
    }
)


def _snapshot(user: User) -> dict[str, Any]:
    return user.model_dump(mode="json")


def _same_content(a: User, b: User) -> bool:
    return a.model_dump(exclude={"version"}) == b.model_dump(exclude={"version"})


class UserService:
    def __init__(self, storage: Storage, runner: CommandRunner, clock: Clock) -> None:
        self._s = storage
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ queries

    def get(self, actor: Actor, user_id: UserId) -> User:
        if actor.user_id != user_id:
            actor.require(Permission.USER_MANAGE)
        user = self._s.users.get(user_id)
        if user is None:
            raise NotFound("User not found.")
        return user

    def list_users(self, actor: Actor, *, include_deleted: bool = False) -> list[User]:
        actor.require(Permission.USER_MANAGE)
        return self._s.users.list(include_deleted=include_deleted)

    def needs_first_admin(self) -> bool:
        return self._s.users.count_active_admins() == 0

    def pilots_with_licence_expiring(self, actor: Actor, within_days: int) -> list[User]:
        actor.require(Permission.USER_MANAGE)
        today = self._clock.today()
        return [
            u
            for u in self._s.users.list()
            if u.role is Role.PILOT
            and u.is_active
            and u.licence is not None
            and u.licence.days_remaining(today) <= within_days
        ]

    # ------------------------------------------------------------------ commands

    def create_first_admin(
        self,
        ctx: CommandContext,
        *,
        username: str,
        full_name: str,
        employee_id: str,
        email: str,
        phone: str,
        licence: PilotLicence | None = None,
    ) -> UserId:
        """First-run setup: creates the first administrator. Only allowed once."""

        def execute() -> Outcome:
            user = User.build(
                id=ctx.derive("user"), username=username, full_name=full_name,
                role=Role.ADMIN, employee_id=employee_id, email=email, phone=phone,
                licence=licence, must_change_password=False,
            )  # fmt: skip
            if self._s.users.get(user.id) is None:
                if not self.needs_first_admin():
                    raise PermissionDenied("An administrator already exists.")
                self._check_unique(user)
            add_once(self._s.users.add, user)
            return Outcome("user", str(user.id), None, _snapshot(user))

        return UserId(uuid.UUID(self._run.run(ctx, "user.create_first_admin", execute)))

    def create_user(
        self,
        ctx: CommandContext,
        *,
        username: str,
        full_name: str,
        role: Role,
        employee_id: str,
        email: str,
        phone: str,
        licence: PilotLicence | None = None,
    ) -> UserId:
        ctx.require_actor().require(Permission.USER_MANAGE)

        def execute() -> Outcome:
            user = User.build(
                id=ctx.derive("user"), username=username, full_name=full_name, role=role,
                employee_id=employee_id, email=email, phone=phone, licence=licence,
                must_change_password=True,
            )  # fmt: skip
            if self._s.users.get(user.id) is None:
                self._check_unique(user)
            add_once(self._s.users.add, user)
            return Outcome("user", str(user.id), None, _snapshot(user))

        return UserId(uuid.UUID(self._run.run(ctx, "user.create", execute)))

    def update_user(
        self, ctx: CommandContext, user_id: UserId, expected_version: int, **changes: Any
    ) -> UserId:
        """Changes the given fields. ``expected_version`` is the version the user was shown."""
        actor = ctx.require_actor()
        unknown = set(changes) - EDITABLE_FIELDS
        if unknown:
            raise RuleViolation(
                f"These fields cannot be changed here: {', '.join(sorted(unknown))}."
            )
        own_profile_only = actor.user_id == user_id and set(changes) <= SELF_SERVICE_FIELDS
        if not own_profile_only:
            actor.require(Permission.USER_MANAGE)

        def execute() -> Outcome:
            stored = self._require(user_id)
            if stored.version == expected_version + 1 and _same_content(
                stored, stored.next_version(**changes)
            ):
                return Outcome("user", str(user_id), None, _snapshot(stored))  # retry, already done
            if stored.version != expected_version:
                raise ConflictError("This user was changed by someone else. Reload and try again.")
            after = stored.next_version(**changes)
            ensure_admin_remains(stored, after, self._other_active_admins(stored))
            self._check_unique(after)
            update_once(self._s.users.update, lambda: self._s.users.get(user_id), after)
            return Outcome("user", str(user_id), _snapshot(stored), _snapshot(after))

        return UserId(uuid.UUID(self._run.run(ctx, "user.update", execute)))

    def delete_user(self, ctx: CommandContext, user_id: UserId, expected_version: int) -> UserId:
        """Soft delete: the user disappears from lists, but history keeps their name."""
        actor = ctx.require_actor()
        actor.require(Permission.USER_MANAGE)
        if actor.user_id == user_id:
            raise RuleViolation("You cannot delete your own account.")

        def execute() -> Outcome:
            stored = self._require(user_id)
            if stored.is_deleted:
                return Outcome("user", str(user_id), None, _snapshot(stored))  # retry, already done
            if stored.version != expected_version:
                raise ConflictError("This user was changed by someone else. Reload and try again.")
            ensure_admin_remains(stored, None, self._other_active_admins(stored))
            after = stored.next_version(is_active=False, deleted_at=self._clock.now())
            update_once(self._s.users.update, lambda: self._s.users.get(user_id), after)
            return Outcome("user", str(user_id), _snapshot(stored), _snapshot(after))

        return UserId(uuid.UUID(self._run.run(ctx, "user.delete", execute)))

    # ------------------------------------------------------------------ helpers

    def _require(self, user_id: UserId) -> User:
        user = self._s.users.get(user_id)
        if user is None:
            raise NotFound("User not found.")
        return user

    def _other_active_admins(self, user: User) -> int:
        total = self._s.users.count_active_admins()
        return total - 1 if user.is_active_admin else total

    def _check_unique(self, user: User) -> None:
        problems: list[str] = []
        for label, found in (
            ("Username", self._s.users.find_by_username(user.username)),
            ("Employee ID", self._s.users.find_by_employee_id(user.employee_id)),
            ("Email", self._s.users.find_by_email(user.email)),
        ):
            if found is not None and found.id != user.id:
                note = (
                    " by a deleted user; restore that account instead" if found.is_deleted else ""
                )
                problems.append(f"{label} is already in use{note}.")
        if problems:
            raise RuleViolation(problems)
