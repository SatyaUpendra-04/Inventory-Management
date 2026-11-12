"""Builds the QML engine with the theme, icons, services and view-models wired in."""

# ``Services`` lives in ``ims.ui.app_services``; it is re-exported here for callers.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from ims.ui.app_services import Services
from ims.ui.images import FileImageProvider
from ims.ui.models.sample_equipment import SampleEquipmentModel, SortableModel
from ims.ui.tasks import TaskQueue
from ims.ui.theme.icons import IconProvider
from ims.ui.theme.manager import ThemeManager
from ims.ui.viewmodels.alerts import AlertsViewModel
from ims.ui.viewmodels.batteries import BatteriesViewModel
from ims.ui.viewmodels.deployments import DeploymentsViewModel
from ims.ui.viewmodels.equipment import EquipmentViewModel
from ims.ui.viewmodels.kits import KitsViewModel
from ims.ui.viewmodels.maintenance import MaintenanceViewModel
from ims.ui.viewmodels.people import PeopleViewModel
from ims.ui.viewmodels.projects import ProjectsViewModel
from ims.ui.viewmodels.reservations import ReservationsViewModel
from ims.ui.viewmodels.session import SessionViewModel
from ims.ui.viewmodels.shell import ShellViewModel
from ims.ui.viewmodels.sites import SitesViewModel
from ims.ui.viewmodels.stock import StockViewModel
from ims.ui.viewmodels.toasts import ToastService

QML_DIR = Path(__file__).resolve().parent / "qml"
MAIN_QML = QML_DIR / "Main.qml"


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
    equipment: EquipmentViewModel
    kits: KitsViewModel
    stock: StockViewModel
    projects: ProjectsViewModel
    deployments: DeploymentsViewModel
    reservations: ReservationsViewModel
    maintenance: MaintenanceViewModel
    batteries: BatteriesViewModel
    alerts: AlertsViewModel
    sample_table: SortableModel


def create_engine(
    settings: QSettings,
    services: Services,
    *,
    version: str,
    environment: str,
    initial_section: str = "dashboard",
    synchronous_tasks: bool = False,
    start_maximized: bool = False,
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
    equipment = EquipmentViewModel(session, services, tasks, engine)
    kits = KitsViewModel(session, services, tasks, engine)
    stock = StockViewModel(session, services, tasks, engine)
    projects = ProjectsViewModel(session, services, tasks, engine)
    deployments = DeploymentsViewModel(session, services, tasks, engine)
    reservations = ReservationsViewModel(session, services, tasks, engine)
    maintenance = MaintenanceViewModel(session, services, tasks, engine)
    batteries = BatteriesViewModel(session, services, tasks, engine)
    alerts = AlertsViewModel(session, services, tasks, engine)
    sample_table = SortableModel(SampleEquipmentModel(engine), engine)

    session.signedIn.connect(lambda: shell.set_permissions(session.permission_codes()))
    session.signedOut.connect(lambda: shell.set_permissions(()))
    people.saved.connect(lambda message: toasts.show("success", message, ""))
    for model in (
        sites, equipment, kits, stock, projects, deployments, reservations, maintenance,
        batteries,
    ):  # fmt: skip
        model.saved.connect(lambda message: toasts.show("success", message, ""))
    # Maintenance done from the asset sheet re-reads the open asset.
    maintenance.saved.connect(lambda _message: equipment.reloadAsset())
    batteries.saved.connect(lambda _message: maintenance.refresh())
    # Anything saved anywhere may raise or clear an alert.
    for changed in (people, sites, equipment, kits, stock, projects, deployments, reservations,
                    maintenance, batteries):  # fmt: skip
        changed.saved.connect(lambda _message: alerts.refreshSoon())
    # Checking out, returning and logging change equipment, stock and project views.
    for source in (projects, deployments, reservations, maintenance):
        for target in (projects, deployments, reservations, maintenance, equipment, stock):
            if target is not source:
                source.saved.connect(lambda _message, t=target: t.refresh())

    context = engine.rootContext()
    for name, value in {
        "Theme": theme,
        "Shell": shell,
        "Toasts": toasts,
        "Tasks": tasks,
        "Session": session,
        "People": people,
        "Sites": sites,
        "Equipment": equipment,
        "Kits": kits,
        "Stock": stock,
        "Projects": projects,
        "Deployments": deployments,
        "Reservations": reservations,
        "Maintenance": maintenance,
        "Batteries": batteries,
        "Alerts": alerts,
        "SampleTable": sample_table,
        "AppVersion": version,
        "AppEnvironment": environment,
        "StartMaximized": start_maximized,
    }.items():
        context.setContextProperty(name, value)

    engine.load(QUrl.fromLocalFile(str(root_qml)))
    return UiContext(
        engine,
        theme,
        shell,
        toasts,
        tasks,
        session,
        people,
        sites,
        equipment,
        kits,
        stock,
        projects,
        deployments,
        reservations,
        maintenance,
        batteries,
        alerts,
        sample_table,
    )


__all__ = ["Services", "UiContext", "create_engine"]
