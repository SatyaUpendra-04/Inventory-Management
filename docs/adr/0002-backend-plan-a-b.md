# ADR-0002: Backend Plan A (SharePoint) and Plan B (Supabase Pro), integrated last

- **Status:** Accepted
- **Date:** 2026-11-08

## Context
Users need one shared data store. The company already licenses Microsoft 365, and keeping data in the tenant is preferred, but SharePoint access needs IT approval. A SQLite file placed in a SharePoint/OneDrive synced folder corrupts, because its `-wal`/`-shm` files sync independently.

## Decision
- **Plan A:** SharePoint Lists via Microsoft Graph, with company Microsoft sign-in (MSAL, delegated `Sites.Selected`).
- **Plan B (if IT declines):** Supabase Pro (PostgreSQL, Mumbai region) with app-specific accounts on Supabase Auth and Row Level Security.
- Development runs on a local SQLite adapter with local accounts. Backend integration is the final sprint.
- The local adapter mimics the stricter backend (SharePoint): per-record versions, no cross-record transactions, indexed lookups only.
- App-specific accounts are never combined with SharePoint.

## Consequences
- All features can be built and tested before IT answers.
- Multi-item operations are written as idempotent command sequences with compensation, which is more work than a single SQL transaction.
- One contract test suite must pass against every adapter.

## Alternatives considered
- **SQLite file in SharePoint:** rejected, corrupts under sync.
- **App accounts + SharePoint via a shared service identity:** rejected, embeds a site-wide secret in every client and still needs IT consent.
- **AWS (RDS + own API):** rejected in favour of Supabase, which needs no custom API service and costs less.
