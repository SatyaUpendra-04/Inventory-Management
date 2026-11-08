"""Builds the QML engine with the theme, icons and view-models wired in."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from ims.ui.models.sample_equipment import SampleEquipmentModel, SortableModel
from ims.ui.theme.icons import IconProvider
from ims.ui.theme.manager import ThemeManager
from ims.ui.viewmodels.shell import ShellViewModel
from ims.ui.viewmodels.toasts import ToastService

QML_DIR = Path(__file__).resolve().parent / "qml"
MAIN_QML = QML_DIR / "Main.qml"


@dataclass
class UiContext:
    engine: QQmlApplicationEngine
    theme: ThemeManager
    shell: ShellViewModel
    toasts: ToastService
    sample_table: SortableModel


def create_engine(
    settings: QSettings,
    *,
    version: str,
    environment: str,
    initial_section: str = "gallery",
    root_qml: Path = MAIN_QML,
    parent: QObject | None = None,
) -> UiContext:
    """Creates the engine and loads ``root_qml``. Call after the QGuiApplication exists."""
    QQuickStyle.setStyle("Basic")  # fully restylable controls; our design system draws them
    engine = QQmlApplicationEngine(parent)
    engine.addImageProvider("icon", IconProvider())

    theme = ThemeManager(settings, engine)
    shell = ShellViewModel(initial_section, engine)
    toasts = ToastService(engine)
    sample_table = SortableModel(SampleEquipmentModel(engine), engine)

    context = engine.rootContext()
    context.setContextProperty("Theme", theme)
    context.setContextProperty("Shell", shell)
    context.setContextProperty("Toasts", toasts)
    context.setContextProperty("SampleTable", sample_table)
    context.setContextProperty("AppVersion", version)
    context.setContextProperty("AppEnvironment", environment)

    engine.load(QUrl.fromLocalFile(str(root_qml)))
    return UiContext(engine, theme, shell, toasts, sample_table)
