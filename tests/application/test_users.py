from datetime import date

import pytest

from ims.adapters.memory import memory_storage
from ims.application.context import Actor, CommandContext
from ims.application.runner import CommandRunner
from ims.application.users import UserService
from ims.domain.common.errors import (
    ConflictError,
    LastAdminError,
    NotFound,
    PermissionDenied,
    RuleViolation,
)
from ims.domain.common.ids import UserId, new_command_id, uuid7
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence
from tests.application.conftest import App
from tests.fakes import FixedClock, make_user

FIELDS = {
    "username": "rkumar",
    "full_name": "R Kumar",
    "employee_id": "EMP-9001",
    "email": "rkumar@example.com",
    "phone": "9876543210",
}


class TestFirstRun:
    def test_first_admin_once_only(self) -> None:
        storage = memory_storage()
        clock = FixedClock()
        users = UserService(storage, CommandRunner(storage, clock), clock)
        assert users.needs_first_admin()
        ctx = CommandContext(new_command_id(), None)
        admin_id = users.create_first_admin(ctx, **FIELDS)
        admin = storage.users.get(admin_id)
        assert admin is not None and admin.role is Role.ADMIN and not admin.must_change_password
        assert not users.needs_first_admin()
        assert users.create_first_admin(ctx, **FIELDS) == admin_id  # retry is harmless
        with pytest.raises(PermissionDenied, match="already exists"):
            users.create_first_admin(
                CommandContext(new_command_id(), None), **{**FIELDS, "username": "other"}
            )
        audit = storage.audit.for_entity("user", str(admin_id))
        assert len(audit) == 1 and audit[0].actor_id is None


class TestCreateUser:
    def test_admin_creates_pilot_with_licence(self, app: App) -> None:
        licence = PilotLicence(number="RPC-1234", expires_on=date(2030, 1, 1))
        user_id = app.users.create_user(
            app.ctx(app.admin), role=Role.PILOT, licence=licence, **FIELDS
        )
        user = app.users.get(app.actor(app.admin), user_id)
        assert user.must_change_password and user.needs_profile_completion
        assert user.licence == licence

    def test_pilot_without_licence_is_rejected(self, app: App) -> None:
        with pytest.raises(RuleViolation, match="DGCA"):
            app.users.create_user(app.ctx(app.admin), role=Role.PILOT, **FIELDS)

    def test_crew_cannot_create_users(self, app: App) -> None:
        with pytest.raises(PermissionDenied, match=r"pilot.*user\.manage"):
            app.users.create_user(app.ctx(app.pilot), role=Role.SURVEYOR, **FIELDS)

    def test_duplicates_are_reported_together(self, app: App) -> None:
        clash = {
            **FIELDS,
            "username": app.pilot.username,
            "email": app.surveyor.email.upper(),
        }
        with pytest.raises(RuleViolation) as caught:
            app.users.create_user(app.ctx(app.admin), role=Role.SURVEYOR, **clash)
        assert caught.value.problems == ("Username is already in use.", "Email is already in use.")

    def test_retrying_the_same_command_creates_one_user(self, app: App) -> None:
        ctx = app.ctx(app.admin)
        first = app.users.create_user(ctx, role=Role.SURVEYOR, **FIELDS)
        second = app.users.create_user(ctx, role=Role.SURVEYOR, **FIELDS)
        assert first == second
        assert len(app.storage.audit.for_entity("user", str(first))) == 1

    def test_reusing_a_command_id_for_another_action_is_refused(self, app: App) -> None:
        ctx = app.ctx(app.admin)
        user_id = app.users.create_user(ctx, role=Role.SURVEYOR, **FIELDS)
        with pytest.raises(ConflictError, match="different action"):
            app.users.delete_user(ctx, user_id, 1)


