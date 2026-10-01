# ADR 0001 — Modular monolith, not microservices

- **Status:** Accepted (Phase 1)
- **Date:** 2026-10-01

## Context
GlideUp has eight functional modules (auth/profile, jobs, matching, interviews, tests, tracker,
dashboard, admin), one developer, a 16 GB laptop as the only environment for three months, and a
need to deploy cheaply to Azure afterwards. Several modules share data heavily (a job links to
matches, interviews, tests and applications).

## Decision
One FastAPI deployable with **enforced module boundaries**:

- Each module lives in `app/modules/<name>` and exposes plain async service functions.
- Routers (`app/api/v1`) are thin; services never import FastAPI.
- Modules call each other only through service functions, never by reaching into another
  module's tables from a router.
- Slow or scheduled work runs in Celery workers built from the **same image** (different command).

## Consequences
- ✅ One build, one migration history, real foreign keys and transactions across modules
  (e.g. a role change and its audit entry commit atomically).
- ✅ Fits the RAM budget: one API process instead of eight services plus a gateway and a broker mesh.
- ✅ Debuggable end to end with one request ID.
- ⚠️ A heavy module can starve others. Mitigation: CPU/LLM-heavy work goes to Celery queues,
  which can be scaled (and later split per queue) independently.
- ⚠️ Boundaries are by convention. Mitigation: code review rules above; `import-linter`
  contracts can be added if modules start leaking.

## When to revisit
Extract a module into its own service only when it has a clearly different scaling or release
profile — the likeliest first candidate is **code execution** (sandbox runners) or the
**LLM gateway**, both already behind interfaces.
