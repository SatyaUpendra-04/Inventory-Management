"""Application settings.

Values come from defaults, overridden by environment variables prefixed ``IMS_``.
Secrets (tokens, passwords) never live here; they go in the OS credential store.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir
from pydantic import BaseModel, ConfigDict, Field

from ims import APP_ID


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Backend(StrEnum):
    SQLITE = "sqlite"
    SHAREPOINT = "sharepoint"
    SUPABASE = "supabase"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Environment = Environment.DEVELOPMENT
    backend: Backend = Backend.SQLITE
    data_dir: Path = Field(default_factory=lambda: Path(user_data_dir(APP_ID, appauthor=False)))
    log_dir: Path = Field(default_factory=lambda: Path(user_log_dir(APP_ID, appauthor=False)))
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Builds settings from ``IMS_*`` environment variables, falling back to defaults."""
        source = os.environ if env is None else env
        overrides: dict[str, str] = {}
        for field in cls.model_fields:
            key = f"IMS_{field.upper()}"
            if key in source:
                overrides[field] = source[key]
        return cls.model_validate(overrides)
