"""Accounts: first-run setup, onboarding, sign-in, passwords and profile files.

Coordinates the user records (``UserService``), the ``AuthProvider`` (passwords and
lockout) and the ``FileStore`` (pictures and licence copies). Every step is audited.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner, Outcome
from ims.application.users import UserService
from ims.domain.common.errors import NotFound, PermissionDenied, RuleViolation
from ims.domain.common.ids import UserId, new_command_id
from ims.domain.files import (
    DOCUMENT_KINDS,
    MAX_DOCUMENT_BYTES,
    MAX_PICTURE_BYTES,
    PICTURE_KINDS,
    check_upload,
)
from ims.domain.identity.lockout import describe_wait
from ims.domain.identity.password_policy import describe_problems, password_problems
from ims.domain.identity.roles import Permission, Role
from ims.domain.identity.user import PilotLicence, User
from ims.ports.auth import AuthProvider, VerifyOutcome
from ims.ports.clock import Clock
from ims.ports.files import FileStore
from ims.ports.repository import Storage


class SignInStatus(StrEnum):
    OK = "ok"
    MUST_CHANGE_PASSWORD = "must_change_password"  # noqa: S105 (a status name, not a password)
    INVALID = "invalid"
    LOCKED = "locked"
    DEACTIVATED = "deactivated"


@dataclass(frozen=True, slots=True)
class SignInResult:
    status: SignInStatus
    message: str = ""
    user: User | None = None

    @property
    def signed_in(self) -> bool:
        return self.status in {SignInStatus.OK, SignInStatus.MUST_CHANGE_PASSWORD}


_INVALID = "The username or password is not correct."


class AccountService:
    def __init__(
        self,
        storage: Storage,
        auth: AuthProvider,
        files: FileStore,
        users: UserService,
        runner: CommandRunner,
        clock: Clock,
    ) -> None:
        self._s = storage
        self._auth = auth
        self._files = files
        self._users = users
        self._run = runner
        self._clock = clock

    # ------------------------------------------------------------------ setup & onboarding

    def setup_first_admin(
        self, ctx: CommandContext, *, password: str, confirm: str, **fields: Any
    ) -> UserId:
        """First run: the first administrator chooses their own password."""
        self._check_new_password(password, confirm, fields.get("username"))
        user_id = self._users.create_first_admin(ctx, **fields)
        if not self._auth.has_password(user_id):
            self._auth.set_password(user_id, password)
        return user_id

    def onboard(self, ctx: CommandContext, *, temporary_password: str, **fields: Any) -> UserId:
        """Creates a person's account with a temporary password they must change."""
        ctx.require_actor().require(Permission.USER_MANAGE)
        self._check_new_password(temporary_password, temporary_password, fields.get("username"))
        user_id = self._users.create_user(ctx, **fields)
        if not self._auth.has_password(user_id):
            self._auth.set_password(user_id, temporary_password)
        return user_id

    def reset_password(
        self, ctx: CommandContext, user_id: UserId, temporary_password: str
    ) -> UserId:
        """Admin reset: new temporary password, changed at next sign-in, lockout cleared."""
        actor = ctx.require_actor()
        actor.require(Permission.USER_MANAGE)
        user = self._require(user_id)
        self._check_new_password(temporary_password, temporary_password, user.username)

        def execute() -> Outcome:
            current = self._require(user_id)
            if not current.must_change_password:
                self._users.update_user(
                    CommandContext(new_command_id(), actor), user_id, current.version,
                    must_change_password=True,
                )  # fmt: skip
            self._auth.set_password(user_id, temporary_password)
            return Outcome("account", str(user_id), None, {"password": "reset"})

        self._run.run(ctx, "account.reset_password", execute)
        return user_id

    def unlock(self, ctx: CommandContext, user_id: UserId) -> UserId:
        ctx.require_actor().require(Permission.USER_MANAGE)
        self._require(user_id)

        def execute() -> Outcome:
            self._auth.unlock(user_id)
            return Outcome("account", str(user_id), None, {"lockout": "cleared"})

        self._run.run(ctx, "account.unlock", execute)
        return user_id

    def is_locked(self, actor: Actor, user_id: UserId) -> bool:
        actor.require(Permission.USER_MANAGE)
        return self._auth.lockout(user_id).is_locked(self._clock.now())

    # ------------------------------------------------------------------ sign-in

    def sign_in(self, username: str, password: str) -> SignInResult:
        user = self._s.users.find_by_username(username) if username.strip() else None
        if user is None or user.is_deleted:
            self._auth.verify_unknown(password)
            self._audit_sign_in(None, username.strip().lower() or "(blank)", "invalid")
            return SignInResult(SignInStatus.INVALID, _INVALID)

        verification = self._auth.verify(user.id, password, self._clock.now())
        if verification.outcome is VerifyOutcome.LOCKED:
            self._audit_sign_in(user.id, str(user.id), "locked")
            wait = describe_wait(verification.seconds_locked)
            return SignInResult(
                SignInStatus.LOCKED,
                f"Too many failed attempts. Try again in {wait}, or ask an administrator.",
            )
        if verification.outcome is VerifyOutcome.INVALID:
            self._audit_sign_in(user.id, str(user.id), "invalid")
            return SignInResult(SignInStatus.INVALID, _INVALID)
        if not user.is_active:
            self._audit_sign_in(user.id, str(user.id), "deactivated")
            return SignInResult(
                SignInStatus.DEACTIVATED, "This account is deactivated. Ask an administrator."
            )
        self._audit_sign_in(user.id, str(user.id), "success")
        if user.must_change_password:
            return SignInResult(SignInStatus.MUST_CHANGE_PASSWORD, "", user)
        return SignInResult(SignInStatus.OK, "", user)

    def change_password(
        self, ctx: CommandContext, *, current: str, new: str, confirm: str
    ) -> UserId:
        """Changes the signed-in person's own password."""
        actor = ctx.require_actor()
        user = self._require(actor.user_id)
        verification = self._auth.verify(user.id, current, self._clock.now())
        if verification.outcome is VerifyOutcome.LOCKED:
            wait = describe_wait(verification.seconds_locked)
            raise PermissionDenied(f"Too many failed attempts. Try again in {wait}.")
        if verification.outcome is not VerifyOutcome.OK:
            raise RuleViolation("Your current password is not correct.")
        if new == current:
            raise RuleViolation("Choose a password different from your current one.")
        self._check_new_password(new, confirm, user.username)

        def execute() -> Outcome:
            self._auth.set_password(user.id, new)
            latest = self._require(user.id)
            if latest.must_change_password:
                self._update_self(actor, latest, must_change_password=False)
            return Outcome("account", str(user.id), None, {"password": "changed"})

        self._run.run(ctx, "account.change_password", execute)
        return user.id

    # ------------------------------------------------------------------ files

    def set_profile_picture(self, ctx: CommandContext, user_id: UserId, content: bytes) -> str:
        actor = ctx.require_actor()
        self._require_self_or_admin(actor, user_id)
        kind = check_upload(content, PICTURE_KINDS, MAX_PICTURE_BYTES)
        ref = self._files.put(content, kind)
        user = self._require(user_id)
        if user.profile_picture != ref:
            self._update(actor, ctx, user, profile_picture=ref)
        return ref

    def set_licence_document(self, ctx: CommandContext, user_id: UserId, content: bytes) -> str:
        actor = ctx.require_actor()
        self._require_self_or_admin(actor, user_id)
        user = self._require(user_id)
        if user.licence is None:
            raise RuleViolation("Add the licence number and expiry date first.")
        kind = check_upload(content, DOCUMENT_KINDS, MAX_DOCUMENT_BYTES)
        ref = self._files.put(content, kind)
        if user.licence.document != ref:
            licence = PilotLicence(
                number=user.licence.number, expires_on=user.licence.expires_on, document=ref
            )
            self._update(actor, ctx, user, licence=licence)
        return ref

    def file(self, ref: str) -> bytes | None:
        return self._files.get(ref)

    # ------------------------------------------------------------------ helpers

    def _require(self, user_id: UserId) -> User:
        user = self._s.users.get(user_id)
        if user is None or user.is_deleted:
            raise NotFound("User not found.")
        return user

    @staticmethod
    def _require_self_or_admin(actor: Actor, user_id: UserId) -> None:
        if actor.user_id != user_id:
            actor.require(Permission.USER_MANAGE)

    @staticmethod
    def _check_new_password(password: str, confirm: str, username: str | None) -> None:
        if password != confirm:
            raise RuleViolation("The passwords do not match.")
        problems = password_problems(password, username)
        if problems:
            raise RuleViolation(describe_problems(problems))

    def _update(self, actor: Actor, ctx: CommandContext, user: User, **changes: Any) -> None:
        if actor.user_id == user.id and actor.role is not Role.ADMIN and "licence" in changes:
            # People may attach their own licence copy; the number and expiry stay admin-only.
            self._update_self(actor, user, **changes)
            return
        self._users.update_user(ctx, user.id, user.version, **changes)

    def _update_self(self, actor: Actor, user: User, **changes: Any) -> None:
        """Writes fields a person may change about themselves outside the admin rules."""
        after = user.next_version(**changes)
        self._s.users.update(after)
        self._run.run(
            CommandContext(new_command_id(), actor),
            "user.update_self",
            lambda: Outcome(
                "user", str(user.id), user.model_dump(mode="json"), after.model_dump(mode="json")
            ),
        )

    def _audit_sign_in(self, user_id: UserId | None, entity_id: str, result: str) -> None:
        actor = None
        if user_id is not None:
            user = self._s.users.get(user_id)
            if user is not None and user.is_active and not user.is_deleted:
                actor = Actor.from_user(user)
        self._run.run(
            CommandContext(new_command_id(), actor),
            f"account.sign_in.{result}",
            lambda: Outcome("account", entity_id, None, {"result": result}),
        )
