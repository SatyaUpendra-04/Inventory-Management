"""File stores: on disk for the app, in memory for tests.

Files are stored under their SHA-256 hash, so a retried upload of the same bytes
returns the same reference and never creates a duplicate.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from ims.domain.files import FileKind
from ims.ports.files import FILE_REF


def _ref(content: bytes, kind: FileKind) -> str:
    return f"{hashlib.sha256(content).hexdigest()}.{kind.value}"


class LocalFileStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, ref: str) -> Path:
        return self._root / ref[:2] / ref

    def put(self, content: bytes, kind: FileKind) -> str:
        ref = _ref(content, kind)
        target = self._path(ref)
        if target.exists():
            return ref
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file, then rename: a crash never leaves half a file.
        fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            Path(temp).replace(target)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
        return ref

    def get(self, ref: str) -> bytes | None:
        if not FILE_REF.match(ref):
            return None
        path = self._path(ref)
        return path.read_bytes() if path.is_file() else None


class MemoryFileStore:
    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def put(self, content: bytes, kind: FileKind) -> str:
        ref = _ref(content, kind)
        self._files.setdefault(ref, content)
        return ref

    def get(self, ref: str) -> bytes | None:
        return self._files.get(ref) if FILE_REF.match(ref) else None
