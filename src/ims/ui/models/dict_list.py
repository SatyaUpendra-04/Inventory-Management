"""A list model whose rows are plain dicts, with one QML role per key."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)


class DictListModel(QAbstractListModel):
    def __init__(self, roles: Sequence[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._roles = {Qt.ItemDataRole.UserRole + i: name for i, name in enumerate(roles)}

    def reset(self, rows: list[dict[str, Any]]) -> None:
        missing = {name for row in rows for name in self._roles.values() if name not in row}
        if missing:
            raise KeyError(f"rows are missing roles: {sorted(missing)}")
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> Any:
        if not index.isValid() or role not in self._roles:
            return None
        return self._rows[index.row()][self._roles[role]]

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {role: QByteArray(name.encode()) for role, name in self._roles.items()}

    def find(self, key: str, value: Any) -> dict[str, Any]:
        """The first row whose ``key`` equals ``value``, or an empty dict."""
        return next((dict(r) for r in self._rows if r.get(key) == value), {})
