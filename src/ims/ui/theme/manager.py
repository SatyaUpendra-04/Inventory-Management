"""``Theme``: the design tokens exposed to QML, kept in step with user and system settings."""

from __future__ import annotations

import ctypes
import sys
from typing import Any

from PySide6.QtCore import Property, QObject, QSettings, Qt, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication

from ims.ui.theme.color import hex_to_oklch
from ims.ui.theme.tokens import (
    ACCENT_PRESETS,
    DEFAULT_ACCENT,
    MOTION,
    RADIUS,
    SPACING,
    TYPOGRAPHY,
    Theme,
    ThemeMode,
    accent_adjustment,
    accent_problems,
    build_theme,
)

_KEY_MODE = "appearance/mode"
_KEY_ACCENT = "appearance/accent"
_KEY_CONTRAST = "appearance/highContrast"
_KEY_MOTION = "appearance/reduceMotion"


def windows_animations_enabled() -> bool:
    """Windows "Animation effects" setting (Settings > Accessibility > Visual effects)."""
    if sys.platform != "win32":
        return True
    spi_getclientareaanimation = 0x1042
    enabled = ctypes.c_int(1)
    ok = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined,unused-ignore]
        spi_getclientareaanimation, 0, ctypes.byref(enabled), 0
    )
    return bool(enabled.value) if ok else True


def _first_installed(families: tuple[str, ...]) -> str:
    installed = set(QFontDatabase.families())
    return next((f for f in families if f in installed), families[-1])


