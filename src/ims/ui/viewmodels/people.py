"""People administration: list, onboard, edit, reset passwords, unlock, deactivate."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ims.application.accounts import AccountService
from ims.application.passwords import generate_temporary_password
from ims.application.users import UserService
from ims.domain.common.ids import UserId
from ims.domain.identity.roles import Role
from ims.domain.identity.user import User
from ims.ports.clock import Clock
from ims.ui.images import prepare_picture
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels.forms import ROLE_LABELS, describe_error, initials, local_path, user_fields
from ims.ui.viewmodels.session import SessionViewModel

_ROLES = (
    "personId", "version", "name", "initials", "username", "role", "roleLabel", "employeeId",
    "email", "phone", "picture", "licenceNumber", "licenceExpiry", "licenceExpiryIso",
    "licenceStatus", "licenceDocument", "account", "accountLabel", "isSelf",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class PersonRow:
    user: User
    locked: bool


def _row_values(row: PersonRow, today: Any, self_id: UserId | None) -> dict[str, Any]:
    u = row.user
    if not u.is_active:
        account, label = "neutral", "Deactivated"
    elif row.locked:
        account, label = "danger", "Locked"
    elif u.must_change_password:
        account, label = "info", "Awaiting first sign-in"
    else:
        account, label = "success", "Active"
    licence = u.licence
    return {
        "personId": str(u.id),
        "version": u.version,
        "name": u.full_name,
        "initials": initials(u.full_name),
        "username": u.username,
        "role": u.role.value,
        "roleLabel": ROLE_LABELS[u.role],
        "employeeId": u.employee_id,
        "email": u.email,
        "phone": u.phone,
        "picture": f"image://files/{u.profile_picture}" if u.profile_picture else "",
        "licenceNumber": licence.number if licence else "",
        "licenceExpiry": licence.expires_on.strftime("%d %b %Y") if licence else "",
        "licenceExpiryIso": licence.expires_on.isoformat() if licence else "",
        "licenceStatus": licence.status_on(today) if licence else "",
        "licenceDocument": licence.document or "" if licence else "",
        "account": account,
        "accountLabel": label,
        "isSelf": self_id == u.id,
    }


class PeopleViewModel(QObject):
    changed = Signal()
    saved = Signal(str)  # message for a toast
    temporaryPassword = Signal(str, str, str)  # noqa: N815 (name, username, password)

    def __init__(
        self,
        session: SessionViewModel,
        users: UserService,
        accounts: AccountService,
        clock: Clock,
        tasks: TaskQueue,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._users = users
        self._accounts = accounts
        self._clock = clock
        self._tasks = tasks
        self._model = DictListModel(_ROLES, self)
        self._all: list[dict[str, Any]] = []
        self._filter = ""
        self._role_filter = ""
        self._error = ""
        session.signedIn.connect(self.refresh)

    # ------------------------------------------------------------------ properties

    def _model_get(self) -> DictListModel:
        return self._model

    def _error_get(self) -> str:
        return self._error

    def _count_get(self) -> int:
        return self._model.rowCount()

    def _total_get(self) -> int:
        return len(self._all)

    def _filter_get(self) -> str:
        return self._filter

    def _role_filter_get(self) -> str:
        return self._role_filter

    model = Property(QObject, _model_get, constant=True)
    error = Property(str, _error_get, notify=changed)
    count = Property(int, _count_get, notify=changed)
    total = Property(int, _total_get, notify=changed)
    filterText = Property(str, _filter_get, notify=changed)  # noqa: N815
    roleFilter = Property(str, _role_filter_get, notify=changed)  # noqa: N815

    # ------------------------------------------------------------------ plumbing

    def _run(
        self,
        work: Callable[[], Any],
        message: str | Callable[[Any], str] = "",
        refresh: bool = True,
    ) -> None:
        self._error = ""
        self.changed.emit()

        def done(value: Any) -> None:
            text = message(value) if callable(message) else message
            if text:
                self.saved.emit(text)
            if refresh:
                self.refresh()

        def failed(exc: BaseException) -> None:
            self._error = describe_error(exc)
            self.changed.emit()

        self._tasks.submit(work, done, failed)

    def _apply_filter(self) -> None:
        needle = self._filter.strip().lower()
        rows = [
            r
            for r in self._all
            if (not self._role_filter or r["role"] == self._role_filter)
            and (
                not needle
                or any(
                    needle in str(r[k]).lower() for k in ("name", "username", "employeeId", "email")
                )
            )
        ]
        self._model.reset(rows)
        self.changed.emit()

    # ------------------------------------------------------------------ slots

    @Slot()
    def refresh(self) -> None:
        if not self._session.can("user.manage"):
            return
        actor = self._session.actor()

        def work() -> list[dict[str, Any]]:
            today = self._clock.today()
            return [
                _row_values(
                    PersonRow(u, self._accounts.is_locked(actor, u.id)), today, actor.user_id
                )
                for u in self._users.list_users(actor)
            ]

        def done(rows: list[dict[str, Any]]) -> None:
            self._all = rows
            self._apply_filter()

        self._tasks.submit(work, done, lambda exc: self._set_error(exc))

    def _set_error(self, exc: BaseException) -> None:
        self._error = describe_error(exc)
        self.changed.emit()

    @Slot(str)
    def setFilterText(self, value: str) -> None:  # noqa: N802
        self._filter = value
        self._apply_filter()

    @Slot(str)
    def setRoleFilter(self, value: str) -> None:  # noqa: N802
        self._role_filter = value
        self._apply_filter()

    @Slot(str, result=dict)
    def person(self, person_id: str) -> dict[str, Any]:
        return self._model.find("personId", person_id) or next(
            (dict(r) for r in self._all if r["personId"] == person_id), {}
        )

    @Slot()
    def clearError(self) -> None:  # noqa: N802
        self._error = ""
        self.changed.emit()

    @Slot(dict)
    def onboard(self, values: dict[str, Any]) -> None:
        fields = values.copy()

        def work() -> tuple[str, str, str]:
            parsed = user_fields(fields)
            temporary = generate_temporary_password(parsed["username"])
            self._accounts.onboard(self._session.context(), temporary_password=temporary, **parsed)
            return parsed["full_name"], parsed["username"], temporary

        def message(result: tuple[str, str, str]) -> str:
            self.temporaryPassword.emit(*result)
            return f"{result[0]} can now sign in"

        self._run(work, message)

    @Slot(str, int, dict)
    def update(self, person_id: str, version: int, values: dict[str, Any]) -> None:
        fields = values.copy()

        def work() -> str:
            user_id = UserId(uuid.UUID(person_id))
            current = self._users.get(self._session.actor(), user_id)
            parsed = user_fields(fields, current.licence)
            self._users.update_user(self._session.context(), user_id, version, **parsed)
            return str(parsed["full_name"])

        self._run(work, lambda name: f"Saved {name}")

    @Slot(str)
    def resetPassword(self, person_id: str) -> None:  # noqa: N802
        def work() -> tuple[str, str, str]:
            user_id = UserId(uuid.UUID(person_id))
            user = self._users.get(self._session.actor(), user_id)
            temporary = generate_temporary_password(user.username)
            self._accounts.reset_password(self._session.context(), user_id, temporary)
            return user.full_name, user.username, temporary

        def message(result: tuple[str, str, str]) -> str:
            self.temporaryPassword.emit(*result)
            return f"Password reset for {result[0]}"

        self._run(work, message)

    @Slot(str)
    def unlock(self, person_id: str) -> None:
        self._run(
            lambda: self._accounts.unlock(self._session.context(), UserId(uuid.UUID(person_id))),
            "Account unlocked",
        )

    @Slot(str, int, bool)
    def setActive(self, person_id: str, version: int, active: bool) -> None:  # noqa: N802
        self._run(
            lambda: self._users.update_user(
                self._session.context(), UserId(uuid.UUID(person_id)), version, is_active=active
            ),
            "Account reactivated" if active else "Account deactivated",
        )

    @Slot(str, int)
    def remove(self, person_id: str, version: int) -> None:
        self._run(
            lambda: self._users.delete_user(
                self._session.context(), UserId(uuid.UUID(person_id)), version
            ),
            "Person removed",
        )

    @Slot(str, str)
    def uploadPicture(self, person_id: str, url: str) -> None:  # noqa: N802
        def work() -> None:
            content = prepare_picture(local_path(url))
            self._accounts.set_profile_picture(
                self._session.context(), UserId(uuid.UUID(person_id)), content
            )

        self._run(work, "Picture updated")

    @Slot(str, str)
    def uploadLicence(self, person_id: str, url: str) -> None:  # noqa: N802
        def work() -> None:
            with open(local_path(url), "rb") as handle:
                content = handle.read()
            self._accounts.set_licence_document(
                self._session.context(), UserId(uuid.UUID(person_id)), content
            )

        self._run(work, "Licence copy attached")

    @Slot(result=list)
    def roles(self) -> list[dict[str, str]]:
        return [{"value": r.value, "label": ROLE_LABELS[r]} for r in Role]
