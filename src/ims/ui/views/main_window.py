"""Main application window (Sprint 0 shell)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QWidget

from ims import APP_NAME


class MainWindow(QMainWindow):
    """Top-level window. Navigation and pages arrive in Sprint 2."""

    def __init__(self, version: str, environment: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)

        placeholder = QLabel(f"{APP_NAME}\nFoundation build", self)
        placeholder.setObjectName("placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(placeholder)

        self.statusBar().showMessage(f"Version {version} · {environment}")
