from datetime import date

import pytest

from ims.domain.common.errors import LastAdminError, RuleViolation
from ims.domain.identity.password_policy import (
    MAX_LENGTH,
    check_password,
    describe_problems,
    password_problems,
)
from ims.domain.identity.roles import ROLE_PERMISSIONS, Permission, Role
from ims.domain.identity.user import PilotLicence, ensure_admin_remains
from tests.fakes import make_user


class TestUserFields:
    def test_values_are_normalised(self) -> None:
        user = make_user(
            Role.SURVEYOR,
            username="  S.Kumar ",
            employee_id=" emp-77 ",
            email=" S.Kumar@Example.COM ",
            phone="+91 (987) 654-3210",
        )
        assert user.username == "s.kumar"
        assert user.employee_id == "EMP-77"
        assert user.email == "s.kumar@example.com"
        assert user.phone == "+919876543210"

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("username", "ab", "username must be 3-32"),
            ("username", "-starts-with-dash", "username must be 3-32"),
            ("employee_id", "E1", "employee ID must be 3-20"),
            ("employee_id", "EMP 01", "employee ID must be 3-20"),
            ("email", "no-at-sign.com", "email address is not valid"),
            ("email", "a@b", "email address is not valid"),
            ("phone", "12345", "7-15 digits"),
            ("full_name", "", "at least 1 character"),
        ],
    )
    def test_invalid_values_are_rejected(self, field: str, value: str, message: str) -> None:
        with pytest.raises(RuleViolation, match=message):
            make_user(Role.SURVEYOR, **{field: value})

    def test_pilots_must_have_a_licence(self) -> None:
        with pytest.raises(RuleViolation, match="DGCA Remote Pilot Certificate"):
            make_user(Role.PILOT, licence=None)

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.SURVEYOR])
    def test_licence_is_optional_for_others(self, role: Role) -> None:
        assert make_user(role, licence=None).licence is None
        licensed = make_user(
            role, licence=PilotLicence(number="rpc-1", expires_on=date(2027, 1, 1))
        )
        assert licensed.licence is not None and licensed.licence.number == "RPC-1"

    def test_licence_number_format(self) -> None:
        with pytest.raises(RuleViolation, match="licence number"):
            PilotLicence.build(number="x", expires_on=date(2027, 1, 1))

    def test_licence_validity_and_days_remaining(self) -> None:
        licence = PilotLicence(number="RPC-9", expires_on=date(2026, 12, 31))
        assert licence.is_valid_on(date(2026, 12, 31))
        assert not licence.is_valid_on(date(2027, 1, 1))
        assert licence.days_remaining(date(2026, 12, 1)) == 30
        pilot = make_user(Role.PILOT, licence=licence)
        assert pilot.licence_valid_on(date(2026, 6, 1))
        assert not make_user(Role.SURVEYOR).licence_valid_on(date(2026, 6, 1))

    def test_profile_picture_completes_the_profile(self) -> None:
        user = make_user(Role.SURVEYOR)
        assert user.needs_profile_completion
        assert not user.next_version(profile_picture="files/abc.png").needs_profile_completion


class TestPermissions:
    def test_admin_has_every_permission(self) -> None:
        assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)

    def test_pilots_and_surveyors_are_crew(self) -> None:
        crew = ROLE_PERMISSIONS[Role.PILOT]
        assert crew == ROLE_PERMISSIONS[Role.SURVEYOR]
        assert Permission.DEPLOYMENT_CREATE in crew
        assert Permission.DEFECT_REPORT in crew
        for admin_only in (
            Permission.USER_MANAGE,
            Permission.ASSET_MANAGE,
            Permission.MAINTENANCE_CERTIFY,
            Permission.STOCK_MANAGE,
            Permission.USAGE_CORRECT,
        ):
            assert admin_only not in crew

    def test_inactive_or_deleted_users_have_no_permissions(self) -> None:
        admin = make_user(Role.ADMIN)
        assert admin.permissions
        assert admin.next_version(is_active=False).permissions == frozenset()


class TestLastAdmin:
    def test_cannot_demote_the_only_admin(self) -> None:
        admin = make_user(Role.ADMIN)
        with pytest.raises(LastAdminError):
            ensure_admin_remains(admin, admin.next_version(role=Role.SURVEYOR), 0)

    def test_cannot_deactivate_or_delete_the_only_admin(self) -> None:
        admin = make_user(Role.ADMIN)
        with pytest.raises(LastAdminError):
            ensure_admin_remains(admin, admin.next_version(is_active=False), 0)
        with pytest.raises(LastAdminError):
            ensure_admin_remains(admin, None, 0)

    def test_allowed_when_another_admin_remains(self) -> None:
        admin = make_user(Role.ADMIN)
        ensure_admin_remains(admin, None, 1)

    def test_non_admins_are_not_affected(self) -> None:
        pilot = make_user(Role.PILOT)
        ensure_admin_remains(pilot, None, 0)


class TestPasswordPolicy:
    def test_strong_password_passes(self) -> None:
        assert check_password("Field-Survey-2026!", username="skumar").ok
        assert password_problems("Field-Survey-2026!") == []
        assert describe_problems([]) == ""

    def test_lists_every_missing_requirement(self) -> None:
        problems = password_problems("short")
        assert problems == [
            "be at least 12 characters long",
            "include an uppercase letter, a digit and a special character",
        ]
        assert describe_problems(problems).startswith("Password must be at least 12")

    def test_too_long(self) -> None:
        assert "be at most 128 characters long" in password_problems("Aa1!" * (MAX_LENGTH // 4 + 1))

    def test_single_repeated_character(self) -> None:
        assert "not be a single repeated character" in password_problems("aaaaaaaaaaaaaa")

    def test_must_not_contain_username(self) -> None:
        assert "not contain the username" in password_problems("Skumar-2026-Pass!", "SKumar")
        assert check_password("Ab1!Ab1!Ab1!x", username="ab").ok  # names under 3 letters ignored
