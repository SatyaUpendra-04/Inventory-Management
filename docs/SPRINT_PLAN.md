# Inventory Management System — Sprint Plan

**Product:** Desktop inventory & operations system for drone and survey (DGPS) equipment, pilots, surveyors and mining survey projects.
**Status:** Sprint 0 · Plan dated 2026-11-08
**Cadence:** 2-week sprints (Sprint 0 is 1 week) · ~19 weeks total
**Baseline:** V1.2.3 (PySide6 + SQLite) — its service layer, audit ledger, migrations and tests are ported, not rewritten.

---

## 1. Key decisions

| Decision | Choice | Reason |
|---|---|---|
| Client | PySide6 desktop app (Windows first) | Reuses V1.2.3 UI and logic; no hosting cost |
| Backend — **Plan A** | SharePoint Lists via Microsoft Graph, with company Microsoft sign-in (MSAL) | Already licensed; data stays inside the company tenant; no password storage of our own |
| Backend — **Plan B** (if IT declines Plan A) | Supabase Pro (PostgreSQL, Mumbai region), with **app-specific accounts** (Supabase Auth) | No IT approval needed; about $25/month; permissions enforced on the server (Row Level Security) |
| Development & testing | Local SQLite + local app accounts; Supabase **free** tier with dummy data only | Builds every feature without waiting on IT; never puts real staff data on a free account |
| Sync model | Logging **before** and **after** a project; no live sync | Matches field workflow; keeps the app simple |
| Build order | Full app on a **local SQLite adapter first**, SharePoint integration **last** | Features can be built and tested without waiting on IT |
| Backup | Admin desktop keeps local SQLite snapshots of the SharePoint data | Read access and restore if SharePoint is unavailable |
| Never | Put a `.db` file inside a SharePoint/OneDrive synced folder | Sync corrupts SQLite (`-wal`/`-shm` files sync separately) |

### Building for either backend before integrating it
Integration is the last sprint and the backend is not yet final, so from Sprint 1 the local adapter **must behave like the stricter of the two (SharePoint)**, or the final sprint becomes a rewrite:

- Services talk only to a `Repository` interface — **no SQL in services or UI**.
- Login goes through an `AuthProvider` interface with three implementations: local (development), Microsoft/MSAL (Plan A) and Supabase Auth (Plan B). Screens never know which one is active.
- Every record carries an `etag`/version; updates fail with `ConflictError` if the record changed since it was read (mirrors SharePoint optimistic concurrency).
- **No cross-record transactions** are assumed. Multi-item operations (e.g. a 5-item checkout) are written as a sequence with compensation (undo on failure).
- Lookups are by indexed fields only (SharePoint slows past ~5,000 items without indexes).
- Pilots and surveyors only **add** records (checkouts, returns, reservations, flight logs). Asset status is **derived** from those records, so non-admins never need edit rights on master lists.
- One shared contract test suite runs against every adapter (SQLite now, SharePoint in Sprint 8).

---

## 2. Roles & user rules

| Role | DGCA licence | Can do |
|---|---|---|
| **Admin** (Manager/Admin, one role) | Optional | Everything: users, assets, locations, projects, approvals, maintenance, reports, backup/restore |
| **Pilot** | **Mandatory** (number + expiry) | View assets/projects, reserve, check out / return drones & batteries, log flights, view own stats |
| **Surveyor** | Optional | View assets/projects, reserve, check out / return DGPS equipment, log survey data, view own stats |

**Every user:** employee ID (unique), email (unique), contact number, profile picture, full name, role.
**Admins:** more than one allowed; the system must never be left with zero active admins.
**Licence expiry:** a pilot with an expired DGCA licence cannot check out drones; warnings at 60/30/7 days.

---

## 3. Sprint breakdown

### Sprint 0 — Foundation (1 week)
- Git repo, `.gitignore`, README, this plan
- Python project layout (`src/`, `tests/`), `pyproject.toml`, pinned dependencies, virtualenv
- pytest + ruff; GitHub Actions running tests on every push
- Import V1.2.3 as the baseline; remove the 22 PySide6 fallback stub classes
- Architecture note: layers (UI → services → repository → adapter)

**Done when:** the baseline app launches, the existing tests pass locally and in CI.

### Sprint 1 — Domain model & storage contract
- Unified **Asset** model (Drone, Battery, DGPS rover/base, Payload, Accessory) replacing separate drone/DGPS tables
- **Kit** entity (named group of assets checked out together)
- `Repository` interface + **local SQLite adapter** with etag/version and SharePoint-like constraints
- Contract test suite for the repository
- Domain rules: role rules, DGCA requirement, mandatory user fields, last-admin protection
- Port audit log and asset event history

**Done when:** all domain rules are covered by tests, with no SQL outside the adapter.

### Sprint 2 — App shell, users & locations
- Login through `AuthProvider` (local accounts for now; Microsoft sign-in or Supabase Auth in Sprint 8)
- App accounts: Admin creates users (no self sign-up), temporary password with forced change on first login, admin password reset, lockout after failed attempts, deactivation
- Main window, navigation, role-based menus
- User management: create/edit/deactivate, profile picture, DGCA licence number + expiry, employee ID, contact
- Own-profile screen
- Locations / mine sites CRUD

**Done when:** an Admin can onboard Pilots and Surveyors end to end.

### Sprint 3 — Assets & kits
- Asset catalog with filters (type, status, location, kit)
- Add/edit/retire assets; serial number uniqueness
- Kit builder
- Asset detail page with full event history
- Status derived from transactions (Available / Reserved / In-Field / Maintenance / Calibration Due / Retired)
- Printable asset labels with QR code (serial + ID)

