"""Rules for uploaded files: identified by their content, not their file name."""

from __future__ import annotations

from enum import StrEnum

from ims.domain.common.errors import RuleViolation


class FileKind(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    PDF = "pdf"


_SIGNATURES: tuple[tuple[bytes, FileKind], ...] = (
    (b"\x89PNG\r\n\x1a\n", FileKind.PNG),
    (b"\xff\xd8\xff", FileKind.JPEG),
    (b"%PDF-", FileKind.PDF),
)

CONTENT_TYPES = {
    FileKind.PNG: "image/png",
    FileKind.JPEG: "image/jpeg",
    FileKind.PDF: "application/pdf",
}

PICTURE_KINDS = frozenset({FileKind.PNG, FileKind.JPEG})
DOCUMENT_KINDS = frozenset({FileKind.PNG, FileKind.JPEG, FileKind.PDF})
MAX_PICTURE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


def detect_kind(content: bytes) -> FileKind | None:
    return next((kind for magic, kind in _SIGNATURES if content.startswith(magic)), None)


def check_upload(content: bytes, allowed: frozenset[FileKind], max_bytes: int) -> FileKind:
    """Returns the file's real kind, or raises :class:`RuleViolation` explaining the problem."""
    if not content:
        raise RuleViolation("The file is empty.")
    if len(content) > max_bytes:
        raise RuleViolation(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    kind = detect_kind(content)
    if kind is None or kind not in allowed:
        names = ", ".join(sorted(k.value.upper() for k in allowed))
        raise RuleViolation(f"Only {names} files can be used here.")
    return kind
