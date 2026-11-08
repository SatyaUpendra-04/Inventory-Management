# Architecture

This document defines how the Inventory Management System is built. "Drone" here means an unmanned aircraft system (UAS); no manned aircraft are in scope. V1.2.3 is used as a **reference for business rules only**; the structure below replaces it. Changes to anything here are recorded as an Architecture Decision Record (ADR) in `docs/adr/`.

---

## 1. Principles

1. **The domain is the product.** Drone airworthiness, component life, battery health and calibration validity are modelled explicitly, the way aviation maintenance (MRO) and asset-management (ISO 55000) systems do, not as free-text fields.
2. **History is never overwritten.** Usage, status changes and corrections are append-only records. Current values (total hours, cycles, status) are calculated from history, so they can always be audited and rebuilt.
3. **The backend is replaceable.** Business logic depends on interfaces (ports), never on SQLite, SharePoint or Supabase directly (hexagonal / ports-and-adapters architecture).
4. **Security is enforced by the backend, not the app.** Checks in the desktop app are for user experience only; the real permission boundary is SharePoint permissions (Plan A) or Row Level Security (Plan B).
5. **Works with bad connectivity.** Every write is an idempotent command with its own ID, so it can be queued offline and safely retried.
6. **Everything is tested and automated.** No feature is done until it is covered by tests that run in CI.

**Honest constraint:** a large enterprise would normally run a central server and database. A desktop app over SharePoint or Supabase is the right trade-off at this scale and budget, and principle 3 keeps the path to a server or web app open without a rewrite.

---

## 2. Layers

```
┌──────────────────────────────────────────────┐
│ UI (PySide6)  views · view-models · widgets  │  no business rules, no storage calls
├──────────────────────────────────────────────┤
│ Application   commands · queries · use cases │  permissions, orchestration, idempotency
├──────────────────────────────────────────────┤
│ Domain        entities · rules · state       │  pure Python, no I/O, fully unit-tested
│               machines · domain events       │
├──────────────────────────────────────────────┤
│ Ports         Repository · AuthProvider ·    │  interfaces only
│               FileStore · Clock · Notifier   │
├──────────────────────────────────────────────┤
│ Adapters      SQLite (dev) · SharePoint (A)  │  swappable; all pass one contract-test suite
│               · Supabase (B) · local files   │
└──────────────────────────────────────────────┘
```

Dependencies point **downwards only**. The domain imports nothing from the other layers. An import-linter check in CI enforces this.

---

## 3. Domain modules (bounded contexts)

| Module | Responsibility |
|---|---|
| **Identity & Access** | Users, roles (Admin, Pilot, Surveyor), permissions, licences on the person |
| **Asset Registry** | Every trackable item in the equipment catalogue (section 4.0): drones and their parts, batteries, survey equipment and accessories. Serial numbers or asset tags, make/model, acquisition, documents |
| **Consumables & Stock** | Quantity-tracked items, above all **GCP banners**: stock per location, issue to projects, return, consumption, reorder alerts |
| **Configuration** | Which components are installed on which drone or kit, and when. Install/remove history per serial number |
| **Operations** | Projects, sites, reservations, deployments (checkout/return), sorties (individual flights), survey sessions |
| **Airworthiness & Maintenance** | Maintenance programme (tasks due by hours, cycles or calendar, whichever comes first), work orders, defects, grounding, return to service |
| **Compliance** | Expiring documents and certificates: pilot licence, drone registration/UIN, insurance, calibration certificates, with alerts |
| **Reporting & Forecasting** | Utilisation, pilot/project stats, maintenance forecasts, battery degradation, exports |
| **Audit** | Immutable log of every command: who, what, when, before/after |

---

## 4. Core domain design

### 4.0 Equipment catalogue and tracking modes
Not every item needs the same tracking. Each **item type** is assigned one of three modes. Admins can add new item types later without code changes.

