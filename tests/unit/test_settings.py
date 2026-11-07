from pathlib import Path

import pytest
from pydantic import ValidationError

from ims.settings import Backend, Environment, Settings


def test_defaults_are_development_on_sqlite() -> None:
    settings = Settings.from_env({})
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.backend is Backend.SQLITE
    assert settings.log_level == "INFO"
    assert settings.data_dir.name  # resolved to a real per-user folder


def test_environment_variables_override_defaults(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "IMS_ENVIRONMENT": "production",
            "IMS_BACKEND": "supabase",
            "IMS_DATA_DIR": str(tmp_path / "data"),
            "IMS_LOG_LEVEL": "DEBUG",
            "UNRELATED": "ignored",
        }
    )
    assert settings.environment is Environment.PRODUCTION
    assert settings.backend is Backend.SUPABASE
    assert settings.data_dir == tmp_path / "data"
    assert settings.log_level == "DEBUG"


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings.from_env({"IMS_BACKEND": "excel"})


def test_settings_are_immutable() -> None:
    settings = Settings.from_env({})
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"  # type: ignore[misc]
