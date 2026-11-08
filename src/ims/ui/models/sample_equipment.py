"""Made-up equipment rows for the design gallery's data table (no real data)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Slot,
)

COLUMNS = ("Asset tag", "Item", "Serial number", "Status", "Location", "Hours")
STATUS_COLUMN = 3
NUMERIC_COLUMN = 5
StatusRole = Qt.ItemDataRole.UserRole + 1
SortRole = Qt.ItemDataRole.UserRole + 2
KindRole = Qt.ItemDataRole.UserRole + 3

_ROWS: tuple[tuple[str, str, str, tuple[str, str], str, float], ...] = (
    ("DRN-0001", "Drone airframe", "X8-22-0017", ("success", "Serviceable"), "Main store", 412.5),
    ("DRN-0002", "Drone airframe", "X8-22-0031", ("warning", "Service due soon"), "Site A", 388.0),
    ("DRN-0003", "Drone airframe", "X8-23-0102", ("danger", "Grounded"), "Workshop", 129.2),
    ("BAT-0114", "Drone flight battery", "LB-6S-4410", ("success", "Serviceable"), "Main store", 0),
    ("BAT-0121", "Drone flight battery", "LB-6S-4418", ("warning", "Limited"), "Site A", 0),
    ("GNS-0004", "DGPS receiver", "R12-6033", ("info", "Calibration in 21 days"), "Site B", 1310.4),
    ("PPK-0002", "PPK base station", "PB-0920", ("success", "Serviceable"), "Main store", 802.0),
    ("CTL-0006", "Survey controller", "TSC7-1188", ("neutral", "Retired"), "Archive", 0),
    ("TRP-0012", "Tripod", "", ("success", "In store"), "Main store", 0),
    ("LAP-0003", "Laptop", "5CD2-77AX", ("success", "Serviceable"), "Site A", 0),
)


class SampleEquipmentModel(QAbstractTableModel):
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(_ROWS)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(COLUMNS)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> Any:
        if not index.isValid():
            return None
        row = _ROWS[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == STATUS_COLUMN:
                return row[3][1]
            if column == NUMERIC_COLUMN:
                return f"{row[5]:,.1f}" if row[5] else "—"
            return row[column] or "—"
        if role == StatusRole:
            return row[3][0] if column == STATUS_COLUMN else ""
        if role == SortRole:
            if column == STATUS_COLUMN:
                return row[3][1]
            return row[column]
        if role == KindRole:
            if column == STATUS_COLUMN:
                return "status"
            return "number" if column == NUMERIC_COLUMN else "text"
        return None

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        names = dict(super().roleNames())
        names[StatusRole] = QByteArray(b"status")
        names[KindRole] = QByteArray(b"kind")
        return names


class SortableModel(QSortFilterProxyModel):
    """Proxy that QML can sort by clicking column headers."""

    def __init__(self, source: QAbstractTableModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setSourceModel(source)
        self.setSortRole(SortRole)

    @Slot(int, bool)
    def sortBy(self, column: int, descending: bool) -> None:  # noqa: N802
        order = Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder
        self.sort(column, order)