| Mode | What is tracked | Item types |
|---|---|---|
| **Serialized + lifecycle** | Individual unit by serial number; custody, serviceability, usage meters (hours/cycles), maintenance, full history | **Drone:** airframe, motors, propellers (sets), landing gear (legs), Helix GPS antenna, camera/payload, logger, telemetry radio · **Batteries:** drone flight batteries, DGPS receiver batteries, controller batteries · **GNSS:** DGPS receivers (e.g. Trimble R12) used as base or rover, drone PPK base, controllers |
| **Tagged equipment** | Individual unit by asset tag (QR label), plus serial number where the item has one; custody, condition, optional warranty and calibration dates; no usage meters | **Drone kit:** laptop, card reader, hard disk, power bank, drone battery charger, LiPo checker, anemometer · **Survey kit:** tripod, bipod, monopod, tribrach, battery chargers, controller chargers · **Data media:** SD cards, hard disks · cases and other accessories |
| **Consumable stock** | Quantity per location; every movement is a stock ledger entry | **GCP banners** (most important), plus any other consumables added later |

Notes:
- **Base vs rover** is a *role* a DGPS receiver plays on a project, not a different item. The same R12 can be a base on one survey and a rover on the next, and its history shows both.
- **PPK base** is a GNSS receiver like the DGPS units, so it shares their calibration, firmware and base/rover-role handling.
- **SD cards and hard disks** are data media, tagged individually so each one can be traced to the project and flights whose data it carried.
- **Laptops** carry warranty dates; the **anemometer** can carry a calibration date. Both are optional fields on tagged equipment, so any item type can use them.
- **Power banks** are tagged equipment with purchase date and condition checks (swelling, damage), not full battery lifecycle tracking. This can be upgraded per item type later.
- **Kit templates** describe a standard set, e.g. "Drone kit" (airframe + batteries + telemetry + PPK base + laptop + SD cards + card reader + hard disk + chargers + LiPo checker + anemometer + power bank) or "DGPS set" (base receiver + rover receiver + controller + tripod + tribrach + bipod + batteries + chargers). Deploying a kit checks that every item is present and serviceable.

### 4.1 Two independent status dimensions
Industry systems separate **"can it be used?"** from **"where is it?"**. Mixing them, as V1.2.3 does with one `status` field, loses information (for example, a drone that is in the field *and* has a defect reported).

| Serviceability | Custody |
|---|---|
| Serviceable | In store |
| Serviceable with limitation (deferred defect) | Reserved |
| Unserviceable / Grounded | Deployed (on a project) |
| Retired / Scrapped | In maintenance · In transit · Disposed |

Each dimension is a **state machine** with allowed transitions only. Every transition records who made it, when and why. Example: an asset cannot be deployed unless it is Serviceable, In store, has no overdue maintenance task and has valid compliance documents.

### 4.2 Usage ledger
- Each sortie or return records usage entries: `(asset, hours, cycles, landings, date, source, recorded_by)`.
- Totals are the sum of entries. Corrections are **reversal entries**, never edits.
- Component time-in-service comes from the configuration history: a motor accumulates hours only while it is installed on a drone.

### 4.3 Maintenance programme
- Task definitions per asset model: interval in hours, cycles and/or calendar days ("whichever comes first"), plus a tolerance.
- Due items are calculated, not stored. Overdue items block deployment automatically.
- Work orders: open → in progress → awaiting parts → completed → certified (return to service, by an Admin).
- **Defect reporting:** any user can report a defect after a flight; severity decides whether the asset is grounded immediately or the defect is deferred with a limitation.

### 4.4 Battery lifecycle
Batteries are their own lifecycle module, separate from the drone or receiver they power, because a battery moves between drones and kits and must keep its own history.
- Battery families: drone flight batteries (cycles from sorties), DGPS receiver batteries and controller batteries (charge cycles or age-based health).
- Per-battery cycle ledger, health %, optional internal resistance, cell imbalance and physical checks (swelling, damage).
- Compatible chargers recorded per battery family.
- Storage-charge reminders for batteries idle longer than a set period.
- Retirement at a cycle limit or health threshold. **Servicing never resets cycles or health.**

### 4.5 Survey equipment
- Calibration and verification records (date, method, reference control point or lab, result, certificate file, valid-until).
- Firmware version history for receivers and drones.
- An expired calibration blocks deployment.

