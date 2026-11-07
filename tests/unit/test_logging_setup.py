import json
import logging
import sys
from pathlib import Path

import structlog

from ims.logging_setup import configure_logging, log_uncaught_exception, shutdown_logging


def _read_events(log_path: Path) -> list[dict[str, object]]:
    shutdown_logging()  # flush and release the file
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def test_writes_json_lines_with_timestamp_and_level(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path / "logs")
    structlog.get_logger("test").info("asset_registered", asset_tag="DR-0001")

    events = _read_events(log_path)
    event = next(e for e in events if e["event"] == "asset_registered")
    assert event["asset_tag"] == "DR-0001"
    assert event["level"] == "info"
    assert str(event["timestamp"]).endswith("Z")


def test_stdlib_loggers_are_captured(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path)
    logging.getLogger("third.party").warning("plain stdlib message")

    events = _read_events(log_path)
    assert any(e["event"] == "plain stdlib message" for e in events)


def test_respects_log_level(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path, level="WARNING")
    structlog.get_logger("test").info("too_quiet")
    structlog.get_logger("test").warning("loud_enough")

    names = [e["event"] for e in _read_events(log_path)]
    assert "loud_enough" in names
    assert "too_quiet" not in names


def test_uncaught_exceptions_are_logged_with_traceback(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        assert exc_type is not None and exc_value is not None
        log_uncaught_exception(exc_type, exc_value, exc_tb)

    event = next(e for e in _read_events(log_path) if e["event"] == "uncaught_exception")
    assert event["level"] == "critical"
    assert "RuntimeError: boom" in str(event["exception"])
