"""Password rules for app-specific accounts (local development and backend Plan B).

Carried over from V1.2.3 (rules catalogue P1, P2). Hashing is not done here; it belongs
to the authentication adapter.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_LENGTH = 12
MAX_LENGTH = 128


@dataclass(frozen=True, slots=True)
class PasswordCheck:
    length: bool
    uppercase: bool
    lowercase: bool
    digit: bool
    special: bool
    not_repeated: bool
    no_username: bool

    @property
    def ok(self) -> bool:
        return all(
            (
                self.length,
                self.uppercase,
                self.lowercase,
                self.digit,
                self.special,
                self.not_repeated,
                self.no_username,
            )
        )


def check_password(password: str, username: str | None = None) -> PasswordCheck:
    """Evaluates each requirement separately (drives the live checklist on screen)."""
    no_username = True
    if username is not None:
        name = username.strip().lower()
        no_username = not (len(name) >= 3 and name in password.lower())
    return PasswordCheck(
        length=MIN_LENGTH <= len(password) <= MAX_LENGTH,
        uppercase=any(ch.isupper() for ch in password),
        lowercase=any(ch.islower() for ch in password),
        digit=any(ch.isdigit() for ch in password),
        special=any(not ch.isalnum() and not ch.isspace() for ch in password),
        not_repeated=len(set(password.lower())) > 1,
        no_username=no_username,
    )


def password_problems(password: str, username: str | None = None) -> list[str]:
    """Every unmet requirement as a readable sentence fragment; empty when acceptable."""
    check = check_password(password, username)
    problems: list[str] = []
    if not check.length:
        problems.append(
            f"be at least {MIN_LENGTH} characters long"
            if len(password) < MIN_LENGTH
            else f"be at most {MAX_LENGTH} characters long"
        )
    missing = [
        label
        for passed, label in (
            (check.uppercase, "an uppercase letter"),
            (check.lowercase, "a lowercase letter"),
            (check.digit, "a digit"),
            (check.special, "a special character"),
        )
        if not passed
    ]
    if missing:
        problems.append("include " + _join(missing))
    if password and not check.not_repeated:
        problems.append("not be a single repeated character")
    if not check.no_username:
        problems.append("not contain the username")
    return problems


def describe_problems(problems: list[str]) -> str:
    return f"Password must {_join(problems)}." if problems else ""


def _join(parts: list[str]) -> str:
    if len(parts) <= 2:
        return " and ".join(parts)
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"
