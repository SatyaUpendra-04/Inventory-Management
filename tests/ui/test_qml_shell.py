"""The real QML UI, loaded off-screen: every page, every theme, no QML warnings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, QObject, QPointF, QSettings, Qt
from PySide6.QtGui import QImage, QWindow
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ims.ui.app import Services, UiContext, create_engine
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
    for key in (
        "gallery",
        "settings",
        "people",
        "sites",
        "profile",
        "equipment",
        "stock",
        "projects",
        "deployments",
    ):
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


def test_window_opens_maximised_and_f11_toggles_full_screen(
    qapp: QApplication, tmp_path: Path, services: Services, qtbot: QtBot
) -> None:
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    context = create_engine(settings, services, version="0.0.0-test", environment="test",
                            start_maximized=True)  # fmt: skip
    window = context.engine.rootObjects()[0]
    assert isinstance(window, QWindow)
    settle(context)
    assert window.isVisible()
    assert window.visibility() is QWindow.Visibility.Maximized
    qtbot.keyClick(window, Qt.Key.Key_F11)
    assert window.visibility() is QWindow.Visibility.FullScreen
    qtbot.keyClick(window, Qt.Key.Key_F11)
    assert window.visibility() is QWindow.Visibility.Maximized
    context.tasks.wait_until_idle()
    window.deleteLater()
    context.engine.deleteLater()
    settle(None, 50)


def _click(ui: UiContext, qtbot: QtBot, item: QQuickItem) -> None:
    centre = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    qtbot.mouseClick(window_of(ui), Qt.MouseButton.LeftButton, pos=centre.toPoint())
    settle(ui, 250)


def test_date_picker_jumps_by_month_and_year(ui: UiContext, qtbot: QtBot) -> None:
    """Far-off dates take a few clicks: title -> months -> years -> pick."""
    ui.shell.navigate("gallery")
    settle(ui, 500)
    window = window_of(ui)
    picker = next(
        o
        for o in window.findChildren(QObject)
        if o.metaObject().className().startswith("AppDatePicker")
    )
    calendar = picker.findChild(QObject, "calendar")
    assert calendar is not None
    QMetaObject.invokeMethod(calendar, "open")
    settle(ui, 300)
    content = calendar.property("contentItem")
    assert isinstance(content, QQuickItem)

    grid = content.findChild(QQuickItem, "monthYearGrid")
    assert grid is not None

    def visible(name: str) -> QQuickItem:
        # Repeater cells are visual children of the grid, not QObject children.
        items = [*content.findChildren(QQuickItem, name), *grid.childItems()]
        return next(i for i in items if i.objectName() == name and i.isVisible())

    year = int(calendar.property("year"))
    title = visible("calendarTitle")
    _click(ui, qtbot, title)
    assert calendar.property("mode") == "months"
    _click(ui, qtbot, title)
    assert calendar.property("mode") == "years"
    _click(ui, qtbot, visible("next"))  # 12 years on
    assert int(calendar.property("year")) == year + 12
    first = int(calendar.property("firstYear"))
    target = first + 2  # a year on the next 12-year page
    _click(ui, qtbot, visible("cell2"))
    assert calendar.property("mode") == "months" and int(calendar.property("year")) == target
    _click(ui, qtbot, visible("cell5"))  # June
    assert calendar.property("mode") == "days" and int(calendar.property("month")) == 5
    _click(ui, qtbot, visible("today"))
    assert picker.property("hasDate") is True and not calendar.property("visible")
    assert warnings_of(ui) == []
