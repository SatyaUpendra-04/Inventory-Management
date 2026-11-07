# ADR-0005: Safe commands without multi-record transactions

- **Status:** Accepted
- **Date:** 2026-11-08

## Context
Neither SharePoint Lists nor a REST API like Supabase's offers transactions that span several records. Field users work on unreliable connections, so a command can fail halfway and be retried, sometimes from an offline queue hours later. Two people can also edit the same asset's history at the same moment.

## Decision
1. **Command IDs.** Every user action carries a UUIDv7 command ID. A finished command is written to a command log; running the same ID again returns the stored result without doing anything.
2. **Derived record IDs.** Records a command creates get IDs derived from the command ID (`uuid5(command_id, purpose)`). A retry after a crash writes the same IDs, gets `AlreadyExists` for the parts that already succeeded, and completes the rest.
3. **Optimistic concurrency on records.** Every mutable record carries a `version`; storage accepts an update only if the stored version is exactly one lower.
4. **Sequenced ledgers.** Status events, usage entries and stock movements carry a per-stream `sequence` (per asset, or per item type for stock). Storage accepts an entry only if it is the next number, so two simultaneous writers cannot both succeed; the loser is asked to reload.
5. **One audit entry per command**, also with a derived ID, written before the command is marked complete.

## Consequences
- Retrying any command is always safe, which is what the offline queue (Sprint 10) needs.
- Concurrent edits are detected and never silently overwrite each other.
- Each adapter must enforce unique `(stream, sequence)` pairs. SQLite uses a unique constraint; SharePoint will use an indexed unique key column; Supabase will use a unique constraint.
- Ledger writes for one asset or item type are serialised, which is fine at this scale.

## Alternatives considered
- **Database transactions:** not available on SharePoint, and would tie the design to one backend.
- **Last-write-wins:** simpler, but silently loses one person's change.
- **Random IDs per attempt:** retries would create duplicate records.
