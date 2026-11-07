"""Composition root: reads settings, sets up logging, wires adapters and starts the UI.

This is the only module allowed to import from ``ims.adapters`` (enforced by import-linter).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

import structlog
from PySide6.QtWidgets import QApplication

from ims import APP_ID, APP_NAME, __version__
from ims.logging_setup import configure_logging, log_uncaught_exception, shutdown_logging
from ims.settings import Settings
from ims.ui.views.main_window import MainWindow


def main(argv: Sequence[str] | None = None) -> int:
    settings = Settings.from_env()
    log_path = configure_logging(settings.log_dir, settings.log_level)
    sys.excepthook = log_uncaught_exception
    log = structlog.get_logger(__name__)
    log.info(
        "app_starting",
        version=__version__,
        environment=settings.environment.value,
        backend=settings.backend.value,
        log_file=str(log_path),
    )

    existing = QApplication.instance()
    app = (
        existing
        if isinstance(existing, QApplication)
        else QApplication(list(argv) if argv is not None else sys.argv)
    )
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setApplicationVersion(__version__)

    window = MainWindow(version=__version__, environment=settings.environment.value)
    window.show()

    exit_code = app.exec()
    log.info("app_stopped", exit_code=exit_code)
    shutdown_logging()
    return exit_code