### 4.5a Consumables and GCP banners
- Stock ledger per item type and location: **received** (purchase), **issued** (to a project), **returned**, **consumed / lost / damaged**, **adjusted** (stock count). On-hand quantity is the sum of entries, never edited directly.
- A deployment issues banners to a project; the post-project return records how many came back, so consumption per survey is known exactly.
- Reorder level per location, with an alert when stock falls below it; usage per project feeds a forecast of when stock will run out.
- Periodic stock count with variance report.

### 4.6 Compliance (India)
Tracked as documents with expiry dates and alerts. **These must be verified against the current DGCA Drone Rules before Sprint 4 (asset registry & compliance):**
- Remote Pilot Certificate (RPC) for every pilot, mandatory, with expiry
- Drone Unique Identification Number (UIN) and type certificate reference
- Third-party insurance per drone
- Calibration certificates for survey equipment

---

## 5. Data conventions

- **IDs:** UUIDv7, generated by the client. They are safe for offline creation and for merging, and they sort by time. A separate human-friendly **asset tag** is printed on labels and QR codes.
- **Time:** stored in UTC (ISO 8601), displayed in the user's local time. One `Clock` port, so tests can freeze time.
- **Units:** hours stored as decimal hours; cycles and landings as integers; area in hectares.
- **Concurrency:** every record has a `version`/etag; a stale update raises `ConflictError` and the user is asked to reload.
- **Soft delete** for master data (assets, users, sites); ledgers are never deleted.
- **Money and quantities:** `Decimal`, never float.

---

## 6. Security

- Role-based permissions defined as data (role → permission codes), checked in the application layer **and** enforced by the backend.
- Least privilege: Pilots and Surveyors only *append* operational records; master data is Admin-only.
- Local development accounts use Argon2 password hashing; in production, passwords are handled by Microsoft (Plan A) or Supabase Auth (Plan B), never by the app.
- Tokens and secrets are kept in the operating system's credential store (Windows Credential Manager via `keyring`), never in files or code.
- Personal data is kept to what is needed (India DPDP Act); contact details are visible only to Admins.
- A dependency vulnerability scan (`pip-audit`) runs in CI.

---

## 7. Desktop application & design system

The UI is a first-class requirement: top-notch, theme-adjustable, with macOS-inspired motion and colour-theory-accurate proportions. "Inspired" means the feel (calm surfaces, depth, fluid spring motion), never Apple's assets, fonts, icons or branding. See ADR-0004.

### 7.1 UI technology
- **Qt Quick (QML)** for all screens, driven by Python view-models (`QObject` properties, signals and slots). Qt Quick renders on the GPU and has declarative animations, which Qt Widgets cannot match for fluid motion.
- Tables and lists use Python `QAbstractItemModel` subclasses shown in Qt Quick `TableView`/`ListView`, so thousands of rows stay smooth.
- The Sprint 0 Qt Widgets window is replaced by a Qt Quick window in Sprint 2 (design system).

### 7.2 Design tokens
Every visual value comes from one token set; no colour, size or duration is hard-coded in a screen.