class TestUpdateUser:
    def test_admin_edits_and_audit_keeps_before_and_after(self, app: App) -> None:
        user_id = app.users.update_user(
            app.ctx(app.admin), app.surveyor.id, 1, full_name="Surveyor Renamed"
        )
        updated = app.users.get(app.actor(app.admin), user_id)
        assert (updated.full_name, updated.version) == ("Surveyor Renamed", 2)
        entry = app.storage.audit.for_entity("user", str(user_id))[0]
        assert entry.before is not None and entry.after is not None
        assert entry.before["full_name"] == app.surveyor.full_name
        assert entry.after["full_name"] == "Surveyor Renamed"

    def test_people_edit_their_own_phone_and_picture_only(self, app: App) -> None:
        app.users.update_user(
            app.ctx(app.pilot), app.pilot.id, 1, phone="9123456780", profile_picture="f/p.png"
        )
        with pytest.raises(PermissionDenied):
            app.users.update_user(app.ctx(app.pilot), app.pilot.id, 2, role=Role.ADMIN)
        with pytest.raises(PermissionDenied):
            app.users.update_user(app.ctx(app.pilot), app.surveyor.id, 1, phone="9123456780")

    def test_unknown_fields_are_refused(self, app: App) -> None:
        with pytest.raises(RuleViolation, match="cannot be changed here: version"):
            app.users.update_user(app.ctx(app.admin), app.pilot.id, 1, version=7)

    def test_stale_version_is_a_conflict(self, app: App) -> None:
        app.users.update_user(app.ctx(app.admin), app.pilot.id, 1, full_name="First")
        with pytest.raises(ConflictError, match="changed by someone else"):
            app.users.update_user(app.ctx(app.admin), app.pilot.id, 1, full_name="Second")

    def test_retry_after_success_is_harmless(self, app: App) -> None:
        ctx = app.ctx(app.admin)
        app.users.update_user(ctx, app.pilot.id, 1, full_name="Once")
        app.users.update_user(ctx, app.pilot.id, 1, full_name="Once")
        assert app.storage.users.get(app.pilot.id).version == 2  # type: ignore[union-attr]

    def test_last_admin_cannot_be_demoted_or_deactivated(self, app: App) -> None:
        with pytest.raises(LastAdminError):
            app.users.update_user(app.ctx(app.admin), app.admin.id, 1, role=Role.SURVEYOR)
        with pytest.raises(LastAdminError):
            app.users.update_user(app.ctx(app.admin), app.admin.id, 1, is_active=False)

    def test_several_admins_allowed(self, app: App) -> None:
        app.users.update_user(app.ctx(app.admin), app.surveyor.id, 1, role=Role.ADMIN)
        app.users.update_user(app.ctx(app.admin), app.admin.id, 1, is_active=False)
        assert app.storage.users.count_active_admins() == 1

    def test_unique_values_checked_on_update(self, app: App) -> None:
        with pytest.raises(RuleViolation, match="Email is already in use"):
            app.users.update_user(app.ctx(app.admin), app.pilot.id, 1, email=app.admin.email)

    def test_missing_user(self, app: App) -> None:
        with pytest.raises(NotFound):
            app.users.update_user(app.ctx(app.admin), UserId(uuid7()), 1, full_name="Ghost")


class TestDeleteAndQueries:
    def test_soft_delete(self, app: App) -> None:
        app.users.delete_user(app.ctx(app.admin), app.surveyor.id, 1)
        stored = app.storage.users.get(app.surveyor.id)
        assert stored is not None and stored.is_deleted and not stored.is_active
        assert app.surveyor.id not in [u.id for u in app.users.list_users(app.actor(app.admin))]
        with pytest.raises(PermissionDenied, match="deactivated"):
            Actor.from_user(stored)

    def test_deleting_twice_or_yourself(self, app: App) -> None:
        app.users.delete_user(app.ctx(app.admin), app.surveyor.id, 1)
        app.users.delete_user(app.ctx(app.admin), app.surveyor.id, 1)  # already gone: no error
        with pytest.raises(RuleViolation, match="your own account"):
            app.users.delete_user(app.ctx(app.admin), app.admin.id, 1)

    def test_cannot_delete_last_admin(self, app: App) -> None:
        second = make_user(Role.ADMIN)
        app.storage.users.add(second)
        app.users.update_user(app.ctx(second), app.admin.id, 1, is_active=False)
        with pytest.raises(LastAdminError):
            app.users.delete_user(app.ctx(app.admin.next_version()), second.id, 1)

    def test_stale_delete_is_a_conflict(self, app: App) -> None:
        app.users.update_user(app.ctx(app.admin), app.pilot.id, 1, full_name="Changed")
        with pytest.raises(ConflictError):
            app.users.delete_user(app.ctx(app.admin), app.pilot.id, 1)

    def test_people_see_themselves_but_not_others(self, app: App) -> None:
        assert app.users.get(app.actor(app.pilot), app.pilot.id) == app.pilot
        with pytest.raises(PermissionDenied):
            app.users.get(app.actor(app.pilot), app.surveyor.id)
        with pytest.raises(NotFound):
            app.users.get(app.actor(app.admin), UserId(uuid7()))

    def test_expiring_licences(self, app: App) -> None:
        soon = make_user(
            Role.PILOT, licence=PilotLicence(number="RPC-SOON", expires_on=date(2026, 12, 1))
        )
        app.storage.users.add(soon)
        expiring = app.users.pilots_with_licence_expiring(app.actor(app.admin), within_days=30)
        assert [u.id for u in expiring] == [soon.id]

    def test_signed_out_callers_are_refused(self, app: App) -> None:
        with pytest.raises(PermissionDenied, match="signed in"):
            app.users.create_user(app.ctx(None), role=Role.SURVEYOR, **FIELDS)
