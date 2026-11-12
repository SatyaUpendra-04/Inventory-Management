# Changelog

All notable changes are recorded here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — Sprint 8 (Battery lifecycle & survey equipment)
- **Batteries** page: every drone, receiver and controller battery with cycles against its limit (bar), health (measured, or estimated and labelled so), last check and condition (OK, storage charge due, near cycle limit, retire, unsafe); search and a *Need attention* filter
- **Battery sheet:** record a check (health %, internal resistance, cell imbalance, swelling, damage, left at storage charge), log charge cycles for receiver and controller batteries, the full check history and **cycle ledger**, and the compatible chargers
- **Limits** per kind of battery (cycle limit, minimum health, storage-charge reminder), editable; starting values 200 / 70% / 14 days for drone packs and 500 / 70% / 30 days for receiver and controller batteries
- **Servicing never resets cycles or health** (fixes V1.2.3 rule M4)
- A battery at its cycle limit, below its measured health limit, or with swelling or damage is **grounded automatically** and cannot be checked out
- **GNSS calibration and verification** on the item sheet: method, lab or control point, result, horizontal and vertical differences, valid-until and certificate. A calibration files the certificate as the item's calibration document; a failed result grounds the receiver until a later record passes
- **Alert centre** behind the toolbar bell: maintenance, defects, batteries, calibration, documents, pilot certificates, GCP stock and reservations waiting for approval, most urgent first; the bell shows how many need attention
- Database migration 0007 (battery limits, battery checks, calibration records)
- ADR-0010

### Fixed — Sprint 8
- The item sheet's *Return to service* button could return an item that maintenance, a defect, a battery limit or a failed calibration still grounds; it is now refused with the reasons

### Added — Sprint 7 (Airworthiness & maintenance)
- **Maintenance programme** per kind of equipment: tasks due by hours, cycles, landings and/or days, whichever comes first, with tolerances; **life limits** for parts that are replaced, never reset. A starting programme is installed (drone 50 h / 90-day inspection and annual service, motor bearing check and 600 h life limit, propeller 100 h life limit, landing gear every 300 landings, GNSS receivers and PPK base every 180 days) and every task can be edited or added to
- **Maintenance** page: *Due* (overdue, due within tolerance, due soon, across the fleet), *Defects*, *Work orders* and *Programme*
- **Automatic grounding:** a flight or survey that takes an item past a limit grounds it straight away; calendar tasks and expired deferrals are grounded when an administrator signs in or opens Maintenance
- **Check-out is blocked** by any overdue task, reached life limit, open grounding defect or expired deferral, on the item or on any part fitted to it; reservations warn about maintenance falling due during the booking
- **Defects:** anyone can report one from the item's sheet (unsafe ones ground it at once); administrators assess: ground, defer with a limitation until a date, or not a defect. Equipment returned damaged or with a defect files a defect automatically
- **Work orders:** open (the item goes into maintenance) → in progress ⇄ waiting for parts → work done → **sign-off returns it to service** (administrators). Sign-off is refused while anything still grounds the item
- Item sheet: a **Maintenance** section with each task's state, open defects, *Report defect*, *Record done* (for maintenance done before or outside the app) and the open work order
- Database migration 0006 (programme, maintenance records, defects, work orders)
- ADR-0009

### Added — Sprint 6 (Reservations)
- **Reservations** page: requests waiting for approval, what is booked, and a four-week **calendar** by equipment or by project (booked, requested and out-on-a-project bars; this week, previous and next week)
- **Reserve equipment** for a project's dates: kits (every member is booked), extra equipment and GCP banners, with a live check of everything that clashes: another booking (blocks), retired items (blocks), competing requests, equipment out with another project, grounded or limited items, items in maintenance, documents missing or expiring before the job ends, incomplete kits, and GCP banners that would fall to the reorder level or run short
- **Approval:** crew requests wait for an administrator, who approves (books every item) or rejects with a reason; an administrator's own booking is confirmed straight away; the requester or an administrator can cancel
- **Double-booking is impossible:** each item has its own booking ledger; of two approvals racing for the same item only one can win, and the other books nothing (ADR-0008)
- **Check out now** from an approved reservation: project, kits, equipment and GCP banners are filled in; the reservation is marked checked out and its bookings released. Other projects' bookings block a check-out on those days
- Project sheet lists the project's reservations, with **Reserve equipment**
- **GCP stock:** *Booked* and *Free* columns; a store whose bookings take it to or below its reorder level is flagged
- **Stocktake:** count every store at once and see the variance report (records, counted, difference); differences are logged as adjustments
- Database migration 0005 (reservations, booking ledger, the reservation a deployment fulfils)
- ADR-0008

