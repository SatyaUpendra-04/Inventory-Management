"""The real QML UI, loaded off-screen: every page, every theme, no QML warnings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, QPointF, Qt
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
            settle(ui, 400)
    assert warnings_of(ui) == []


def test_sidebar_keyboard_navigation(ui: UiContext, qtbot: QtBot) -> None:
    window = window_of(ui)
    sidebar = window.findChild(QQuickItem, "sidebarNav")
    assert isinstance(sidebar, QQuickItem)
    assert sidebar.property("activeFocusOnTab"), "sidebar list should be reachable with Tab"
    sidebar.forceActiveFocus(Qt.FocusReason.TabFocusReason)
    ui.shell.navigate("gallery")
    settle(ui, 50)
    qtbot.keyClick(window, Qt.Key.Key_Down)
    assert ui.shell.current == "settings"
    qtbot.keyClick(window, Qt.Key.Key_Up)
    qtbot.keyClick(window, Qt.Key.Key_Up)
    assert ui.shell.current == "reports"


def test_shortcut_opens_settings(ui: UiContext, qtbot: QtBot) -> None:
    window = window_of(ui)
    window.requestActivate()
    qtbot.keyClick(window, Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)
    settle(ui, 100)
    assert ui.shell.current == "settings"


def _not_blank(image: QImage) -> bool:
    step = 37
    colours = {
        image.pixel(x, y)
        for x in range(0, image.width(), step)
        for y in range(0, image.height(), step)
    }
    return len(colours) > 12


@pytest.mark.parametrize(
    ("mode", "high_contrast"),
    [("light", False), ("dark", False), ("light", True), ("dark", True)],
)
def test_screenshots_of_key_pages(ui: UiContext, mode: str, high_contrast: bool) -> None:
    """Renders pages for review; CI uploads them as an artifact."""
    ui.theme.setMode(mode)
    ui.theme.setHighContrast(high_contrast)
    ui.sites.create(
        {
            "code": "MAIN-STORE",
            "name": "Main store",
            "kind": "store",
            "region": "Bhubaneswar, Odisha",
            "latitude": "20.2961",
            "longitude": "85.8245",
        }
    )
    ui.people.onboard(
        {
            "fullName": "Ravi Kumar",
            "username": "rkumar",
            "employeeId": "EMP-0102",
            "email": "ravi@example.com",
            "phone": "9123456780",
            "role": "pilot",
            "licenceNumber": "DGCA-RPC-2291",
            "licenceExpiry": "2027-06-30",
        }
    )
    settle(ui, 300)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"{mode}{'-hc' if high_contrast else ''}"
    for key in ("gallery", "settings", "people", "sites", "profile", "equipment", "stock"):
        ui.shell.navigate(key)
        settle(ui, 600)
        image = window_of(ui).grabWindow()
        assert not image.isNull() and _not_blank(image), f"{key} rendered blank"
        image.save(str(SCREENSHOT_DIR / f"{key}-{suffix}.png"))
    ui.session.signOut()
    settle(ui, 600)
    window_of(ui).grabWindow().save(str(SCREENSHOT_DIR / f"sign-in-{suffix}.png"))
    assert warnings_of(ui) == []


def test_sidebar_focus_ring_is_for_keyboard_only(ui: UiContext, qtbot: QtBot) -> None:
    """A mouse click selects without a ring; Tab and arrow keys show the ring."""
    window = window_of(ui)
    sidebar = window.findChild(QQuickItem, "sidebarNav")
    assert isinstance(sidebar, QQuickItem)
    projects = QMetaObject.invokeMethod(
        sidebar, "itemAtIndex", Q_RETURN_ARG("QQuickItem*"), Q_ARG(int, 1)
    )
    assert isinstance(projects, QQuickItem)
    centre = projects.mapToScene(QPointF(projects.width() / 2, projects.height() / 2)).toPoint()
    qtbot.mouseClick(window, Qt.MouseButton.LeftButton, pos=centre)
    settle(ui, 100)
    assert ui.shell.current == "projects"
    assert sidebar.hasActiveFocus() and not sidebar.property("keyboardFocus")
    qtbot.keyClick(window, Qt.Key.Key_Down)
    assert ui.shell.current == "deployments" and sidebar.property("keyboardFocus")
    sidebar.setFocus(False)
    settle(ui, 50)
    sidebar.forceActiveFocus(Qt.FocusReason.TabFocusReason)
    assert sidebar.property("keyboardFocus")
    assert warnings_of(ui) == []
