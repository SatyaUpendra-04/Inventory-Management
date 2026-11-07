"""Users and the rules on their fields (rules catalogue U2-U8, U13)."""

from __future__ import annotations

import re
from datetime import date

from pydantic import Field, field_validator, model_validator

from ims.domain.common.errors import LastAdminError
from ims.domain.common.ids import UserId
from ims.domain.common.model import UtcDateTime, ValueModel, VersionedRecord
from ims.domain.identity.roles import Permission, Role, permissions_for

_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
_EMPLOYEE_ID = re.compile(r"^[A-Z0-9_-]{3,20}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LICENCE = re.compile(r"^[A-Z0-9/_-]{4,40}$")

LICENCE_WARNING_DAYS = (60, 30, 7)


class PilotLicence(ValueModel):
    """DGCA Remote Pilot Certificate held by a person."""

    number: str
    expires_on: date

    @field_validator("number")
    @classmethod
    def _number(cls, value: str) -> str:
        normalised = value.strip().upper()
        if not _LICENCE.match(normalised):
            raise ValueError("licence number must be 4-40 letters, digits, '/', '-' or '_'")
        return normalised

    def is_valid_on(self, day: date) -> bool:
        return day <= self.expires_on

    def days_remaining(self, day: date) -> int:
        return (self.expires_on - day).days


class User(VersionedRecord):
    id: UserId
    username: str
    full_name: str = Field(min_length=1, max_length=100)
    role: Role
    employee_id: str
    email: str
    phone: str
    licence: PilotLicence | None = None
    profile_picture: str | None = None  # FileStore reference, never image bytes
    is_active: bool = True
    must_change_password: bool = True
    deleted_at: UtcDateTime | None = None

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        normalised = value.strip().lower()
        if not _USERNAME.match(normalised):
            raise ValueError(
                "username must be 3-32 characters: letters, digits, '.', '-' or '_',"
                " starting with a letter or digit"
            )
        return normalised

    @field_validator("employee_id")
    @classmethod
    def _employee_id(cls, value: str) -> str:
        normalised = value.strip().upper()
        if not _EMPLOYEE_ID.match(normalised):
            raise ValueError("employee ID must be 3-20 letters, digits, '-' or '_'")
        return normalised

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        normalised = value.strip().lower()
        if not _EMAIL.match(normalised):
            raise ValueError("email address is not valid")
        return normalised

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        raw = value.strip()
        digits = re.sub(r"\D", "", raw)
        if not 7 <= len(digits) <= 15:
            raise ValueError("phone number must have 7-15 digits")
        return ("+" if raw.startswith("+") else "") + digits

    @model_validator(mode="after")
    def _pilot_needs_licence(self) -> User:
        if self.role is Role.PILOT and self.licence is None:
            raise ValueError(
                "pilots must have a DGCA Remote Pilot Certificate number and expiry date"
            )
        return self

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_active_admin(self) -> bool:
        return self.role is Role.ADMIN and self.is_active and not self.is_deleted

    @property
    def needs_profile_completion(self) -> bool:
        """Every user must have a profile picture; they add it at first sign-in."""
        return self.profile_picture is None

    @property
    def permissions(self) -> frozenset[Permission]:
        if not self.is_active or self.is_deleted:
            return frozenset()
        return permissions_for(self.role)

    def licence_valid_on(self, day: date) -> bool:
        return self.licence is not None and self.licence.is_valid_on(day)


def ensure_admin_remains(before: User, after: User | None, other_active_admins: int) -> None:
    """Raises :class:`LastAdminError` if the change removes the last active admin.

    ``after`` is ``None`` when the user is being deleted.
    """
    if not before.is_active_admin:
        return
    still_admin = after is not None and after.is_active_admin
    if not still_admin and other_active_admins < 1:
        raise LastAdminError()
