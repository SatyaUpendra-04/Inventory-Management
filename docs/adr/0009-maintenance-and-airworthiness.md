# ADR-0009: Maintenance programme, automatic grounding and return to service

- **Status:** Accepted
- **Date:** 2026-11-12

## Context
Sprint 7 must guarantee that no item goes out with an overdue task or an open grounding defect. Usage already lands in the per-asset usage ledger (Sprint 5), parts already accrue hours only while fitted (Sprint 4), and check-out already has a readiness check (ADR-0007). What is missing is the programme, the due calculation, defects, work orders and the sign-off.

## Decision
1. **Programme per item type.** A task repeats every so many hours, cycles, landings and/or days, *whichever comes first*, with a tolerance per measure. A **life limit** is a separate kind of task: it never resets, has no tolerance, and is met only by replacing the part (it cannot be "completed"). A starting programme is installed once and every value is editable; the values must be checked against the manufacturers' manuals.
2. **Due status is calculated, never stored.** From the usage totals, the latest *completion* of the task on that asset (an append-only, per-asset sequenced ledger), and the later of acquisition and the task coming into force. States: OK, due soon (last 10% of an interval, or the last week), due (past the interval, inside the tolerance: still usable), overdue (past the tolerance, or at a life limit).
3. **Grounding reasons are one function** (`grounding_reasons`): overdue tasks, life limits reached, open grounding defects, and deferrals that have run out. Check-out blocks on them (and on the same reasons for parts fitted to an airframe); reservations warn about maintenance falling due inside the booking.
4. **Automatic grounding.** A flight or survey log that takes an item past a limit grounds it in the same command. Calendar tasks and deferrals run out as days pass, so an idempotent sweep (`ground_overdue`) runs when an administrator signs in or opens the Maintenance page. Grounding is an ordinary status event with the reason, so it is audited and undone only by return to service.
5. **Defects** are reported by anyone (unsafe ones ground the item at once), assessed by an administrator (ground, defer with a limitation until a date, or not a defect), and closed only by a completed work order. Equipment returned damaged or with a defect files a defect automatically.
6. **Work orders**: open (takes the item into maintenance) → in progress ⇄ awaiting parts → completed (records each task as done at today's readings and closes its defects) → certified. **Certification** (maintenance.certify, administrators) is the return to service. It is refused while any grounding reason remains, and returns the item as *limited* if a deferred defect is still open. One open work order per item.
7. **Numbers** (DEF-0001, WO-0001) are unique in storage; a clash between two simultaneous writers is a `ConflictError` and the retry takes the next number.

## Consequences
- The guarantee "nothing overdue goes out" holds even before the sweep runs, because check-out evaluates the reasons itself.
- Two new versioned tables (defects, work orders), one programme table and one sequenced ledger (completions) for the Plan A/B adapters.
- Battery-specific rules (cycle limits, health, storage charge) are Sprint 8 and plug into the same programme and grounding reasons.

## Alternatives considered
- **Storing a "next due" date per asset:** goes stale with every flight and needs a writer to keep it right; calculating is cheap at this fleet size.
- **A background scheduler for grounding:** a desktop app has no always-on process; the check at check-out plus the sweep on sign-in covers it without one.
