import json
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ims import main as main_module

pytestmark = pytest.mark.integration


def test_app_starts_logs_and_exits_cleanly(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("IMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMS_ENVIRONMENT", "test")
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)  # main() replaces it; restore after
    # Return immediately instead of entering the Qt event loop.
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)

    assert main_module.main([]) == 0

    lines = (tmp_path / "logs" / "ims.log").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    started = next(e for e in events if e["event"] == "app_starting")
    assert started["environment"] == "test"
    assert started["backend"] == "sqlite"
    assert any(e["event"] == "app_stopped" for e in events)