### Added — Sprint 5 (Projects, deployments & field logs)
- **Projects** page: survey jobs with site, client, dates, chief pilot (must hold a valid DGCA certificate) and lead surveyor; suggested codes such as PRJ-KJR-2611; open / completed / cancelled filters; complete, cancel, reopen and remove
- **Check out equipment** to a project: choose kits (every member goes), extra equipment, crew and GCP banners. A live readiness check lists everything that stops it: grounded or retired items, items already out or in maintenance, missing or expired UIN, insurance or calibration, grounded parts fitted to a drone, a drone without a licensed pilot, pilots with expired certificates, too few GCP banners. Incomplete kits and certificates about to expire are warnings
- **Safe multi-item check-out:** if any step is refused part-way (for example someone else took the same drone a moment earlier), everything already done is undone and nothing is left half-deployed (ADR-0007)
- **Flight logs:** drone, pilot, date, minutes, landings, cycles, batteries, PPK base and the SD cards that carried the data. Hours, landings and cycles go onto the drone and every part fitted to it; each battery gets a cycle
- **Survey sessions:** RTK, PPK or static; which receiver was the base and which were rovers; controller, batteries, area, points and fix rate. Receivers gain the session hours
- **Cancelling a wrong log** (administrators) reverses exactly the usage it added
- **Return equipment:** each item OK, usable with a defect (marked limited) or damaged (grounded and sent to maintenance); GCP banners brought back to a chosen store, the rest recorded as used on site
- **Deployments** page: what is out now, and the history of check-outs
- **Your projects** for pilots and surveyors: *Assigned* (open projects where you are chief pilot, lead surveyor, in a crew that took equipment out, or on a log; active first) and *Completed*, with counts, your role and your own flights and survey time; *Your part* on the project sheet
- Project totals: flights and flight time, survey sessions and time, area, points, GCP banners issued, returned and used
- Database migration 0004 (projects, deployments, sorties, survey sessions)
- ADR-0007

### Changed — Sprint 5
- **Date picker:** click the month title to pick a month, click again to pick a year (12 at a time); arrows step by month, year or 12 years to match; Page Up / Page Down (Shift for a year); new Today and Clear buttons
- The app opens maximised to fill the screen; **F11** switches to true full screen and back
- Usage on the equipment list shows hours to two decimals ("0.75 h", not "0.8 h") and "1 cycle" in the singular
- Long sheets reserve their scroll-bar space without a layout feedback loop

### Added — Sprint 4 (Asset registry, configuration & compliance)
- **Equipment** page: every asset with condition, location, usage and document status; search, category filter and a "needs attention" filter
- **Register and edit assets** with the next free tag suggested (DRN-0001, R12 receivers, tripods ...), home site, warranty and opening flight hours, cycles and landings for second-hand equipment
- **Asset sheet:** ground, mark limited, return to service, send to maintenance, retire and dispose (each offered only when the rules and your role allow it, with a reason where needed); full status history
- **Configuration:** fit and remove motors, propellers, landing gear, Helix antenna, camera, logger and telemetry on drone airframes, with each part keeping its own install history
- **Compliance documents:** UIN (Digital Sky), type certificate, third-party insurance, calibration certificates and others, with scans, issue and expiry dates; missing, expiring (30 days) and expired documents are flagged on the list and the sheet. Only the document kinds that apply to an item are offered
- **Firmware** version records per asset
- **Kits:** Drone kit and DGPS set templates; build kits, add and remove equipment, see exactly what is missing, break a kit up
- **GCP stock** page: banners on hand per site, receive deliveries, write off, stock counts that log the difference as an adjustment, reorder levels with alerts, recent movements
- **QR asset labels:** 21-up A4 label sheets (63.5 × 38.1 mm) as PDF, with a start position for part-used sheets
- Database migration 0003 (configuration, documents, firmware, kits, reorder levels)

### Changed — Sprint 4
- Times on screen are shown in local time (they are stored in UTC)
- Status pills fall back to the neutral style for unknown states instead of drawing nothing

### Added — Sprint 3 (Accounts, users & sites)
- **First-run setup** for the first administrator, with a live password checklist
- **Sign-in** against local accounts: Argon2id password hashes, identical messages for unknown users and wrong passwords, escalating lockout stored with the account (1 → 30 minutes), sign-ins audited
- **Temporary passwords** issued by administrators (shown once, with Copy), forced change at first sign-in, admin reset and unlock
- **Profile pictures** required before first use (cropped to a square, shown as round avatars); **DGCA certificate copies** (PDF, PNG, JPEG) attached to licences; licence expiry shown as valid / expiring / expired
- **People** page (admin only): search, role filter, add, edit, reset password, unlock, deactivate/reactivate, remove
- **Sites** page: stores, mine sites, workshops and offices with coordinates, area, mineral and status; a site holding stock cannot be removed
- **My profile** page: picture, contact number, licence copy, password change, sign out; account menu on the sidebar profile chip
- **Role-based navigation:** People only for administrators; Design gallery hidden in production builds
- **Background task queue** so storage work never freezes the screen
- Database migration 0002 (sites, local credentials, licence document)
- ADR-0006

### Changed
- Toasts appear bottom-right so they never cover page actions; stacked toasts no longer get stuck half-faded
- Lists use button padding so row content is inset correctly
- Sidebar focus ring now appears only for keyboard navigation, drawn inside the highlight so it is never clipped

### Fixed
- App would not start on Windows without a time-zone database (added `tzdata`)
- Picture saving failed because PySide's type stubs disagree with its runtime (found by the walk-through)
- Lockout could crash after ~45 consecutive failures (overflow; found by a property test)
- The database connection was left open when the app closed

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
