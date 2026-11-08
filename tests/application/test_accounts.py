from datetime import date

import pytest

from ims.adapters.files import MemoryFileStore
from ims.adapters.local_auth import LocalAuthProvider, MemoryCredentialStore, fast_hasher
from ims.adapters.memory import memory_storage
from ims.application.accounts import AccountService, SignInStatus
from ims.application.context import CommandContext
from ims.application.passwords import generate_temporary_password
from ims.application.runner import CommandRunner
from ims.application.users import UserService
from ims.domain.common.errors import NotFound, PermissionDenied, RuleViolation
from ims.domain.common.ids import UserId, new_command_id, uuid7
from ims.domain.identity.password_policy import password_problems
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence
from tests.application.conftest import App
from tests.fakes import FixedClock

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
TEMP = "Kq7m-Xp4t-Rw9z"
FIELDS = {
    "username": "rkumar",
    "full_name": "R Kumar",
    "employee_id": "EMP-9001",
    "email": "rkumar@example.com",
    "phone": "9876543210",
}


def test_temporary_passwords_meet_policy_and_differ() -> None:
    passwords = {generate_temporary_password("rkumar") for _ in range(50)}
    assert len(passwords) == 50
    assert all(not password_problems(p, "rkumar") for p in passwords)
    assert all(len(p) == 14 and p.count("-") == 2 for p in passwords)


class TestFirstRun:
    def _service(self) -> tuple[AccountService, UserService]:
        storage, clock = memory_storage(), FixedClock()
        runner = CommandRunner(storage, clock)
        users = UserService(storage, runner, clock)
        auth = LocalAuthProvider(MemoryCredentialStore(), fast_hasher())
        return AccountService(storage, auth, MemoryFileStore(), users, runner, clock), users

    def test_first_admin_sets_own_password_and_can_sign_in(self) -> None:
        accounts, users = self._service()
        ctx = CommandContext(new_command_id(), None)
        user_id = accounts.setup_first_admin(
            ctx, password="Field-Survey-2026!", confirm="Field-Survey-2026!", **FIELDS
        )
        result = accounts.sign_in("RKUMAR", "Field-Survey-2026!")
        assert result.status is SignInStatus.OK and result.user is not None
        assert result.user.id == user_id and not users.needs_first_admin()

    def test_weak_or_mismatched_password_is_refused(self) -> None:
        accounts, users = self._service()
        ctx = CommandContext(new_command_id(), None)
        with pytest.raises(RuleViolation, match="do not match"):
            accounts.setup_first_admin(ctx, password="Field-Survey-2026!", confirm="x", **FIELDS)
        with pytest.raises(RuleViolation, match="at least 12 characters"):
            accounts.setup_first_admin(ctx, password="short", confirm="short", **FIELDS)
        assert users.needs_first_admin()


class TestOnboardingAndSignIn:
    def test_new_person_must_change_temporary_password(self, app: App) -> None:
        user_id = app.accounts.onboard(
            app.ctx(app.admin), temporary_password=TEMP, role=Role.SURVEYOR, **FIELDS
        )
        first = app.accounts.sign_in("rkumar", TEMP)
        assert first.status is SignInStatus.MUST_CHANGE_PASSWORD and first.signed_in
        assert first.user is not None
        me = app.ctx(first.user)
        app.accounts.change_password(
            me, current=TEMP, new="Mine-Survey-2026!", confirm="Mine-Survey-2026!"
        )
        assert app.accounts.sign_in("rkumar", TEMP).status is SignInStatus.INVALID
        second = app.accounts.sign_in("rkumar", "Mine-Survey-2026!")
        assert second.status is SignInStatus.OK
        user = app.storage.users.get(user_id)
        assert user is not None and not user.must_change_password

    def test_only_admins_onboard(self, app: App) -> None:
        with pytest.raises(PermissionDenied):
            app.accounts.onboard(
                app.ctx(app.pilot), temporary_password=TEMP, role=Role.SURVEYOR, **FIELDS
            )

    def test_unknown_and_wrong_passwords_give_the_same_message(self, app: App) -> None:
        app.auth.set_password(app.surveyor.id, "Right-Password-26!")
        unknown = app.accounts.sign_in("nobody", "whatever")
        wrong = app.accounts.sign_in(app.surveyor.username, "wrong")
        blank = app.accounts.sign_in("  ", "")
        assert unknown.message == wrong.message == blank.message
        assert unknown.status is wrong.status is SignInStatus.INVALID

    def test_lockout_escalates_and_admin_can_unlock(self, app: App) -> None:
        app.auth.set_password(app.surveyor.id, "Right-Password-26!")
        name = app.surveyor.username
        for _ in range(4):
            assert app.accounts.sign_in(name, "wrong").status is SignInStatus.INVALID
        locked = app.accounts.sign_in(name, "wrong")
        assert locked.status is SignInStatus.LOCKED and "1 minute" in locked.message
        assert app.accounts.sign_in(name, "Right-Password-26!").status is SignInStatus.LOCKED
        assert app.accounts.is_locked(app.actor(app.admin), app.surveyor.id)
        app.clock.advance(minutes=1, seconds=1)
        assert app.accounts.sign_in(name, "wrong").status is SignInStatus.LOCKED  # now 2 minutes
        assert "2 minutes" in app.accounts.sign_in(name, "Right-Password-26!").message
        app.accounts.unlock(app.ctx(app.admin), app.surveyor.id)
        assert app.accounts.sign_in(name, "Right-Password-26!").signed_in

    def test_deactivated_accounts_cannot_sign_in(self, app: App) -> None:
        app.auth.set_password(app.surveyor.id, "Right-Password-26!")
        app.users.update_user(app.ctx(app.admin), app.surveyor.id, 1, is_active=False)
        result = app.accounts.sign_in(app.surveyor.username, "Right-Password-26!")
        assert result.status is SignInStatus.DEACTIVATED and not result.signed_in
        # The deactivated message is only revealed to someone who knows the password.
        assert app.accounts.sign_in(app.surveyor.username, "wrong").status is SignInStatus.INVALID

    def test_sign_ins_are_audited(self, app: App) -> None:
        app.auth.set_password(app.surveyor.id, "Right-Password-26!")
        app.accounts.sign_in(app.surveyor.username, "wrong")
        app.clock.advance(seconds=5)
        app.accounts.sign_in(app.surveyor.username, "Right-Password-26!")
        actions = [e.action for e in app.storage.audit.for_entity("account", str(app.surveyor.id))]
        assert actions == ["account.sign_in.invalid", "account.sign_in.success"]


