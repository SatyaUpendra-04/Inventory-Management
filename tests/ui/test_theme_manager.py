from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from ims.ui.theme.icons import IconProvider, available_icons, render_icon
from ims.ui.theme.manager import ThemeManager
from ims.ui.theme.tokens import DEFAULT_ACCENT
from ims.ui.viewmodels.shell import SECTIONS, ShellViewModel
from ims.ui.viewmodels.toasts import ToastService

pytestmark = pytest.mark.ui


class TestThemeManager:
    def test_choices_are_saved_and_restored(self, qapp: QApplication, settings: QSettings) -> None:
        theme = ThemeManager(settings)
        changes: list[None] = []
        theme.changed.connect(lambda: changes.append(None))
        theme.setMode("dark")
        assert theme.setAccent("#12A594")
        theme.setHighContrast(True)
        theme.setReduceMotion(True)
        assert len(changes) == 4
        assert theme.dark and theme.accent == "#12a594" and theme.highContrast

        restored = ThemeManager(settings)
        assert (restored.mode, restored.accent, restored.highContrast) == ("dark", "#12a594", True)
        assert restored.reducedMotion and restored.motion["pressScale"] == 1.0

    def test_light_and_dark_tokens(self, qapp: QApplication, settings: QSettings) -> None:
        theme = ThemeManager(settings)
        theme.setMode("light")
        light_window = theme.colors["window"]
        theme.setMode("dark")
        assert theme.colors["window"] != light_window
        assert QColor(theme.colors["window"]).lightness() < QColor(light_window).lightness()
        theme.setMode("dark")  # no change, no signal storm
        assert set(theme.palettes) >= {"accent", "neutral", "success", "danger"}
        assert len(theme.palettes["accent"]) == 12

    def test_invalid_accent_is_refused(self, qapp: QApplication, settings: QSettings) -> None:
        theme = ThemeManager(settings)
        assert not theme.setAccent("not a colour")
        assert theme.accent == DEFAULT_ACCENT
        assert theme.accentProblems("nope") and not theme.isValidHex("nope")
        assert theme.isValidHex("#abcdef") and not theme.accentIsAdjusted("#2f6fed")

    def test_bad_saved_accent_falls_back(self, qapp: QApplication, settings: QSettings) -> None:
        settings.setValue("appearance/accent", "garbage")
        assert ThemeManager(settings).accent == DEFAULT_ACCENT

    def test_tokens_exposed_to_qml(self, qapp: QApplication, settings: QSettings) -> None:
        theme = ThemeManager(settings)
        assert theme.type["family"] and theme.type["body"] == 14
        assert theme.space["md"] == 16 and theme.radius["lg"] == 14
        assert len(theme.motion["easing"]) == 6
        assert {p["name"] for p in theme.presets} >= {"Blue", "Green"}
        assert theme.alpha("#2f6fed", 0.5) == "#802f6fed"


class TestIcons:
    def test_every_icon_renders_visible_pixels(self, qapp: QApplication) -> None:
        names = available_icons()
        assert len(names) >= 40
        for name in names:
            image = render_icon(name, "#ff0000", QSize(24, 24))
            alpha = [image.pixelColor(x, y).alpha() for x in range(24) for y in range(24)]
            assert max(alpha) > 200, f"{name} rendered nothing"

    def test_provider_tints_and_sizes(self, qapp: QApplication) -> None:
        provider = IconProvider()
        size = QSize()
        image = provider.requestImage("check?color=%2300ff00", size, QSize(40, 40))
        assert (image.width(), image.height(), size.width()) == (40, 40, 40)
        colours = {image.pixelColor(x, y).name() for x in range(40) for y in range(40)
                   if image.pixelColor(x, y).alpha() == 255}  # fmt: skip
        assert colours == {"#00ff00"}

    def test_unknown_or_unsafe_names_give_blank_images(self, qapp: QApplication) -> None:
        provider = IconProvider()
        for request in ("does-not-exist", "../../secrets", "check?color=javascript:1"):
            image = provider.requestImage(request, QSize(), QSize())
            assert image.width() == 20
        unsafe = provider.requestImage("../x", QSize(), QSize(16, 16))
        assert max(unsafe.pixelColor(x, y).alpha() for x in range(16) for y in range(16)) == 0


class TestViewModels:
    def test_navigation(self, qapp: QApplication) -> None:
        shell = ShellViewModel("gallery")
        shell.set_permissions(["user.manage", "site.view"])
        seen: list[str] = []
        shell.currentChanged.connect(lambda: seen.append(shell.current))
        shell.navigate("people")
        shell.navigate("people")  # no repeat signal
        shell.navigate("nowhere")  # ignored
        assert seen == ["people"] and shell.currentSection["page"] == "PeoplePage"
        shell.step(-100)
        assert shell.current == SECTIONS[0].key
        shell.step(100)
        assert shell.current == "settings"  # last item in the sidebar
        shell.navigate("profile")  # reachable, but not listed in the sidebar
        assert shell.current == "profile"
        assert "profile" not in [s["key"] for s in shell.sections]
        shell.step(1)  # from a page outside the sidebar, arrows start at the top
        assert shell.current == SECTIONS[0].key
        assert ShellViewModel("bogus").current == SECTIONS[0].key

    def test_sections_follow_permissions_and_environment(self, qapp: QApplication) -> None:
        crew = ShellViewModel("gallery")
        crew.set_permissions(["site.view", "asset.view"])
        keys = [s["key"] for s in crew.sections]
        assert "people" not in keys and "sites" in keys and "gallery" in keys
        crew.navigate("people")
        assert crew.current != "people"
        production = ShellViewModel("gallery", production=True)
        production.set_permissions(["user.manage", "site.view"])
        assert "gallery" not in [s["key"] for s in production.sections]
        assert production.current == SECTIONS[0].key

    def test_toasts_normalise_kind(self, qapp: QApplication) -> None:
        toasts = ToastService()
        got: list[tuple[str, str, str]] = []
        toasts.posted.connect(lambda k, t, m: got.append((k, t, m)))
        toasts.show("success", "Saved", "")
        toasts.show("weird", "Hello", "World")
        assert got == [("success", "Saved", ""), ("info", "Hello", "World")]


def test_sample_table_sorts(qapp: QApplication) -> None:
    from ims.ui.models.sample_equipment import SampleEquipmentModel, SortableModel

    model = SortableModel(SampleEquipmentModel())
    assert model.columnCount() == 6 and model.rowCount() > 5
    model.sortBy(5, True)
    assert model.index(0, 0).data() == "GNS-0004"  # most hours first
    model.sortBy(0, False)
    assert model.index(0, 0).data() == "BAT-0114"


def test_fonts_helper_is_idempotent(qapp: QApplication, tmp_path: Path) -> None:
    from ims.ui.fonts import ensure_windows_ui_fonts

    ensure_windows_ui_fonts()
    assert ensure_windows_ui_fonts() == []
