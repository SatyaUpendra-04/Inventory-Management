"""Navigation for the app shell: sidebar sections and the current page."""

from __future__ import annotations

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


SECTIONS: tuple[Section, ...] = (
    Section("dashboard", "Dashboard", "dashboard", "Overview", "PlaceholderPage", 9,
            "Fleet availability, alerts and utilisation at a glance."),
    Section("projects", "Projects", "briefcase", "Operations", "PlaceholderPage", 5,
            "Mining survey projects, crews and results."),
    Section("deployments", "Deployments", "send", "Operations", "PlaceholderPage", 5,
            "Equipment taken out before a project and returned after it."),
    Section("reservations", "Reservations", "calendar", "Operations", "PlaceholderPage", 6,
            "Book equipment and kits for upcoming projects."),
    Section("equipment", "Equipment", "drone", "Fleet", "PlaceholderPage", 4,
            "Drones, parts, GNSS receivers, accessories and kits."),
    Section("batteries", "Batteries", "battery", "Fleet", "PlaceholderPage", 8,
            "Cycle counts, health and retirement of every battery."),
    Section("maintenance", "Maintenance", "wrench", "Fleet", "PlaceholderPage", 7,
            "Service schedules, defects, work orders and return to service."),
    Section("stock", "GCP stock", "flag", "Fleet", "PlaceholderPage", 4,
            "GCP banner stock, issues to projects and reorder alerts."),
    Section("people", "People", "users", "Organisation", "PlaceholderPage", 3,
            "Pilots, surveyors and administrators, with licences."),
    Section("reports", "Reports", "chart", "Organisation", "PlaceholderPage", 9,
            "Pilot, project and fleet reports with exports."),
    Section("gallery", "Design gallery", "palette", "System", "GalleryPage", 0,
            "Every component in every theme, for review."),
    Section("settings", "Settings", "sliders", "System", "SettingsPage", 0,
            "Appearance, accessibility and preferences."),
)  # fmt: skip


class ShellViewModel(QObject):
    currentChanged = Signal()  # noqa: N815 (Qt signal name)

    def __init__(self, initial: str = "gallery", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._keys = [s.key for s in SECTIONS]
        self._current = initial if initial in self._keys else self._keys[0]

    def _get_sections(self) -> list[dict[str, object]]:
        return [asdict(s) for s in SECTIONS]

    def _get_current(self) -> str:
        return self._current

    def _get_current_section(self) -> dict[str, object]:
        return asdict(next(s for s in SECTIONS if s.key == self._current))

    sections = Property(list, _get_sections, constant=True)
    current = Property(str, _get_current, notify=currentChanged)
    currentSection = Property(dict, _get_current_section, notify=currentChanged)  # noqa: N815

    @Slot(str)
    def navigate(self, key: str) -> None:
        if key in self._keys and key != self._current:
            self._current = key
            self.currentChanged.emit()

    @Slot(int)
    def step(self, delta: int) -> None:
        """Moves the selection up or down the sidebar (keyboard navigation)."""
        index = self._keys.index(self._current)
        self.navigate(self._keys[max(0, min(len(self._keys) - 1, index + delta))])