**Done when:** the whole equipment register can be maintained in the app.

### Sprint 4 — Projects & deployments (before / after logging)
- Projects: code, mine site, dates, chief pilot, surveyor, status
- **Pre-project checkout:** pick kit/assets, pilot/surveyor, expected return; licence and availability checks
- **Post-project check-in:** per-asset hours, battery cycles, return condition, notes, damage flag
- Flight log entries per pilot; survey log per surveyor (area, images, PPK fix rate)
- Multi-item checkout with compensation on partial failure

**Done when:** a full project cycle (checkout → field → return) works and updates stats.

### Sprint 5 — Reservations
- Reserve assets/kits for a date range against a project
- Conflict detection (overlap with reservations, active checkouts, maintenance)
- Admin approval / rejection
- Reservation calendar view (by asset and by project)
- Convert an approved reservation into a checkout

**Done when:** double-booking is prevented and reservations flow into checkouts.

### Sprint 6 — Maintenance & battery lifecycle
- Maintenance work orders (open → in progress → done), service types, performed by, parts/notes
- Service schedules by flight hours, cycles or calendar
- **Battery lifecycle:** per-battery cycle log, health %, optional internal resistance / swelling checks, retirement — **cycles are never reset by servicing** (fixes the V1.2.3 bug)
- DGPS calibration records with certificate attachment and validity dates
- Alerts: service due, calibration due, battery end-of-life, licence expiry

**Done when:** every asset has a complete, accurate service and lifecycle history.

### Sprint 7 — Stats, reports & forecasting
- Pilot stats: hours by month/fiscal year, flights, aircraft flown, licence status
- Surveyor stats: projects, area surveyed, PPK fix rates
- Project stats: equipment used, hours, area, images, quality
- Fleet dashboard: utilisation, availability, alerts
- **Predictive maintenance v1:** "service due in ~N days" from actual usage rate; battery degradation trend; risk score per asset
- Excel and PDF export

**Done when:** management reports come from the app, not spreadsheets.

### Sprint 8 — Backend integration & release (final)
The plan is chosen by IT's answer before Sprint 8 starts.

**Plan A — SharePoint**
- IMS SharePoint site, groups (IMS Admins / IMS Members) and list provisioning script
- Microsoft sign-in (MSAL), roles mapped from the IMS Users list
- **SharePoint adapter** for the repository; contract tests pass against it

**Plan B — Supabase Pro**
- Database tables and migrations, Row Level Security rules per role, storage bucket for pictures and certificates
- App-specific accounts on Supabase Auth: admin-created users, email password reset
- **Supabase adapter** for the repository; contract tests pass against it

**Both plans**
- Offline queue for entries made without connectivity
- One-time migration of local data to the chosen backend
- Admin backup: scheduled snapshot to local SQLite, browse offline, restore
- Windows installer, user guide, UAT with real pilots/surveyors

**Done when:** all users run the installed app against the chosen backend, and a restore from backup has been tested.

> **Risk:** Sprint 8 carries the most unknowns (IT permissions, Graph throttling, list limits). If it overruns, it splits into 8a (adapter + sign-in) and 8b (backup, installer, UAT), adding 2 weeks.
> **Mitigation (recommended):** once IT approves, spend half a day in Sprint 1 or 2 on a throwaway test that reads and writes one list item through Graph. That confirms access early without changing the build order.

---

## 4. Backend options for Sprint 8

| | **Plan A — SharePoint** | **Plan B — Supabase Pro** |
|---|---|---|
| Data store | SharePoint Lists in the company tenant | PostgreSQL (Mumbai region) |
| Accounts | Company Microsoft accounts | App-specific accounts (Supabase Auth) |
| Permissions enforced by | SharePoint groups and list permissions | Row Level Security rules per role |
| Change history | SharePoint version history + app audit log | App audit log |
| Running cost | ₹0 (existing licences) | about $25/month (≈ ₹2,200) |
| Needs IT | Yes (see below) | No |
| Later benefit | Data never leaves Microsoft 365 | A web or mobile app can reuse the same backend |

The contract test suite from Sprint 1 keeps the switch cheap: whichever adapter is built must pass it. App-specific accounts are **not** combined with SharePoint, because that would need one shared secret embedded in every copy of the app and would still need IT consent.

### Plan A prerequisites from IT (needed by Sprint 8)
- Entra ID app registration: public client (desktop), redirect URI `http://localhost`
- Delegated Graph permissions: `User.Read`, `Sites.Selected` (write access granted on the IMS site only)
- SharePoint site **IMS** with groups **IMS Admins** (Full Control) and **IMS Members** (Contribute)

### Plan B prerequisites
- Supabase Pro project in the Mumbai region, owned by a company email account
- Manager approval for about $25/month

## 5. Definition of Done (every sprint)
- Features work in the running app, not just in tests
- Unit and contract tests pass in CI
- Every data change writes an audit entry
- No SQL outside the storage adapter
- Sprint demo plus a short changelog entry

## 6. Timeline

| Sprint | Weeks | Focus |
|---|---|---|
| 0 | 1 | Foundation |
| 1 | 2 | Domain model & storage contract |
| 2 | 2 | App shell, users, locations |
| 3 | 2 | Assets & kits |
| 4 | 2 | Projects & deployments |
| 5 | 2 | Reservations |
| 6 | 2 | Maintenance & battery lifecycle |
| 7 | 2 | Stats, reports, forecasting |
| 8 | 2 (+2 buffer) | SharePoint integration & release |
| **Total** | **~17–19 weeks** | |
