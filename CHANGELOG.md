# Changelog

All notable changes are recorded here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — Sprint 1 (Domain core & storage contract)
- **Identity:** Admin / Pilot / Surveyor roles and permission matrix; user field rules (employee ID, email, phone, mandatory DGCA licence for Pilots); last-admin protection; password policy
- **Equipment catalogue:** 29 default item types in three tracking modes (serialized with meters, tagged, consumable stock), including drone parts, batteries, GNSS equipment, field electronics, survey accessories and GCP banners
- **Assets:** registration with asset tags and serial numbers, item-type rules, opening meter balances
- **Status:** separate serviceability and custody state machines; status kept as an append-only event history; role-based permissions per transition
- **Usage ledger:** hours, cycles and landings; corrections only by exact reversal; totals never negative
- **Stock ledger:** GCP banner receipts, issues, returns, consumption, write-offs and adjustments; store and project balances never negative
- **Application layer:** permission-checked commands that are safe to retry, with one audit entry each (ADR-0005)
- **Storage:** port interfaces, an in-memory reference adapter and a SQLite adapter (SQLAlchemy + Alembic migrations, verified backup before upgrades)
- **Tests:** 225 tests, including property-based tests and a storage contract suite run against every adapter; domain coverage 99%

### Changed
- CI actions updated to their Node 24 releases; CI now also enforces 90% domain coverage
- `AuthProvider` and `FileStore` ports moved from Sprint 1 to Sprint 3, where they are first used

### Added — Sprint 0 (Foundation)
- Project layout following the architecture layers (`domain`, `application`, `ports`, `adapters`, `ui`)
- Python 3.13 environment managed by `uv` with a lock file
- Settings from `IMS_*` environment variables; per-user data and log folders
- Structured JSON logging to a rotating file; crashes are logged with tracebacks
- Main application window shell
- Quality gates: ruff (lint + format), mypy strict, import-linter layer rules, pytest with coverage
- GitHub Actions CI on Windows, plus a dependency vulnerability audit
- Architecture Decision Records 0001–0003 and the V1.2.3 business rules catalogue
