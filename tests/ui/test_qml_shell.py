"""The real QML UI, loaded off-screen: every page, every theme, no QML warnings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickItem, QQuickWindow
from pytestqt.qtbot import QtBot

from ims.ui.app import UiContext
from ims.ui.viewmodels.shell import SECTIONS
from tests.ui.conftest import settle, warnings_of

pytestmark = pytest.mark.ui

SCREENSHOT_DIR = Path(os.environ.get("IMS_SCREENSHOT_DIR", "test-artifacts/screenshots"))


def window_of(ui: UiContext) -> QQuickWindow:
    root = ui.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    return root


def test_main_window_loads_without_warnings(ui: UiContext) -> None:
    window = window_of(ui)
    assert window.title() == "Inventory Management"
    assert ui.shell.current == "gallery"
    assert warnings_of(ui) == []


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_section_renders_in_every_theme_without_warnings(ui: UiContext, mode: str) -> None:
    ui.theme.setMode(mode)
    for high_contrast in (False, True):
        ui.theme.setHighContrast(high_contrast)
        for section in SECTIONS:
            ui.shell.navigate(section.key)
            settle(450)
    assert warnings_of(ui) == []


def test_theme_cross_fade_runs_and_applies(ui: UiContext) -> None:
    ui.theme.setMode("light")
    window = window_of(ui)
    root = ui.engine.rootObjects()[0]
    QMetaObject.invokeMethod(root, "openSignInPreview")
    settle(500)
    QMetaObject.invokeMethod(root, "closeSignInPreview")
    settle(400)
    assert window.isVisible()
    assert warnings_of(ui) == []


def test_sidebar_keyboard_navigation(ui: UiContext, qtbot: QtBot) -> None:
    window = window_of(ui)
    sidebar = window.findChild(QQuickItem, "sidebarNav")
    assert isinstance(sidebar, QQuickItem)
    assert sidebar.property("activeFocusOnTab"), "sidebar list should be reachable with Tab"
    sidebar.forceActiveFocus(Qt.FocusReason.TabFocusReason)
    ui.shell.navigate("gallery")
    settle(50)
    qtbot.keyClick(window, Qt.Key.Key_Down)
    assert ui.shell.current == "settings"
    qtbot.keyClick(window, Qt.Key.Key_Up)
    qtbot.keyClick(window, Qt.Key.Key_Up)
    assert ui.shell.current == "reports"


def test_shortcut_opens_settings(ui: UiContext, qtbot: QtBot) -> None:
    window = window_of(ui)
    window.requestActivate()
    qtbot.keyClick(window, Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)
    settle(100)
    assert ui.shell.current == "settings"


def _not_blank(image: QImage) -> bool:
    step = 37
    colours = {image.pixel(x, y) for x in range(0, image.width(), step)
               for y in range(0, image.height(), step)}  # fmt: skip
    return len(colours) > 20


@pytest.mark.parametrize(
    ("mode", "high_contrast"),
    [("light", False), ("dark", False), ("light", True), ("dark", True)],
)
def test_screenshots_of_key_pages(ui: UiContext, mode: str, high_contrast: bool) -> None:
    """Renders pages for review; CI uploads them as an artifact."""
    ui.theme.setMode(mode)
    ui.theme.setHighContrast(high_contrast)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"{mode}{'-hc' if high_contrast else ''}"
    for key in ("gallery", "settings", "equipment"):
        ui.shell.navigate(key)
        settle(600)
        image = window_of(ui).grabWindow()
        assert not image.isNull() and _not_blank(image), f"{key} rendered blank"
        image.save(str(SCREENSHOT_DIR / f"{key}-{suffix}.png"))
    assert warnings_of(ui) == []
