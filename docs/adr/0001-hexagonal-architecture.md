# ADR-0001: Hexagonal architecture with enforced layers

- **Status:** Accepted
- **Date:** 2026-11-08

## Context
V1.2.3 mixed SQL, permissions and business rules in one 1,600-line service class, with UI code calling it directly. The final backend (SharePoint or Supabase) is not decided and is integrated last, so business logic must not depend on any storage technology.

## Decision
- Four layers: **UI → application → ports → domain**, with adapters implementing ports.
- The domain is pure Python: no I/O, no Qt, no storage or logging libraries.
- Only the composition root (`ims.main`) may import adapters.
- These rules are enforced in CI by import-linter (`[tool.importlinter]` in `pyproject.toml`); a violation fails the build.

## Consequences
- Business rules are unit-tested without a database or a screen.
- Swapping SQLite for SharePoint or Supabase touches only an adapter and the composition root.
- More files and interfaces than a "just call the database" design; that cost is accepted.

## Alternatives considered
- **Keep the V1.2.3 service-class structure:** fastest to start, but ties every rule to SQLite and makes the backend switch a rewrite.
- **Full microservices / server:** right for a large enterprise, unnecessary for a desktop app at this scale.
