# Inventory Management System — Sprint Plan

**Product:** Desktop inventory, airworthiness and operations system for drones, batteries, payloads and survey (GNSS/DGPS) equipment, with pilots, surveyors and mining survey projects.
**Status:** Sprint 0 · Plan dated 2026-11-08
**Cadence:** 2-week sprints (Sprint 0 is 1 week) · ~21 weeks, plus a 2-week buffer
**Architecture:** see [ARCHITECTURE.md](ARCHITECTURE.md). This is a **new, industry-grade build**. V1.2.3 is used only as a reference for business rules; its code structure is not carried over.

---

## 1. Key decisions

| Decision | Choice | Reason |
|---|---|---|
| Client | PySide6 desktop app (Windows first) | No hosting cost; works on site laptops |
| Architecture | Hexagonal (ports & adapters), domain modules, append-only ledgers, state machines | Auditable history, replaceable backend, testable rules |
| Backend — **Plan A** | SharePoint Lists via Microsoft Graph, with company Microsoft sign-in (MSAL) | Already licensed; data stays inside the company tenant; no password storage of our own |
| Backend — **Plan B** (if IT declines Plan A) | Supabase Pro (PostgreSQL, Mumbai region), with **app-specific accounts** (Supabase Auth) | No IT approval needed; about $25/month; permissions enforced on the server (Row Level Security) |
| Development & testing | Local SQLite + local app accounts; Supabase **free** tier with dummy data only | Builds every feature without waiting on IT; never puts real staff data on a free account |
| Sync model | Logging **before** and **after** a project; no live sync | Matches field workflow; keeps the app simple |
| Build order | Full app on the local adapter first, backend integration **last** | Features can be built and tested without waiting on IT |
| Backup | Admin desktop keeps local SQLite snapshots of the shared data | Read access and restore if the backend is unavailable |
| Never | Put a `.db` file inside a SharePoint/OneDrive synced folder | Sync corrupts SQLite (`-wal`/`-shm` files sync separately) |
| Never | Combine app-specific accounts with SharePoint | Would need one shared secret in every copy of the app, and still needs IT consent |

### Building for either backend before integrating it
The local adapter **must behave like the stricter backend (SharePoint)** from Sprint 1, or the final sprint becomes a rewrite:

- Business logic talks only to ports (`Repository`, `AuthProvider`, `FileStore`, `Clock`) — **no SQL outside adapters**.
- Every record carries a version/etag; a stale update raises `ConflictError`.
- **No cross-record transactions** are assumed. Multi-item operations are sequences of idempotent commands with compensation on failure.
- Lookups use indexed fields only (SharePoint slows past ~5,000 items without indexes).
- Pilots and surveyors only **append** operational records. Status and totals are **derived** from them, so non-admins never need edit rights on master data.
- One contract test suite runs against every adapter.

---

## 2. Roles & user rules

| Role | DGCA Remote Pilot Certificate | Can do |
|---|---|---|
| **Admin** (Manager/Admin, one role) | Optional | Everything: users, assets, sites, projects, approvals, maintenance sign-off, reports, backup/restore |
| **Pilot** | **Mandatory** (number + expiry) | View assets/projects, reserve, deploy and return drone equipment, log sorties, report defects, view own stats |
| **Surveyor** | Optional | View assets/projects, reserve, deploy and return survey equipment, log survey sessions, report defects, view own stats |

- **Every user:** employee ID (unique), email (unique), contact number, profile picture, full name, role.
- **Admins:** more than one allowed; the system never allows zero active admins.
- **Licence expiry:** a pilot with an expired certificate cannot be assigned drones; warnings at 60/30/7 days.

---

## 3. Sprint breakdown

### Sprint 0 — Foundation (1 week)
- Repository layout per ARCHITECTURE.md (`src/ims/...`, `tests/...`), `pyproject.toml`, `uv` lock file
- `ruff`, `mypy --strict` (domain), import-linter layer rules, `pytest`, `pytest-qt`, `hypothesis`
- GitHub Actions: lint, type-check, tests, coverage, `pip-audit`
- ADR template and the first ADRs (architecture, backend plans A/B, ID and time conventions)
- Extract V1.2.3 business rules into a written rules catalogue (reference for later sprints)
- Empty app window that launches, with logging and settings in place

**Done when:** CI is green on an empty-but-real skeleton, and the app window opens.

