"""The signed-in person and the gates before the app: setup, sign-in, password, profile."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.application.accounts import AccountService, SignInResult, SignInStatus
from ims.application.context import Actor, CommandContext
from ims.application.users import UserService
from ims.domain.common.errors import PermissionDenied
from ims.domain.common.ids import new_command_id
from ims.domain.identity.password_policy import check_password
from ims.domain.identity.roles import Permission, Role
from ims.domain.identity.user import User
from ims.ports.clock import Clock
from ims.ui.images import prepare_picture
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import ROLE_LABELS, describe_error, initials, local_path, user_fields


class Stage:
    SETUP = "setup"  # no administrator yet: create the first one
    SIGN_IN = "signIn"
    CHANGE_PASSWORD = "changePassword"  # noqa: S105 (a stage name, not a password)
    # temporary password must be replaced
    COMPLETE_PROFILE = "completeProfile"  # profile picture still missing
    APP = "app"


class SessionViewModel(QObject):
    changed = Signal()
    signedIn = Signal()  # noqa: N815
    signedOut = Signal()  # noqa: N815

    def __init__(
        self,
        accounts: AccountService,
        users: UserService,
        clock: Clock,
        tasks: TaskQueue,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._accounts = accounts
        self._users = users
        self._clock = clock
        self._tasks = tasks
        self._user: User | None = None
        self._error = ""
        self._stage = Stage.SETUP if users.needs_first_admin() else Stage.SIGN_IN
        tasks.busyChanged.connect(self.changed)

    # ------------------------------------------------------------------ Python API

    def actor(self) -> Actor:
        if self._user is None:
            raise PermissionDenied("You must be signed in to do this.")
        return Actor.from_user(self._user)

    def context(self) -> CommandContext:
        return CommandContext(new_command_id(), self.actor())

    @property
    def user(self) -> User | None:
        return self._user

    def permission_codes(self) -> list[str]:
        return self._permissions_get()

    def refresh_user(self) -> None:
        if self._user is not None:
            latest = self._users.get(self.actor(), self._user.id)
            self._user = latest
            self.changed.emit()

    # ------------------------------------------------------------------ properties

    def _get(self, attr: str, default: Any = "") -> Any:
        return getattr(self._user, attr, default) if self._user is not None else default

    def _stage_get(self) -> str:
        return self._stage

    def _error_get(self) -> str:
        return self._error

    def _busy_get(self) -> bool:
        return bool(self._tasks.busy)

    def _name_get(self) -> str:
        return str(self._get("full_name"))

    def _first_name_get(self) -> str:
        return self._name_get().split(" ")[0] if self._user else ""

    def _initials_get(self) -> str:
        return initials(self._name_get()) if self._user else ""

    def _username_get(self) -> str:
        return str(self._get("username"))

    def _role_get(self) -> str:
        return self._user.role.value if self._user else ""

    def _role_label_get(self) -> str:
        return ROLE_LABELS[self._user.role] if self._user else ""

    def _picture_get(self) -> str:
        ref = self._get("profile_picture", None)
        return f"image://files/{ref}" if ref else ""

    def _is_admin_get(self) -> bool:
        return self._user is not None and self._user.role is Role.ADMIN

    def _permissions_get(self) -> list[str]:
        return sorted(p.value for p in self._user.permissions) if self._user else []

    def _licence_get(self) -> dict[str, Any]:
        licence = self._get("licence", None)
        if licence is None:
            return {}
        today = self._clock.today()
        return {
            "number": licence.number,
            "expires": licence.expires_on.strftime("%d %b %Y"),
            "status": licence.status_on(today),
            "daysRemaining": licence.days_remaining(today),
            "document": licence.document or "",
        }

    def _contact_get(self) -> dict[str, str]:
        if self._user is None:
            return {}
        return {
            "email": self._user.email,
            "phone": self._user.phone,
            "employeeId": self._user.employee_id,
        }

    stage = Property(str, _stage_get, notify=changed)
    error = Property(str, _error_get, notify=changed)
    busy = Property(bool, _busy_get, notify=changed)
    displayName = Property(str, _name_get, notify=changed)  # noqa: N815
    firstName = Property(str, _first_name_get, notify=changed)  # noqa: N815
    initials = Property(str, _initials_get, notify=changed)
    username = Property(str, _username_get, notify=changed)
    role = Property(str, _role_get, notify=changed)
    roleLabel = Property(str, _role_label_get, notify=changed)  # noqa: N815
    picture = Property(str, _picture_get, notify=changed)
    isAdmin = Property(bool, _is_admin_get, notify=changed)  # noqa: N815
    permissions = Property(list, _permissions_get, notify=changed)
    licence = Property(dict, _licence_get, notify=changed)
    contact = Property(dict, _contact_get, notify=changed)

    # ------------------------------------------------------------------ helpers

    def _set(self, *, stage: str | None = None, error: str | None = None) -> None:
        if stage is not None:
            self._stage = stage
        if error is not None:
            self._error = error
        self.changed.emit()

    def _run(self, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        self._set(error="")
        self._tasks.submit(work, done, lambda exc: self._set(error=describe_error(exc)))

    def _after_password_ok(self, user: User) -> None:
        self._user = user
        stage = Stage.COMPLETE_PROFILE if user.needs_profile_completion else Stage.APP
        self._set(stage=stage, error="")
        if stage == Stage.APP:
            self.signedIn.emit()

    # ------------------------------------------------------------------ slots

    @Slot(str, str, result=list)
    def passwordChecklist(self, password: str, username: str) -> list[dict[str, Any]]:  # noqa: N802
        """Live checklist under password fields."""
        check = check_password(password, username or self._username_get() or None)
        return [
            {"label": "12 to 128 characters", "met": check.length},
            {"label": "Upper and lower case letters", "met": check.uppercase and check.lowercase},
            {"label": "At least one number", "met": check.digit},
            {"label": "At least one symbol, such as ! or -", "met": check.special},
            {
                "label": "Does not contain your username",
                "met": check.no_username and bool(password),
            },
        ]

    @Slot(dict, str, str)
    def setupAdmin(self, values: dict[str, Any], password: str, confirm: str) -> None:  # noqa: N802
        def work() -> SignInResult:
            fields = user_fields({**values, "role": Role.ADMIN.value})
            fields.pop("role")
            self._accounts.setup_first_admin(
                CommandContext(new_command_id(), None), password=password, confirm=confirm, **fields
            )
            return self._accounts.sign_in(fields["username"], password)

        self._run(work, self._on_sign_in)

    @Slot(str, str)
    def signIn(self, username: str, password: str) -> None:  # noqa: N802
        if not username.strip() or not password:
            self._set(error="Enter your username and password.")
            return
        self._run(lambda: self._accounts.sign_in(username, password), self._on_sign_in)

    def _on_sign_in(self, result: SignInResult) -> None:
        if result.user is None or not result.signed_in:
            self._set(error=result.message)
            return
        if result.status is SignInStatus.MUST_CHANGE_PASSWORD:
            self._user = result.user
            self._set(stage=Stage.CHANGE_PASSWORD, error="")
            return
        self._after_password_ok(result.user)

    @Slot(str, str, str)
    def changePassword(self, current: str, new: str, confirm: str) -> None:  # noqa: N802
        def work() -> User:
            ctx = self.context()
            self._accounts.change_password(ctx, current=current, new=new, confirm=confirm)
            return self._users.get(ctx.require_actor(), ctx.require_actor().user_id)

        def done(user: User) -> None:
            if self._stage == Stage.CHANGE_PASSWORD:
                self._after_password_ok(user)
            else:
                self._user = user
                self._set(error="")
                self.passwordChanged.emit()

        self._run(work, done)

    passwordChanged = Signal()  # noqa: N815

    @Slot(str)
    def uploadPicture(self, url: str) -> None:  # noqa: N802
        def work() -> User:
            content = prepare_picture(local_path(url))
            ctx = self.context()
            self._accounts.set_profile_picture(ctx, ctx.require_actor().user_id, content)
            return self._users.get(ctx.require_actor(), ctx.require_actor().user_id)

        def done(user: User) -> None:
            self._user = user
            self._set(error="")

        self._run(work, done)

    @Slot(str)
    def uploadLicence(self, url: str) -> None:  # noqa: N802
        def work() -> User:
            with open(local_path(url), "rb") as handle:
                content = handle.read()
            ctx = self.context()
            self._accounts.set_licence_document(ctx, ctx.require_actor().user_id, content)
            return self._users.get(ctx.require_actor(), ctx.require_actor().user_id)

        def done(user: User) -> None:
            self._user = user
            self._set(error="")

        self._run(work, done)

    @Slot(str)
    def updatePhone(self, phone: str) -> None:  # noqa: N802
        def work() -> User:
            ctx = self.context()
            user = self._users.get(ctx.require_actor(), ctx.require_actor().user_id)
            self._users.update_user(ctx, user.id, user.version, phone=phone)
            return self._users.get(ctx.require_actor(), user.id)

        def done(user: User) -> None:
            self._user = user
            self._set(error="")

        self._run(work, done)

    @Slot()
    def finishProfile(self) -> None:  # noqa: N802
        if self._user is not None and not self._user.needs_profile_completion:
            self._set(stage=Stage.APP, error="")
            self.signedIn.emit()
        else:
            self._set(error="Add a profile picture to continue.")

    @Slot()
    def signOut(self) -> None:  # noqa: N802
        self._user = None
        self._set(stage=Stage.SIGN_IN, error="")
        self.signedOut.emit()

    @Slot(str, result=bool)
    def can(self, permission: str) -> bool:
        return self._user is not None and Permission(permission) in self._user.permissions
