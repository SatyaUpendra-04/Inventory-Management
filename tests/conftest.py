"""Shared test configuration."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from hypothesis import settings

# Qt must render off-screen in CI and headless runs; set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ims.logging_setup import shutdown_logging

# Property-test effort. Choose with HYPOTHESIS_PROFILE=dev|ci|stress (default: dev).
settings.register_profile("dev", max_examples=300)
settings.register_profile("ci", max_examples=2_000, deadline=None, print_blob=True)
settings.register_profile("stress", max_examples=20_000, deadline=None, print_blob=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(autouse=True)
def _isolated_logging() -> Iterator[None]:
    """Closes any log handlers a test opened, so files are released on Windows."""
    yield
    shutdown_logging()
