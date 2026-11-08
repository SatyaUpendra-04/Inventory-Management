from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from ims.adapters.files import MemoryFileStore
from ims.adapters.local_auth import LocalAuthProvider, MemoryCredentialStore, fast_hasher
from ims.adapters.memory import memory_storage
from ims.application.accounts import AccountService
from ims.application.runner import CommandRunner
from ims.application.sites import SiteService
from ims.application.users import UserService
from ims.ui.app import Services, UiContext, create_engine
from ims.ui.fonts import ensure_windows_ui_fonts
from tests.fakes import FixedClock

pytestmark = pytest.mark.ui

ADMIN_PASSWORD = "Field-Survey-2026!"
ADMIN = {
    "fullName": "Satya Upendra",
    "username": "satya",
    "employeeId": "EMP-0001",
    "email": "satya@example.com",
    "phone": "9876543210",
}


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def services() -> Services:
    storage, clock = memory_storage(), FixedClock()
    runner = CommandRunner(storage, clock)
    users = UserService(storage, runner, clock)
    auth = LocalAuthProvider(MemoryCredentialStore(), fast_hasher())
    accounts = AccountService(storage, auth, MemoryFileStore(), users, runner, clock)
    return Services(
        accounts=accounts, users=users, sites=SiteService(storage, runner, clock), clock=clock
    )


@pytest.fixture
def picture(tmp_path: Path) -> str:
    image = QImage(320, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("#2f6fed"))
    path = tmp_path / "me.png"
    image.save(str(path))
    return str(path)


@pytest.fixture
def fresh_ui(qapp: QApplication, settings: QSettings, services: Services) -> Iterator[UiContext]:
    """The full QML UI on an empty system (first-run setup showing)."""
    ensure_windows_ui_fonts()
    context = create_engine(settings, services, version="0.0.0-test", environment="test",
                            initial_section="gallery")  # fmt: skip
    warnings: list[str] = []
    context.engine.warnings.connect(lambda items: warnings.extend(w.toString() for w in items))
    context.engine.setProperty("collected_warnings", warnings)
    window = context.engine.rootObjects()[0]
    window.setProperty("width", 1440)
    window.setProperty("height", 900)
    settle(context, 300)
    yield context
    context.tasks.wait_until_idle()
    for root in context.engine.rootObjects():
        root.deleteLater()
    context.engine.deleteLater()
    settle(None, 50)  # the task queue is deleted with the engine


@pytest.fixture
def ui(fresh_ui: UiContext, picture: str) -> UiContext:
    """The full QML UI with the first administrator set up and signed in."""
    sign_up_admin(fresh_ui, picture)
    return fresh_ui


def sign_up_admin(ui: UiContext, picture: str) -> None:
    ui.session.setupAdmin(ADMIN, ADMIN_PASSWORD, ADMIN_PASSWORD)
    settle(ui)
    ui.session.uploadPicture(picture)
    settle(ui)
    ui.session.finishProfile()
    settle(ui, 300)
    assert ui.session.stage == "app", ui.session.error


def settle(ui: UiContext | None = None, ms: int = 150) -> None:
    """Lets background tasks finish and animations run."""
    if ui is not None:
        ui.tasks.wait_until_idle()
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    if ui is not None:
        ui.tasks.wait_until_idle()


def warnings_of(context: UiContext) -> list[str]:
    return list(context.engine.property("collected_warnings") or [])
