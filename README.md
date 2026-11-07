# Inventory Management

Desktop application for managing drone and survey (GNSS/DGPS) equipment, batteries, GCP banner stock, pilots, surveyors, projects, reservations and maintenance.

- **Client:** Python 3.13 + PySide6 (desktop, Windows first)
- **Data:** local SQLite adapter during development → final sprint: SharePoint Lists with Microsoft sign-in (Plan A), or Supabase Pro with app-specific accounts (Plan B)
- **Roles:** Admin, Pilot (DGCA licence required), Surveyor

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design, [docs/SPRINT_PLAN.md](docs/SPRINT_PLAN.md) for the roadmap and [docs/adr/](docs/adr/) for architecture decisions.

## Development setup

Requires [uv](https://docs.astral.sh/uv/). It installs the right Python version and every dependency from the lock file.

```bash
uv sync
```

Run the app:

```bash
uv run python -m ims
```

Or double-click `run.bat`.

## Quality checks (the same ones CI runs)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest --cov
```

## Configuration

Settings come from environment variables; none are required for development.

| Variable | Default | Meaning |
|---|---|---|
| `IMS_ENVIRONMENT` | `development` | `development`, `test` or `production` |
| `IMS_BACKEND` | `sqlite` | `sqlite`, `sharepoint` or `supabase` |
| `IMS_DATA_DIR` | per-user app data folder | Where local data is stored |
| `IMS_LOG_DIR` | per-user log folder | Where `ims.log` is written |
| `IMS_LOG_LEVEL` | `INFO` | Logging level |

Secrets are never put in environment variables or files; they are kept in the Windows Credential Manager.
