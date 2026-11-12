"""Composition root: reads settings, sets up logging, wires adapters and starts the UI.

This is the only module allowed to import from ``ims.adapters`` (enforced by import-linter).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import structlog
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication

from ims import APP_ID, APP_NAME, __version__
from ims.adapters.files import LocalFileStore
from ims.adapters.local_auth import LocalAuthProvider
from ims.adapters.sqlite import DB_FILE_NAME, open_sqlite_storage
from ims.adapters.sqlite.repositories import SqliteCredentialStore
from ims.adapters.system_clock import SystemClock
from ims.application.accounts import AccountService
from ims.application.alerts import AlertService
from ims.application.assets import AssetService
from ims.application.batteries import BatteryService
from ims.application.calibration import CalibrationService
from ims.application.catalogue import CatalogueService
from ims.application.deployments import DeploymentService
from ims.application.field_logs import FieldLogService
from ims.application.kits import KitService
from ims.application.maintenance import MaintenanceService
from ims.application.projects import ProjectService
from ims.application.registry import RegistryService
from ims.application.reservations import ReservationService
from ims.application.runner import CommandRunner
from ims.application.sites import SiteService
from ims.application.stock import StockService
from ims.application.users import UserService
from ims.logging_setup import configure_logging, log_uncaught_exception, shutdown_logging
from ims.settings import Backend, Settings
from ims.ui.app import Services, create_engine


def build_services(data_dir: Path) -> tuple[Services, Callable[[], None]]:
    """Wires the local backend (SQLite, Argon2 accounts, files on disk).

    Returns the services and a ``close`` function that releases the database.
    """
    storage, engine = open_sqlite_storage(data_dir / DB_FILE_NAME)
    clock = SystemClock()
    runner = CommandRunner(storage, clock)
    users = UserService(storage, runner, clock)
    files = LocalFileStore(data_dir / "files")
    accounts = AccountService(
        storage, LocalAuthProvider(SqliteCredentialStore(engine)), files, users, runner, clock
    )
    services = Services(
        accounts=accounts,
        users=users,
        sites=SiteService(storage, runner, clock),
        catalogue=CatalogueService(storage, runner),
        assets=AssetService(storage, runner, clock),
        registry=RegistryService(storage, runner, clock, files),
        kits=KitService(storage, runner, clock),
        stock=StockService(storage, runner, clock),
        projects=ProjectService(storage, runner, clock),
        deployments=DeploymentService(storage, runner, clock),
        logs=FieldLogService(storage, runner, clock),
        reservations=ReservationService(storage, runner, clock),
        maintenance=MaintenanceService(storage, runner, clock),
        batteries=BatteryService(storage, runner, clock),
        calibration=CalibrationService(storage, runner, clock, files),
        alerts=AlertService(storage, clock),
        clock=clock,
    )
    return services, engine.dispose


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
    if settings.backend is not Backend.SQLITE:
        log.error("backend_not_available_yet", backend=settings.backend.value)
        shutdown_logging()
        return 2

    existing = QGuiApplication.instance()
    app = (
        existing
        if isinstance(existing, QGuiApplication)
        else QGuiApplication(list(argv) if argv is not None else sys.argv)
    )
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setApplicationVersion(__version__)

    services, close_backend = build_services(settings.data_dir)
    ui = create_engine(
        QSettings(APP_ID, APP_NAME),
        services,
        version=__version__,
        environment=settings.environment.value,
        start_maximized=True,
    )
    ui.engine.warnings.connect(
        lambda warnings: [log.warning("qml_warning", message=w.toString()) for w in warnings]
    )
    if not ui.engine.rootObjects():
        log.error("ui_failed_to_load")
        close_backend()
        shutdown_logging()
        return 1

    exit_code = app.exec()
    ui.tasks.wait_until_idle()  # let queued saves finish before the database closes
    close_backend()
    log.info("app_stopped", exit_code=exit_code)
    shutdown_logging()
    return exit_code
