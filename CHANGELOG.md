# Changelog

All notable changes are recorded here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — Sprint 2 (Design system & app shell)
- **Qt Quick UI** replacing the Sprint 0 widgets window; Python view-models behind every screen
- **Colour engine:** OKLCH conversion, gamut mapping and WCAG contrast maths; 12-step palettes whose text and border steps are forced to meet AA contrast
- **Themes:** Light, Dark and Automatic (follows Windows live), Increase contrast, ten accent presets plus any custom colour (nudged for readability when needed); choices are saved; theme changes cross-fade
- **Motion:** sheets that drop from the top, page transitions, sidebar selection that glides on a spring, hover lift and press sink, animated list changes, skeleton shimmer, toasts; Reduce motion setting and Windows "Animation effects" respected
- **Components:** text, icon, button, icon button, text field (with password reveal and errors), select, date picker, toggle, checkbox, segmented control, card (3 elevations), status pill, badge, data table (sortable), sheet, popover, toasts, empty state, skeleton
- **App shell:** grouped sidebar, toolbar with search and quick theme switch, Settings page, sign-in screen design, design gallery, placeholders naming the sprint for each upcoming section; Ctrl+, and Ctrl+Shift+L shortcuts
- **Icons:** 45 outline SVG icons, tinted per theme
- **Tests:** WCAG AA checks for every preset theme and random custom accents, palette evenness, icon rendering, theme persistence, QML loading with zero warnings on every page in every theme, keyboard navigation, screenshots uploaded by CI

### Changed
- `run.bat` checks and repairs the app environment before launching
- Disabled buttons use a neutral fill instead of fading the colour, so they stay legible
- ADR-0004 amended: Segoe UI Variable font, own icon set, accent nudging, screenshot review instead of pixel baselines

### Fixed
- Focus ring could fall just below 3:1 contrast on cards with very dark custom accents (found by property tests)

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
