import pytest
from pytestqt.qtbot import QtBot

from ims import APP_NAME
from ims.ui.views.main_window import MainWindow

pytestmark = pytest.mark.ui


def test_main_window_shows_title_version_and_environment(qtbot: QtBot) -> None:
    window = MainWindow(version="1.2.3", environment="test")
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == APP_NAME
    assert window.isVisible()
    assert window.statusBar().currentMessage() == "Version 1.2.3 · test"