### Sprint 1 — Domain core & storage contract
- Ports: `Repository`, `AuthProvider`, `FileStore`, `Clock`
- Identity: users, roles, permission matrix, user rules (licence, mandatory fields, last-admin protection)
- Equipment catalogue with three tracking modes (ARCHITECTURE.md §4.0): **serialized + lifecycle** (airframe, motors, propellers, landing gear, Helix GPS antenna, camera, logger, telemetry, batteries, DGPS receivers, PPK base, controllers), **tagged equipment** (laptop, card reader, hard disk, power bank, chargers, LiPo checker, anemometer, tripod, bipod, monopod, tribrach, SD cards), **consumable stock** (GCP banners)
- Stock ledger model (receive, issue, return, consume, adjust)
- **Serviceability** and **custody** state machines with allowed transitions
- Usage ledger (hours, cycles, landings) with reversal-based corrections
- Audit log for every command; idempotent command IDs
- Local SQLite adapter (SQLAlchemy + Alembic) and the contract test suite

**Done when:** all domain rules are unit-tested (≥ 90% coverage) and the SQLite adapter passes the contract tests.

### Sprint 2 — Design system & app shell
- Switch the UI to **Qt Quick (QML)** with Python view-models (ADR-0004); replace the Sprint 0 window
- **Design tokens:** OKLCH tonal palettes, 60-30-10 proportions, semantic status colours, type scale (Inter), 4-point spacing, radii, shadows, motion durations and easing
- **Themes:** Light, Dark, System (follows Windows live), high-contrast, user-chosen accent colour with automatic contrast check; cross-fade on theme change
- **Motion:** sheets, page transitions, gliding sidebar selection, hover/press micro-interactions, animated list changes, skeleton loading, toasts; reduced-motion support
- **Component library:** buttons, text fields, selects, date picker, toggles, segmented controls, checkboxes, cards, badges/status pills, data table, sidebar, toolbar, sheets, popovers, toasts, empty states
- **App shell:** sidebar navigation, toolbar, settings page with theme and accent picker, login screen design
- Component gallery page (for review and screenshot tests)
- Quality: WCAG AA contrast tests for every theme and accent; visual regression screenshots in CI; keyboard navigation and focus rings

**Done when:** the shell and every component work in all themes, contrast tests pass, and you have approved the look and motion in a review session.

### Sprint 3 — Accounts, users & sites
- Login via `AuthProvider` (local accounts for now)
- Account management: Admin-created users, temporary password with forced change, admin reset, lockout, deactivation
- Role-based navigation; every action runs on background workers so screens never freeze
- User profiles: picture, contact, employee ID, pilot certificate number and expiry (with file upload)
- Sites / mine areas

**Done when:** an Admin can onboard Pilots and Surveyors end to end.

### Sprint 4 — Asset registry, configuration & compliance
- Asset catalogue, filters, add/edit/retire, asset detail with full history
- **Configuration:** install/remove components on drones (motors, propellers, landing gear, Helix GPS antenna, camera, logger), with time-in-service per component
- Kit templates and kits: "Drone kit" and "DGPS set" (base + rover receivers, controller, tripod, tribrach, bipod, batteries, chargers)
- Consumables: GCP banner stock per location, purchase receipts, reorder levels
- **Compliance documents** with expiry and alerts: drone UIN/registration, type certificate reference, insurance, calibration certificates
- Firmware version records
- QR-code asset labels

**Done when:** the whole fleet is registered with components, documents and expiries.

### Sprint 5 — Projects, deployments & field logs
- Projects: code, site, dates, chief pilot, surveyor, status
- **Pre-project deployment:** choose kit/assets and crew; blocked automatically if any asset is unserviceable, overdue for maintenance, out of compliance, or the pilot's certificate has expired
- **Sorties:** per-flight log (drone, battery, pilot, date, duration, cycles, landings, site)
- **Survey sessions:** which receiver acted as base and which as rover, area, points, PPK/RTK fix rate
- **GCP banners issued** to the project from stock at deployment
- **Post-project return:** per-asset condition, damage and defect reporting; GCP banners returned vs consumed; SD cards linked to the flights they carried
- Multi-item deployment with compensation on partial failure

**Done when:** a full project cycle works and every hour and cycle lands in the usage ledger.

### Sprint 6 — Reservations
- Reserve assets/kits for a date range against a project
- Conflict detection: overlaps with reservations, deployments, planned maintenance and expiring documents
- Admin approval / rejection
- Calendar views by asset and by project
- Convert an approved reservation into a deployment
- Reserve GCP banner quantities; warn if planned projects would push stock below the reorder level
- Stock count (stocktake) with variance report

**Done when:** double-booking is impossible, reservations flow into deployments, and GCP stock never runs out unnoticed.

### Sprint 7 — Airworthiness & maintenance
- Maintenance programme per asset model: tasks due by hours, cycles or calendar, whichever comes first, with tolerances
- Due and overdue list; overdue tasks ground the asset automatically
- **Defects:** report → assess (ground immediately or defer with a limitation) → rectify
- Work orders: open → in progress → awaiting parts → completed → **return to service** (Admin sign-off)
- Life-limited components tracked through the configuration history

