# ADR-0008: Reservations book items in a per-item ledger

- **Status:** Accepted
- **Date:** 2026-11-12

## Context
Sprint 6 must make double-booking impossible: the same drone cannot be promised to two projects for overlapping days. A simple "check for overlaps, then save the reservation" fails without transactions (ADR-0005): two administrators approving overlapping requests at the same moment would both pass the check and both save. Reservations also need to coexist with the custody state machine (ARCHITECTURE §4.1), which describes where an item is *now*, not where it is promised next month.

## Decision
1. **Reservations are calendar bookings, not a custody change.** A request names a project, a date range, kits (expanded to their members), extra items and GCP banners. It does not move items to *Reserved*; equipment stays usable until the booking starts.
2. **Approval writes to a per-item booking ledger.** Each item has an append-only `booking_events` stream (`booked` / `released`, with the reservation and dates), sequenced like the status ledger. Before appending, the service replays the stream and refuses an overlapping booking for another reservation. The sequence rule then guarantees that, of two approvals racing for the same item, only one entry can take the next number; the other is refused.
3. **Approval is all or nothing.** Items are booked one by one with IDs derived from the command. If one is refused, the ones already booked by this command are released and the request stays *waiting*, with the reason shown.
4. **Bookings block other projects at check-out.** The deployment readiness check blocks an item booked for another project on the check-out date. A check-out started from a reservation records `reservation_id`; once the deployment is out, the bookings are released and the reservation becomes *fulfilled* (forward-only; a retry finishes it). If the check-out is undone (ADR-0007), the reservation stays approved and its bookings stay in place.
5. **Conflicts are blockers or warnings.** Blockers: another booking overlaps, the item is retired, the dates are in the past or reversed. Warnings: competing requests, items out with another project, grounded or limited items, in maintenance, documents missing or expiring before the job ends, planned maintenance (Sprint 7), incomplete kits, and GCP banners that would fall to or below the reorder level (or run short) once every live booking from that store is counted.
6. **Administrators' own requests are booked immediately**; crew requests wait for an administrator, who can approve or reject (with a reason). The requester or an administrator can cancel, which releases the bookings.
7. **Stocktake** counts several stores in one command. Expected stock is computed from the ledger *excluding* this command's own adjustments, so a retried stocktake reports and records exactly the same variances.

## Consequences
- SharePoint and Supabase adapters need one more sequenced list/table with a unique `(asset_id, sequence)` key; no transactions.
- Booking history is auditable per item: who booked or released it, for which project and dates.
- Bookings for GCP banners are forecasts, not stock movements; stock moves only when banners are issued at check-out.

## Alternatives considered
- **Move items to custody *Reserved* on approval:** blocks the item for unrelated work until the booking starts, and cannot represent two future bookings for different weeks.
- **Check-then-save on the reservation record alone:** loses races between concurrent approvals.
- **A single global lock record:** a hotspot that serialises every approval, and still needs compensation if the holder crashes.
