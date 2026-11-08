"""Short, non-blocking notifications shown in the top-right corner."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

KINDS = frozenset({"success", "warning", "danger", "info"})


class ToastService(QObject):
    posted = Signal(str, str, str)  # kind, title, message

    @Slot(str, str, str)
    def show(self, kind: str, title: str, message: str = "") -> None:
        self.posted.emit(kind if kind in KINDS else "info", title, message)