| Token group | Definition |
|---|---|
| **Colour** | Tonal palettes generated in the **OKLCH** colour space, so every step has an even, perceptually accurate change in lightness. Each palette has 12 steps (background → solid → text). |
| **Proportion** | **60-30-10:** about 60% neutral surfaces, 30% secondary surfaces and content, 10% accent (primary actions, selection, focus). Accent never fills large areas. |
| **Semantic status** | Serviceable (green), limitation / due soon (amber), grounded / overdue (red), information (blue), retired (neutral). Same meaning in every theme, and **never colour alone**: always with an icon and a label, for colour-blind users. |
| **Typography** | Segoe UI Variable (Windows 11's interface font) with Segoe UI and Inter as fallbacks (ADR-0004 amendment 1); modular type scale (ratio 1.2); tabular figures for numbers in tables. |
| **Spacing & shape** | 4-point grid (4, 8, 12, 16, 24, 32, 48); corner radii 6 / 10 / 14; soft layered shadows for elevation. |
| **Motion** | Durations 120 ms (micro), 220 ms (standard), 350 ms (page/sheet); spring-style easing (fast start, gentle settle) instead of linear movement. |

### 7.3 Themes
- **Light, Dark and System** (follows the Windows setting live), plus a **user-chosen accent colour**: the full accent palette is generated in OKLCH from that one colour and checked for contrast before it is accepted.
- **High-contrast** variant for bright outdoor/site use.
- Theme changes cross-fade instead of flashing; the choice is saved per user.

### 7.4 Motion (macOS-inspired)
- **Sheets:** dialogs slide down from the window's title area over a dimmed background, like macOS sheets, and slide back on close.
- **Page transitions:** short slide + fade between sections; the sidebar selection highlight glides to the new item.
- **Micro-interactions:** hover lift, press scale (≈ 0.97), smooth focus rings, toggle and segmented-control slides.
- **Lists:** inserted and removed rows animate height and opacity; loading shows a skeleton shimmer instead of a spinner where possible.
- **Toasts** slide in from the top-right and stack.
- **Reduced motion:** when Windows "Animation effects" is off, movement becomes simple fades with no travel.
- Translucent, blurred sidebar ("vibrancy") is emulated subtly where the GPU allows, with a solid fallback.

### 7.5 Accessibility & quality
- **WCAG 2.2 AA contrast:** 4.5:1 for text, 3:1 for icons and control borders, **checked by automated tests for every theme and accent**.
- Full keyboard navigation with visible focus; text scaling from 100% to 150% without broken layouts; screen-reader names on every control.
- **Screenshot tests:** key screens are rendered off-screen in light, dark and high-contrast; CI fails on blank renders or any QML warning and uploads the images for review (ADR-0004 amendment 4).
- Icons: our own consistent outline SVG set (1.75 px rounded strokes), tinted by theme tokens through an image provider.

### 7.6 Application behaviour
- **Pattern:** QML views + Python view-models (MVVM); view-models hold state and call the application layer, never storage.
- **No frozen screens:** all storage and network calls run on background workers; the UI shows progress and errors.
- **Offline queue:** commands wait in a local queue with their IDs and are replayed when online; duplicates are ignored by ID.
- **Errors:** user-friendly messages; full details go to a rotating log file with a "copy diagnostics" button.
- **Distribution:** Windows installer, code-signed, with an in-app update check.

---

## 8. Technology

| Concern | Choice |
|---|---|
| Language | Python 3.13 (pinned) |
| UI | PySide6 (Qt 6) with **Qt Quick / QML** views and Python view-models |
| Design system | Design tokens, OKLCH palette generator, Segoe UI Variable, own SVG icon set |
| Domain models & validation | Pydantic v2 |
| Local adapter | SQLAlchemy 2 + Alembic migrations on SQLite |
| Plan A adapter | Microsoft Graph (`msal`, `httpx`) |
| Plan B adapter | Supabase (`supabase-py` / `httpx`), Row Level Security |
| Environment & packaging | `uv`, `pyproject.toml`, lock file |
| Code quality | `ruff` (lint + format), `mypy --strict` on the domain, import-linter |
| Tests | `pytest`, `pytest-qt`, `hypothesis` (property tests for ledgers and state machines), contract tests per adapter, contrast tests per theme, visual regression screenshots |
| CI | GitHub Actions: lint, type-check, tests, coverage report, `pip-audit` |
| Installer | PyInstaller + Inno Setup |
| Logging | `structlog`, JSON lines, rotating files |

---

## 9. Quality gates (every pull request)

- Lint, format and type-check pass
- Domain test coverage ≥ 90%; overall ≥ 75%
- Contract tests pass for every implemented adapter
- No layer-boundary violations
- Contrast checks pass for every theme; visual regression screenshots match or are re-approved
- Database changes go through a migration, never by hand
- Every user-visible change has a changelog entry; releases use semantic versioning

---

## 10. Repository layout

```
src/ims/
  domain/          identity/ assets/ configuration/ operations/ maintenance/ compliance/ audit/
  application/     commands, queries, permissions, offline queue
  ports/           repository.py, auth.py, files.py, clock.py
  adapters/        sqlite/ sharepoint/ supabase/
  ui/              qml/ (components, shell, pages) viewmodels/ models/ theme/ (colour, palette, tokens, manager, icons) assets/icons/
  main.py
tests/
  unit/  contract/  integration/  ui/
docs/
  ARCHITECTURE.md  SPRINT_PLAN.md  adr/
```
