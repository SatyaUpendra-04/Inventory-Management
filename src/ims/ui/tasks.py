"""Background task queue: storage work runs off the UI thread, results come back on it.

One worker thread runs tasks in submission order, so storage calls never overlap and the
screen never freezes. Callbacks always run on the UI thread.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)

log = structlog.get_logger(__name__)

Callback = Callable[[Any], None]


class TaskQueue(QObject):
    busyChanged = Signal()  # noqa: N815 (Qt signal name)
    _finished = Signal(object, object, bool)  # callback, value, failed

    def __init__(self, parent: QObject | None = None, *, synchronous: bool = False) -> None:
        super().__init__(parent)
        self._synchronous = synchronous
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._pending = 0
        self._finished.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def _get_busy(self) -> bool:
        return self._pending > 0

    busy = Property(bool, _get_busy, notify=busyChanged)

    def submit(
        self,
        work: Callable[[], Any],
        on_done: Callback | None = None,
        on_error: Callback | None = None,
    ) -> None:
        self._pending += 1
        if self._pending == 1:
            self.busyChanged.emit()
        if self._synchronous:
            try:
                value = work()
            except Exception as exc:  # delivered to on_error, like the threaded path
                self._deliver(on_error, exc, True)
            else:
                self._deliver(on_done, value, False)
            return

        finished = self._finished

        class _Job(QRunnable):
            def run(self) -> None:
                try:
                    value = work()
                except Exception as exc:
                    finished.emit(on_error, exc, True)
                else:
                    finished.emit(on_done, value, False)

        self._pool.start(_Job())

    @Slot(object, object, bool)
    def _deliver(self, callback: Callback | None, value: Any, failed: bool) -> None:
        self._pending -= 1
        if self._pending == 0:
            self.busyChanged.emit()
        if callback is not None:
            callback(value)
        elif failed:
            log.error("background_task_failed", error=repr(value))

    def wait_until_idle(self, timeout_ms: int = 5000) -> None:
        """For tests: waits for queued work and delivers its results."""
        self._pool.waitForDone(timeout_ms)
        for _ in range(50):
            QCoreApplication.processEvents()
            if self._pending == 0:
                return
