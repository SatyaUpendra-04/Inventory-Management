"""Turning QML form values into domain values, and errors into readable messages."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import QUrl

from ims.domain.common.errors import DomainError, RuleViolation
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence

ROLE_LABELS = {Role.ADMIN: "Administrator", Role.PILOT: "Pilot", Role.SURVEYOR: "Surveyor"}


def describe_error(error: BaseException) -> str:
    if isinstance(error, RuleViolation):
        return " ".join(_sentence(p) for p in error.problems)
    if isinstance(error, DomainError):
        return str(error)
    return "Something went wrong. The details are in the log file."


def _sentence(problem: str) -> str:
    text = problem.strip()
    if ": " in text and text.split(": ", 1)[0].replace("_", "").replace(".", "").isalnum():
        text = text.split(": ", 1)[1]  # drop pydantic field prefixes such as "email: "
    text = text[:1].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def text(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    return "" if value is None else str(value).strip()


def optional_date(values: dict[str, Any], key: str) -> date | None:
    raw = text(values, key)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise RuleViolation(f"{key.replace('_', ' ')}: enter a valid date") from exc


def optional_decimal(values: dict[str, Any], key: str, label: str) -> Decimal | None:
    raw = text(values, key).replace(",", "")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise RuleViolation(f"{label} must be a number") from exc


def licence_from(
    values: dict[str, Any], existing: PilotLicence | None = None
) -> PilotLicence | None:
    number = text(values, "licenceNumber")
    expires = optional_date(values, "licenceExpiry")
    if not number and expires is None:
        return None
    if not number or expires is None:
        raise RuleViolation("Enter both the licence number and its expiry date.")
    document = existing.document if existing and existing.number == number.upper() else None
    return PilotLicence.build(number=number, expires_on=expires, document=document)


def user_fields(values: dict[str, Any], existing: PilotLicence | None = None) -> dict[str, Any]:
    return {
        "username": text(values, "username"),
        "full_name": text(values, "fullName"),
        "role": Role(text(values, "role") or Role.SURVEYOR.value),
        "employee_id": text(values, "employeeId"),
        "email": text(values, "email"),
        "phone": text(values, "phone"),
        "licence": licence_from(values, existing),
    }


def local_path(url_or_path: str) -> str:
    """Accepts ``file:///C:/...`` URLs from QML file dialogs, or plain paths."""
    if url_or_path.startswith("file:"):
        return QUrl(url_or_path).toLocalFile()
    return url_or_path


def initials(full_name: str) -> str:
    parts = [p for p in full_name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def local_time(moment: datetime) -> str:
    """A recorded UTC instant as the user's local date and time, e.g. ``08 Nov 2026 10:35``."""
    return moment.astimezone().strftime("%d %b %Y %H:%M")
