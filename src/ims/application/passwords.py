"""Temporary passwords handed to people by an administrator."""

from __future__ import annotations

import secrets

from ims.domain.identity.password_policy import password_problems

# No easily confused characters (0/O, 1/l/I), so a password read aloud or copied by hand works.
_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_LOWER = "abcdefghijkmnpqrstuvwxyz"
_DIGITS = "23456789"


def generate_temporary_password(username: str | None = None) -> str:
    """Three readable groups such as ``Kq7m-Xp4t-Rw9z``; always meets the password policy."""
    rng = secrets.SystemRandom()
    while True:
        groups = []
        for _ in range(3):
            chars = [
                rng.choice(_UPPER),
                rng.choice(_LOWER),
                rng.choice(_DIGITS),
                rng.choice(_LOWER),
            ]
            rng.shuffle(chars)
            groups.append("".join(chars))
        candidate = "-".join(groups)
        if not password_problems(candidate, username):
            return candidate
