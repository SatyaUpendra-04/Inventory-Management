"""Builds the QML engine with the theme, icons, services and view-models wired in."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from ims.application.accounts import AccountService
from ims.application.sites import SiteService
from ims.application.users import UserService
from ims.ports.clock import Clock
from ims.ui.images import FileImageProvider
from ims.ui.models.sample_equipment import SampleEquipmentModel, SortableModel
from ims.ui.tasks import TaskQueue
from ims.ui.theme.icons import IconProvider
from ims.ui.theme.manager import ThemeManager
from ims.ui.viewmodels.people import PeopleViewModel
from ims.ui.viewmodels.session import SessionViewModel
from ims.ui.viewmodels.shell import ShellViewModel
from ims.ui.viewmodels.sites import SitesViewModel
from ims.ui.viewmodels.toasts import ToastService

QML_DIR = Path(__file__).resolve().parent / "qml"
MAIN_QML = QML_DIR / "Main.qml"


@dataclass(frozen=True, slots=True)
class Services:
    """Application services the UI talks to (never storage or adapters directly)."""

    accounts: AccountService
    users: UserService
    sites: SiteService
    clock: Clock


@dataclass
class UiContext:
    engine: QQmlApplicationEngine
    theme: ThemeManager
    shell: ShellViewModel
    toasts: ToastService
    tasks: TaskQueue
    session: SessionViewModel
    people: PeopleViewModel
    sites: SitesViewModel
    sample_table: SortableModel


def create_engine(
    settings: QSettings,
    services: Services,
    *,
    version: str,
    environment: str,
    initial_section: str = "dashboard",
    synchronous_tasks: bool = False,
    root_qml: Path = MAIN_QML,
    parent: QObject | None = None,
) -> UiContext:
    """Creates the engine and loads ``root_qml``. Call after the QGuiApplication exists."""
    QQuickStyle.setStyle("Basic")  # fully restylable controls; our design system draws them
    engine = QQmlApplicationEngine(parent)
    engine.addImageProvider("icon", IconProvider())
    engine.addImageProvider("files", FileImageProvider(services.accounts.file))

    tasks = TaskQueue(engine, synchronous=synchronous_tasks)
    theme = ThemeManager(settings, engine)
    shell = ShellViewModel(initial_section, production=environment == "production", parent=engine)
    toasts = ToastService(engine)
    session = SessionViewModel(services.accounts, services.users, services.clock, tasks, engine)
    people = PeopleViewModel(
        session, services.users, services.accounts, services.clock, tasks, engine
    )
    sites = SitesViewModel(session, services.sites, tasks, engine)
    sample_table = SortableModel(SampleEquipmentModel(engine), engine)

    session.signedIn.connect(lambda: shell.set_permissions(session.permission_codes()))
    session.signedOut.connect(lambda: shell.set_permissions(()))
    people.saved.connect(lambda message: toasts.show("success", message, ""))
    sites.saved.connect(lambda message: toasts.show("success", message, ""))

    context = engine.rootContext()
    for name, value in {
        "Theme": theme,
        "Shell": shell,
        "Toasts": toasts,
        "Tasks": tasks,
        "Session": session,
        "People": people,
        "Sites": sites,
        "SampleTable": sample_table,
        "AppVersion": version,
        "AppEnvironment": environment,
    }.items():
        context.setContextProperty(name, value)

    engine.load(QUrl.fromLocalFile(str(root_qml)))
    return UiContext(engine, theme, shell, toasts, tasks, session, people, sites, sample_table)
