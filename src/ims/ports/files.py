"""File storage port: profile pictures, licence copies, calibration certificates."""

from __future__ import annotations

import re
from typing import Protocol

from ims.domain.files import FileKind

FILE_REF = re.compile(r"^[0-9a-f]{64}\.(png|jpeg|pdf)$")
"""References are content hashes plus kind, e.g. ``3a7b...e1.png``: the same file is
stored once, and storing it again (a retried upload) returns the same reference."""


class FileStore(Protocol):
    def put(self, content: bytes, kind: FileKind) -> str: ...

    def get(self, ref: str) -> bytes | None:
        """The file's bytes, or ``None`` if the reference is unknown or malformed."""
        ...