class TestPasswordChanges:
    def test_admin_reset_forces_change_and_clears_lockout(self, app: App) -> None:
        app.auth.set_password(app.surveyor.id, "Right-Password-26!")
        for _ in range(5):
            app.accounts.sign_in(app.surveyor.username, "wrong")
        new_temp = generate_temporary_password(app.surveyor.username)
        app.accounts.reset_password(app.ctx(app.admin), app.surveyor.id, new_temp)
        result = app.accounts.sign_in(app.surveyor.username, new_temp)
        assert result.status is SignInStatus.MUST_CHANGE_PASSWORD
        with pytest.raises(PermissionDenied):
            app.accounts.reset_password(app.ctx(app.pilot), app.surveyor.id, new_temp)

    def test_change_password_rules(self, app: App) -> None:
        app.auth.set_password(app.pilot.id, "Right-Password-26!")
        me = app.ctx(app.pilot)
        with pytest.raises(RuleViolation, match="current password is not correct"):
            app.accounts.change_password(
                me, current="nope", new="New-Password-2026!", confirm="New-Password-2026!"
            )
        with pytest.raises(RuleViolation, match="different from your current"):
            app.accounts.change_password(
                me,
                current="Right-Password-26!",
                new="Right-Password-26!",
                confirm="Right-Password-26!",
            )
        with pytest.raises(RuleViolation, match="not contain the username"):
            pw = f"{app.pilot.username.title()}-2026-Pass!"
            app.accounts.change_password(me, current="Right-Password-26!", new=pw, confirm=pw)

    def test_change_password_while_locked(self, app: App) -> None:
        app.auth.set_password(app.pilot.id, "Right-Password-26!")
        for _ in range(5):
            app.accounts.sign_in(app.pilot.username, "wrong")
        with pytest.raises(PermissionDenied, match="Try again"):
            app.accounts.change_password(
                app.ctx(app.pilot),
                current="Right-Password-26!",
                new="New-Password-2026!",
                confirm="New-Password-2026!",
            )


class TestFiles:
    def test_profile_picture(self, app: App) -> None:
        ref = app.accounts.set_profile_picture(app.ctx(app.surveyor), app.surveyor.id, PNG)
        user = app.storage.users.get(app.surveyor.id)
        assert (
            user is not None and user.profile_picture == ref and not user.needs_profile_completion
        )
        assert app.accounts.file(ref) == PNG
        assert app.accounts.set_profile_picture(app.ctx(app.surveyor), app.surveyor.id, PNG) == ref

    def test_pictures_must_be_images(self, app: App) -> None:
        with pytest.raises(RuleViolation, match="Only JPEG, PNG"):
            app.accounts.set_profile_picture(app.ctx(app.admin), app.pilot.id, PDF)
        with pytest.raises(PermissionDenied):
            app.accounts.set_profile_picture(app.ctx(app.pilot), app.surveyor.id, PNG)

    def test_pilot_attaches_own_licence_copy(self, app: App) -> None:
        ref = app.accounts.set_licence_document(app.ctx(app.pilot), app.pilot.id, PDF)
        user = app.storage.users.get(app.pilot.id)
        assert user is not None and user.licence is not None and user.licence.document == ref
        assert app.pilot.licence is not None
        assert user.licence.number == app.pilot.licence.number  # number unchanged
        audit = app.storage.audit.for_entity("user", str(app.pilot.id))
        assert audit[-1].action == "user.update_self"

    def test_licence_copy_needs_a_licence(self, app: App) -> None:
        with pytest.raises(RuleViolation, match="licence number"):
            app.accounts.set_licence_document(app.ctx(app.admin), app.surveyor.id, PDF)

    def test_admin_attaches_licence_for_someone(self, app: App) -> None:
        app.users.update_user(
            app.ctx(app.admin),
            app.surveyor.id,
            1,
            licence=PilotLicence(number="RPC-5551", expires_on=date(2031, 1, 1)),
        )
        ref = app.accounts.set_licence_document(app.ctx(app.admin), app.surveyor.id, PNG)
        assert ref.endswith(".png")

    def test_unknown_people(self, app: App) -> None:
        with pytest.raises(NotFound):
            app.accounts.unlock(app.ctx(app.admin), UserId(uuid7()))