**Done when:** no asset can be deployed with an overdue task or open grounding defect.

### Sprint 8 — Battery lifecycle & survey equipment
- Separate lifecycle for every battery: drone flight batteries, DGPS receiver batteries, controller batteries
- Battery cycle ledger, health %, optional internal resistance / cell imbalance / swelling checks; compatible chargers per battery family
- Storage-charge reminders for idle batteries; retirement at cycle or health limits
- **Servicing never resets cycles or health** (fixes the V1.2.3 bug)
- GNSS calibration and verification records (method, reference point or lab, result, certificate, valid-until)
- Alert centre combining maintenance, battery, calibration, document and licence alerts

**Done when:** every battery and survey instrument has a complete, accurate lifecycle record.

### Sprint 9 — Stats, reports & forecasting
- Pilot stats: hours by month/fiscal year, sorties, drone models, certificate status
- Surveyor stats: projects, area surveyed, fix rates
- Project stats: equipment used, hours, area, images, quality, GCP banners consumed
- GCP stock forecast: when stock runs out at the current survey rate
- Fleet dashboard: utilisation, availability, alerts
- **Predictive maintenance v1:** "task due in ~N days" from actual usage rate; battery degradation trend; risk score per asset
- Excel and PDF exports

**Done when:** management reports come from the app, not spreadsheets.

### Sprint 10 — Backend integration & release (final)
The plan is chosen by IT's answer before Sprint 10 starts.

**Plan A — SharePoint**
- IMS SharePoint site, groups (IMS Admins / IMS Members) and list provisioning script with indexes
- Microsoft sign-in (MSAL), roles mapped from the IMS Users list
- **SharePoint adapter**; contract tests pass against it

**Plan B — Supabase Pro**
- Tables, migrations, Row Level Security rules per role, storage bucket for pictures and certificates
- App-specific accounts on Supabase Auth: admin-created users, email password reset
- **Supabase adapter**; contract tests pass against it

**Both plans**
- Offline command queue with replay
- One-time migration of local data to the chosen backend
- Admin backup: scheduled snapshot to local SQLite, browse offline, tested restore
- Code-signed Windows installer, update check, user guide, UAT with real pilots and surveyors

**Done when:** all users run the installed app against the chosen backend, and a restore from backup has been tested.

> **Risk:** Sprint 10 carries the most unknowns (IT permissions, Graph throttling, list limits). The 2-week buffer is reserved for it.
> **Mitigation (recommended):** once IT answers, spend half a day reading and writing one record against the chosen backend. That confirms access early without changing the build order.

---

## 4. Backend options for Sprint 10

| | **Plan A — SharePoint** | **Plan B — Supabase Pro** |
|---|---|---|
| Data store | SharePoint Lists in the company tenant | PostgreSQL (Mumbai region) |
| Accounts | Company Microsoft accounts | App-specific accounts (Supabase Auth) |
| Permissions enforced by | SharePoint groups and list permissions | Row Level Security rules per role |
| Change history | SharePoint version history + app audit log | App audit log |
| Running cost | ₹0 (existing licences) | about $25/month (≈ ₹2,200) |
| Needs IT | Yes (see below) | No |
| Later benefit | Data never leaves Microsoft 365 | A web or mobile app can reuse the same backend |

### Plan A prerequisites from IT
- Entra ID app registration: public client (desktop), redirect URI `http://localhost`
- Delegated Graph permissions: `User.Read`, `Sites.Selected` (write access granted on the IMS site only)
- SharePoint site **IMS** with groups **IMS Admins** (Full Control) and **IMS Members** (Contribute)

### Plan B prerequisites
- Supabase Pro project in the Mumbai region, owned by a company email account
- Manager approval for about $25/month

---

## 5. Definition of Done (every sprint)
- Features work in the running app, not just in tests
- CI green: lint, types, tests, coverage gates, layer rules, dependency audit
- Every data change writes an audit entry
- Database changes only through migrations
- Sprint demo, changelog entry, and an ADR for any architecture change

## 6. Timeline

| Sprint | Weeks | Focus |
|---|---|---|
| 0 | 1 | Foundation ✅ |
| 1 | 2 | Domain core & storage contract |
| 2 | 2 | Design system & app shell |
| 3 | 2 | Accounts, users, sites |
| 4 | 2 | Asset registry, configuration, compliance |
| 5 | 2 | Projects, deployments, field logs |
| 6 | 2 | Reservations |
| 7 | 2 | Airworthiness & maintenance |
| 8 | 2 | Battery lifecycle & survey equipment |
| 9 | 2 | Stats, reports, forecasting |
| 10 | 2 (+2 buffer) | Backend integration & release |
| **Total** | **~21–23 weeks** | |
