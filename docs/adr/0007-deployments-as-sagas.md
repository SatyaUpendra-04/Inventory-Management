# ADR-0007: Deployments, field logs and returns as compensating sagas

- **Status:** Accepted
- **Date:** 2026-11-08

## Context
Checking equipment out to a project writes many records: one status event per item, a GCP banner issue in the stock ledger, the project becoming active and the deployment itself. A flight log writes a usage entry for the drone, every part fitted to it, each battery and the PPK base. ADR-0005 rules out multi-record transactions, so a failure part-way (most often: someone else deployed the same drone a moment earlier) must not leave half the kit deployed or half a flight logged.

## Decision
1. **The deployment record is the plan.** After the readiness check passes, the deployment is saved in state `pending` with every item, the crew and the GCP quantity. The remaining steps follow it.
2. **Every step is idempotent.** Each status event, usage entry and stock movement has an ID derived from the command ID and a purpose (`deploy:<asset>`, `gcp-issue`, `usage:<asset>:<meter>`). Shared helpers in `application/ledgers.py` return an entry already written by the same command instead of writing it again, so retrying a command that stopped part-way carries on.
3. **Refusal triggers compensation.** If a step is refused with a domain error, the steps already taken are undone newest first: items go back in store, issued banners are returned, and the deployment ends `cancelled` with the reason. The command is still recorded and audited, so the attempt is on file; the user then sees why nothing was deployed. A failure *during* compensation (storage unreachable) leaves the deployment `pending`, and a retry finishes it forward.
4. **Logs are written last.** Flight and survey logs write their usage entries first and the log record last, as the completion marker. The log keeps the `(asset, entry)` pairs it wrote, so voiding it reverses exactly those entries. Logs are never edited.
5. **Returns check everything before writing anything.** Each item's status change is validated against its current status first; only then are the changes applied. A return never improves serviceability: lifting a limitation or a grounding is a certified maintenance step.
6. **Readiness is one pure function** (`check_readiness`) that lists blockers and warnings: grounded, retired or already-out items, missing or expired documents, grounded fitted parts, overdue maintenance (Sprint 7), crew without valid DGCA certificates, a drone without a licensed pilot, incomplete kits (warning) and short GCP stock. The checkout screen shows the same list live, and the service re-runs it before writing.

## Consequences
- No storage backend needs transactions; SharePoint and Supabase adapters only have to honour the per-record rules in ADR-0005.
- A cancelled deployment leaves a visible trail (status events out and back) rather than silently disappearing.
- Reserved items that go out and are then undone come back as *in store*; Sprint 6 (reservations) restores the reservation itself.

## Alternatives considered
- **Database transactions:** not available on SharePoint (ADR-0005).
- **Checking everything first and hoping nothing changes:** two crews deploying the same drone at once would both pass the check; only the ledger's sequence rule catches the second, so compensation is still needed.
- **Editing flight logs in place:** loses the history of what was recorded; void-and-relog keeps it.
