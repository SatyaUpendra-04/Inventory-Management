"""Every storage adapter runs the same contract tests (ADR-0002).

Plan A (SharePoint) and Plan B (Supabase) adapters are added to ``ADAPTERS`` in Sprint 10.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ims.adapters.memory import memory_storage
from ims.adapters.sqlite import open_sqlite_storage
from ims.ports.repository import Storage

ADAPTERS = ["memory", "sqlite"]


@pytest.fixture(params=ADAPTERS)
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Storage]:
    if request.param == "memory":
        yield memory_storage()
        return
    store, engine = open_sqlite_storage(tmp_path / "contract.sqlite3")
    yield store
    engine.dispose()
