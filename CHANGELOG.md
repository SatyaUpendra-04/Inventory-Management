# Changelog

All notable changes are recorded here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — Sprint 0 (Foundation)
- Project layout following the architecture layers (`domain`, `application`, `ports`, `adapters`, `ui`)
- Python 3.13 environment managed by `uv` with a lock file
- Settings from `IMS_*` environment variables; per-user data and log folders
- Structured JSON logging to a rotating file; crashes are logged with tracebacks
- Main application window shell
- Quality gates: ruff (lint + format), mypy strict, import-linter layer rules, pytest with coverage
- GitHub Actions CI on Windows, plus a dependency vulnerability audit
- Architecture Decision Records 0001–0003 and the V1.2.3 business rules catalogue
