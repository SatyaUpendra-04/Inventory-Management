"""Navigation for the app shell: sidebar sections (filtered by role) and the current page."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from PySide6.QtCore import Property, QObject, Signal, Slot


@dataclass(frozen=True, slots=True)
class Section:
    key: str
    title: str
    icon: str
    group: str
    page: str  # QML page file in qml/pages
    sprint: int  # sprint that delivers the real page (0 = available now)
    summary: str
    permission: str = ""  # needed to see the section ("" = everyone signed in)
    in_sidebar: bool = True
    dev_only: bool = False  # hidden in production builds


SECTIONS: tuple[Section, ...] = (
    Section("dashboard", "Dashboard", "dashboard", "Overview", "PlaceholderPage", 9,
            "Fleet availability, alerts and utilisation at a glance."),
    Section("projects", "Projects", "briefcase", "Operations", "ProjectsPage", 0,
            "Mining survey projects, crews, flights and survey results.",
            permission="project.view"),
    Section("deployments", "Deployments", "send", "Operations", "DeploymentsPage", 0,
            "Equipment taken out before a project and returned after it.",
            permission="project.view"),
    Section("reservations", "Reservations", "calendar", "Operations", "ReservationsPage", 0,
            "Book equipment, kits and GCP banners for upcoming projects.",
            permission="project.view"),
    Section("equipment", "Equipment", "drone", "Fleet", "EquipmentPage", 0,
            "Drones, parts, GNSS receivers, accessories and kits.", permission="asset.view"),
    Section("batteries", "Batteries", "battery", "Fleet", "PlaceholderPage", 8,
            "Cycle counts, health and retirement of every battery."),
    Section("maintenance", "Maintenance", "wrench", "Fleet", "MaintenancePage", 0,
            "What is due, defects, work orders, return to service and the programme.",
            permission="asset.view"),
    Section("stock", "GCP stock", "flag", "Fleet", "StockPage", 0,
            "GCP banner stock at each site, with reorder alerts.", permission="stock.view"),
    Section("people", "People", "users", "Organisation", "PeoplePage", 0,
            "Pilots, surveyors and administrators, with licences and accounts.",
            permission="user.manage"),
    Section("sites", "Sites", "map-pin", "Organisation", "SitesPage", 0,
            "Stores, mine sites, workshops and offices.", permission="site.view"),
    Section("reports", "Reports", "chart", "Organisation", "PlaceholderPage", 9,
            "Pilot, project and fleet reports with exports."),
    Section("gallery", "Design gallery", "palette", "System", "GalleryPage", 0,
            "Every component in every theme, for review.", dev_only=True),
    Section("settings", "Settings", "sliders", "System", "SettingsPage", 0,
            "Appearance, accessibility and preferences."),
    Section("profile", "My profile", "user", "System", "ProfilePage", 0,
            "Your picture, contact details, licence and password.", in_sidebar=False),
)  # fmt: skip


class ShellViewModel(QObject):
    currentChanged = Signal()  # noqa: N815 (Qt signal name)
    sectionsChanged = Signal()  # noqa: N815

    def __init__(
        self, initial: str = "dashboard", *, production: bool = False, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._initial = initial
        self._production = production
        self._permissions: frozenset[str] = frozenset()
        self._available: list[Section] = []
        self._recompute()
        self._current = self._pick(initial)

    # ------------------------------------------------------------------ helpers

    def _recompute(self) -> None:
        self._available = [
            s
            for s in SECTIONS
            if (not s.permission or s.permission in self._permissions)
            and not (s.dev_only and self._production)
        ]

    def _keys(self) -> list[str]:
        return [s.key for s in self._available]

    def _sidebar(self) -> list[Section]:
        return [s for s in self._available if s.in_sidebar]

    def _pick(self, key: str) -> str:
        keys = self._keys()
        return key if key in keys else keys[0]

    # ------------------------------------------------------------------ properties

    def _get_sections(self) -> list[dict[str, object]]:
        return [asdict(s) for s in self._sidebar()]

    def _get_current(self) -> str:
        return self._current

    def _get_current_section(self) -> dict[str, object]:
        return asdict(next(s for s in self._available if s.key == self._current))

    sections = Property(list, _get_sections, notify=sectionsChanged)
    current = Property(str, _get_current, notify=currentChanged)
    currentSection = Property(dict, _get_current_section, notify=currentChanged)  # noqa: N815

    # ------------------------------------------------------------------ slots

    def set_permissions(self, permissions: Iterable[str]) -> None:
        """Shows only the sections the signed-in person may use; returns to the start page."""
        self._permissions = frozenset(permissions)
        self._recompute()
        self.sectionsChanged.emit()
        self._current = self._pick(self._initial)
        self.currentChanged.emit()

    @Slot(str)
    def navigate(self, key: str) -> None:
        if key in self._keys() and key != self._current:
            self._current = key
            self.currentChanged.emit()

    @Slot(int)
    def step(self, delta: int) -> None:
        """Moves the selection up or down the sidebar (keyboard navigation)."""
        keys = [s.key for s in self._sidebar()]
        if self._current not in keys:
            self.navigate(keys[0])
            return
        index = keys.index(self._current)
        self.navigate(keys[max(0, min(len(keys) - 1, index + delta))])