class ThemeManager(QObject):
    """QML singleton-like object (``Theme``) with every token the UI needs."""

    changed = Signal()

    def __init__(self, settings: QSettings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._mode = ThemeMode(str(settings.value(_KEY_MODE, ThemeMode.SYSTEM.value)))
        accent = str(settings.value(_KEY_ACCENT, DEFAULT_ACCENT))
        self._accent = accent if not accent_problems(accent) else DEFAULT_ACCENT
        self._high_contrast = _as_bool(settings.value(_KEY_CONTRAST, False))
        self._reduce_motion_setting = _as_bool(settings.value(_KEY_MOTION, False))
        self._system_animations = windows_animations_enabled()
        self._font = _first_installed(TYPOGRAPHY["families"])
        self._display_font = _first_installed(TYPOGRAPHY["displayFamilies"])
        self._theme = self._build()

        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(self._on_system_scheme_changed)
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.applicationStateChanged.connect(self._on_app_state_changed)

    # ------------------------------------------------------------------ helpers

    def _system_is_dark(self) -> bool:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

    def _is_dark(self) -> bool:
        if self._mode is ThemeMode.SYSTEM:
            return self._system_is_dark()
        return self._mode is ThemeMode.DARK

    def _build(self) -> Theme:
        return build_theme(
            dark=self._is_dark(), accent=self._accent, high_contrast=self._high_contrast
        )

    def _refresh(self) -> None:
        self._theme = self._build()
        self.changed.emit()

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._mode is ThemeMode.SYSTEM:
            self._refresh()

    def _on_app_state_changed(self, state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            animations = windows_animations_enabled()
            if animations != self._system_animations:
                self._system_animations = animations
                self.changed.emit()

    # ------------------------------------------------------------------ properties

    def _get_mode(self) -> str:
        return self._mode.value

    def _get_dark(self) -> bool:
        return self._theme.dark

    def _get_high_contrast(self) -> bool:
        return self._high_contrast

    def _get_accent(self) -> str:
        return self._accent

    def _get_colors(self) -> dict[str, str]:
        return dict(self._theme.colors)

    def _get_shadows(self) -> dict[str, Any]:
        return {k: dict(v) for k, v in self._theme.shadows.items()}

    def _get_palettes(self) -> dict[str, list[str]]:
        return {name: list(p.steps) for name, p in self._theme.palettes.items()}

    def _get_reduced_motion(self) -> bool:
        return self._reduce_motion_setting or not self._system_animations

    def _get_reduce_motion_setting(self) -> bool:
        return self._reduce_motion_setting

    def _get_system_reduces_motion(self) -> bool:
        return not self._system_animations

    def _get_type(self) -> dict[str, Any]:
        data = {k: v for k, v in TYPOGRAPHY.items() if not isinstance(v, tuple)}
        data["family"] = self._font
        data["displayFamily"] = self._display_font
        return data

    def _get_space(self) -> dict[str, int]:
        return dict(SPACING)

    def _get_radius(self) -> dict[str, int]:
        return dict(RADIUS)

    def _get_motion(self) -> dict[str, Any]:
        data = {k: (list(v) if isinstance(v, tuple) else v) for k, v in MOTION.items()}
        if self._get_reduced_motion():
            data["hoverLift"] = 0
            data["pressScale"] = 1.0
        return data

    def _get_presets(self) -> list[dict[str, str]]:
        return [{"name": name, "color": color} for name, color in ACCENT_PRESETS.items()]

    mode = Property(str, _get_mode, notify=changed)
    dark = Property(bool, _get_dark, notify=changed)
    highContrast = Property(bool, _get_high_contrast, notify=changed)  # noqa: N815 (QML name)
    accent = Property(str, _get_accent, notify=changed)
    colors = Property(dict, _get_colors, notify=changed)
    shadows = Property(dict, _get_shadows, notify=changed)
    palettes = Property(dict, _get_palettes, notify=changed)
    reducedMotion = Property(bool, _get_reduced_motion, notify=changed)  # noqa: N815
    reduceMotionSetting = Property(bool, _get_reduce_motion_setting, notify=changed)  # noqa: N815
    systemReducesMotion = Property(bool, _get_system_reduces_motion, notify=changed)  # noqa: N815
    type = Property(dict, _get_type, constant=True)
    space = Property(dict, _get_space, constant=True)
    radius = Property(dict, _get_radius, constant=True)
    motion = Property(dict, _get_motion, notify=changed)
    presets = Property(list, _get_presets, constant=True)

    # ------------------------------------------------------------------ slots

    @Slot(str)
    def setMode(self, mode: str) -> None:  # noqa: N802 (QML name)
        new = ThemeMode(mode)
        if new is self._mode:
            return
        self._mode = new
        self._settings.setValue(_KEY_MODE, new.value)
        self._refresh()

    @Slot(str, result=bool)
    def setAccent(self, accent: str) -> bool:  # noqa: N802
        """Applies ``accent`` if it is readable; returns whether it was applied."""
        if accent_problems(accent):
            return False
        normalised = "#" + accent.strip().lstrip("#").lower()
        if normalised != self._accent:
            self._accent = normalised
            self._settings.setValue(_KEY_ACCENT, normalised)
            self._refresh()
        return True

    @Slot(str, result="QStringList")
    def accentProblems(self, accent: str) -> list[str]:  # noqa: N802
        return accent_problems(accent)

    @Slot(str, result=bool)
    def accentIsAdjusted(self, accent: str) -> bool:  # noqa: N802
        """True if the accent had to be shifted noticeably to keep button text readable."""
        if accent_problems(accent):
            return False
        return max(accent_adjustment(accent, dark=d) for d in (False, True)) > 0.02

    @Slot(str, result=bool)
    def isValidHex(self, value: str) -> bool:  # noqa: N802
        try:
            hex_to_oklch(value)
        except ValueError:
            return False
        return True

    @Slot(bool)
    def setHighContrast(self, enabled: bool) -> None:  # noqa: N802
        if enabled != self._high_contrast:
            self._high_contrast = enabled
            self._settings.setValue(_KEY_CONTRAST, enabled)
            self._refresh()

    @Slot(bool)
    def setReduceMotion(self, enabled: bool) -> None:  # noqa: N802
        if enabled != self._reduce_motion_setting:
            self._reduce_motion_setting = enabled
            self._settings.setValue(_KEY_MOTION, enabled)
            self.changed.emit()

    @Slot(str, float, result=str)
    def alpha(self, color: str, opacity: float) -> str:
        """``color`` with transparency, for translucent fills."""
        hex_part = color.lstrip("#")[-6:]
        return f"#{round(max(0.0, min(1.0, opacity)) * 255):02x}{hex_part}"


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}
