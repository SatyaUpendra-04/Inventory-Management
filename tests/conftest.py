"""Shared test configuration."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Qt must render off-screen in CI and headless runs; set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ims.logging_setup import shutdown_logging


@pytest.fixture(autouse=True)
def _isolated_logging() -> Iterator[None]:
    """Closes any log handlers a test opened, so files are released on Windows."""
    yield
    shutdown_logging()
