"""Makes the Windows interface fonts available when Qt cannot see system fonts.

The off-screen renderer used for tests and screenshots starts with an empty font
database on Windows; loading the Segoe UI files explicitly gives it real text.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QFontDatabase

_WINDOWS_UI_FONTS = (
    "SegUIVar.ttf",  # Segoe UI Variable (Windows 11)
    "segoeui.ttf",
    "seguisb.ttf",
    "segoeuib.ttf",
)


def ensure_windows_ui_fonts() -> list[str]:
    """Registers Segoe UI fonts if they are missing; returns the families added."""
    if "Segoe UI" in QFontDatabase.families():
        return []
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    added: list[str] = []
    for name in _WINDOWS_UI_FONTS:
        path = fonts_dir / name
        if path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(path))
            added.extend(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(set(added))
