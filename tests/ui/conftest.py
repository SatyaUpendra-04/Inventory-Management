from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from ims.ui.app import UiContext, create_engine
from ims.ui.fonts import ensure_windows_ui_fonts

pytestmark = pytest.mark.ui


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def ui(qapp: QApplication, settings: QSettings) -> Iterator[UiContext]:
    """The full QML UI, loaded off-screen; collects every QML warning."""
    ensure_windows_ui_fonts()
    context = create_engine(settings, version="0.0.0-test", environment="test")
    warnings: list[str] = []
    context.engine.warnings.connect(lambda items: warnings.extend(w.toString() for w in items))
    context.engine.setProperty("collected_warnings", warnings)
    window = context.engine.rootObjects()[0]
    window.setProperty("width", 1440)
    window.setProperty("height", 900)
    settle(300)
    yield context
    for root in context.engine.rootObjects():
        root.deleteLater()
    context.engine.deleteLater()
    settle(50)


def settle(ms: int) -> None:
    """Lets animations and deferred loading finish."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def warnings_of(context: UiContext) -> list[str]:
    return list(context.engine.property("collected_warnings") or [])
