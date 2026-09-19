# 003: No Database Until Multi-Tenancy
**Date:** 2026-09-20
**Status:** Accepted

## Context
Current MVP: single-user demo, stateless function, no persistence needed. Adding Postgres adds cost, migration complexity, connection management, and operational burden.

## Decision
Defer database until Phase 4 (Auth + Multi-Tenancy). Phase 1–3 use in-memory dict for asset registry, swap to Postgres with identical interface.

## Consequences
- **Positive:** Zero infra cost. Simpler deployment. Faster iteration on core features.
- **Negative:** Data lost on function restart. No multi-user. No history.
- **Mitigation:** Interface designed for swap. Asset registry abstracts storage.

## Alternatives Considered
- SQLite in function → ephemeral, same problem
- Vercel KV → limited query, not relational
- Supabase from start → premature optimization