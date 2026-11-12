# ADR-0010: Battery lifecycle, calibration records and the alert centre

- **Status:** Accepted
- **Date:** 2026-11-12

## Context
V1.2.3 reset a battery's cycles to 0 and health to 100% when it was serviced (rules catalogue M4), so a worn pack looked new after a repair. Batteries move between drones, receivers and kits and must keep their own history. GNSS receivers need calibration and field verification records, not just a certificate. And alerts were scattered across pages; the toolbar bell was a placeholder.

## Decision
1. **Cycles come from the usage ledger**, the same one flights and survey sessions already write. Charge cycles for receiver and controller batteries are logged with a new usage source, `charge`. There is no operation that resets a meter; corrections are reversals (ADR-0003).
2. **Battery checks are an append-only ledger per battery**: measured health %, internal resistance, cell imbalance, swelling, damage, and whether the pack was left at storage charge. Servicing adds a check; it never edits history. Health is the latest measured value. With none, the V1.2.3 formula (100 − cycles ÷ limit × 35) is shown, marked as an estimate, and **never grounds** a battery on its own.
3. **Limits per kind of battery** (cycle limit, minimum health, idle days before a storage-charge reminder) are editable records, installed with starting values.
4. **Battery and calibration problems are grounding reasons** (ADR-0009): cycle limit reached, measured health below the limit, swelling or damage, or a failed last calibration/verification. So check-out blocks them, the sweep and the log or check that causes them ground the item, and **returning an item to service is refused while any grounding reason remains**, including from the status buttons on the item sheet.
5. **Calibration and verification records** are an append-only ledger per receiver. A passing calibration also files the certificate as the item's calibration *document* in the same command, so expiry stays in one place (Sprint 4 compliance). Field verifications record horizontal and vertical differences against a control point and can be entered by the crew; calibrations by administrators.
6. **The alert centre is calculated, not stored.** It combines maintenance, defects, batteries, calibration, documents, pilot certificates, GCP stock and reservations waiting for approval, filtered by what the person may act on, most urgent first. The toolbar bell shows the count of urgent and warning alerts and refreshes shortly after any save.

## Consequences
- No battery can look newer than it is; history is complete for every pack.
- Three more tables for the Plan A/B adapters: battery limits (one per battery kind, unique), battery checks and calibration records (both sequenced per item).
- Alerts cost a fleet-wide calculation; fine at this scale, and cacheable later if needed.

## Alternatives considered
- **A cycles counter on the battery record:** editable, and exactly what allowed the V1.2.3 reset bug.
- **Grounding on estimated health:** the formula is a rough guide; grounding on it would retire healthy packs. Only measured health grounds.
- **Separate calibration certificates and records:** two places to keep in step; filing the certificate from the record keeps one source of truth for expiry.
