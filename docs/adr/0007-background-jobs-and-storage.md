# ADR 0007 — Background jobs (Celery or inline) and pluggable object storage

- **Status:** Accepted (Phase 2)
- **Date:** 2026-10-01

## Context
Resume parsing takes 10–70 s with a local model, so it cannot run inside an HTTP request.
The brief specifies Celery + Redis and MinIO. The developer's laptop could not run Docker for
part of Phase 2, and tests must not need Redis or MinIO.

## Decision
**Jobs are plain `async def` functions** that open their own DB session and are idempotent
(re-running a parsed resume is a no-op). How they run is configuration (`TASK_EXECUTION`):

- `celery`: the API enqueues to Redis; a Celery task wrapper runs the coroutine on **one
  long-lived event loop per worker process**, so the async DB pool and HTTP clients are reused.
  `acks_late` and `reject_on_worker_lost` give at-least-once delivery, which is safe because
  jobs are idempotent.
- `inline`: the job is scheduled on the API's event loop (development without Docker, tests).

The API always **commits before dispatching**, so a job never starts before its rows exist.

**Storage** sits behind a three-method `ObjectStorage` interface (`put`, `get`, `delete`):
`S3Storage` (MinIO, AWS, any S3-compatible store) and `LocalStorage` (a folder, protected
against path traversal). Keys are validated against a strict pattern. Azure Blob is one more
implementation.

**Celery-level retries are off for parsing**: the LLM gateway already falls back across
providers, and a failed parse is shown to the user with a "try again" action, which beats
silent retries.

## Consequences
- ✅ One code path for jobs: tests exercise the real job functions.
- ✅ Development works with or without Docker; Compose pins `celery` + `s3`.
- ⚠️ Inline jobs die with the API process (acceptable for local development only, and the
  user can re-parse).
- ✅ A worker killed mid-job leaves the resume in `parsing`; after 10 minutes that status
  counts as abandoned, and the redelivered job (or the user's "try again") reclaims it.
  A fresher `parsing` status makes duplicate deliveries no-ops.
- ⚠️ A periodic sweeper plus a failed-jobs admin screen arrive in Phase 9.
