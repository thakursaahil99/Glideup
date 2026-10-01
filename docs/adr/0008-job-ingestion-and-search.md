# ADR 0008 — Job ingestion from official APIs, deduplication, and resilient search

- **Status:** Accepted (Phase 3)
- **Date:** 2026-10-01

## Context
GlideUp needs real, fresh jobs without scraping sites whose terms forbid it (LinkedIn, Naukri,
Indeed). Sources differ wildly in shape, reliability and rate limits, and the same role often
appears more than once. Search must be fast and typo-tolerant, and must keep working when the
search service is down.

## Decision

**Sources (official APIs only).** One `JobSourcePlugin` interface; adding a source means one
module plus one registry line.
- ATS boards that companies publish themselves: **Greenhouse, Lever, Ashby**. The admin-managed
  company list started with **58 boards verified against the live APIs** (about 10,700 jobs).
- **Adzuna** (free key, attribution shown in the UI) for broad India coverage; off until configured.
- Every job links to the company's own apply page. We store only what the source publishes.

**Fetching.** A shared HTTP client spaces requests to each source's admin-editable rate,
retries 429/5xx/network errors with exponential backoff and jitter (honouring `Retry-After`),
never retries other 4xx, and identifies itself with a User-Agent.

**Pipeline per run:** fetch → normalise → upsert → dedup → retire stale → index.
- *Scopes:* each board (or aggregator query) is a scope, committed separately. A scope that
  fails is reported, and **its jobs are not retired**, so a source outage never empties the board.
- *Normalisation:* nh3 allow-list sanitising of third-party HTML; work mode and seniority
  heuristics; technical skills from the shared taxonomy (soft skills and HR boilerplate excluded).
- *Change detection:* a hash of the **raw** posting plus a `NORMALIZER_VERSION`. Unchanged jobs
  skip normalisation, so a steady-state Greenhouse run fell from 334 s to 41 s (just the
  rate-limited network time). Bumping the version re-normalises everything once.
- *Dedup:* SHA-256 of normalised title + company + location. The oldest listed copy wins
  (ties broken by id, so two copies never hide each other). When the original disappears, its
  duplicate is promoted. Admins can mark "not a duplicate", which sticks across runs.
- *Concurrency:* one run per source at a time (a `running` row acts as the lock and expires
  after an hour, so a crashed worker cannot block a source forever).

**Scheduling.** Celery Beat checks every 5 minutes which sources are due (default every 6 h,
admin-editable). Without Docker, the API runs the same check in-process.

**Search.** Meilisearch (typo tolerance, filters, facet counts) returns only job IDs; jobs are
always loaded from Postgres, so a stale index can never show a hidden or retired job. If
Meilisearch fails, search **falls back to the database** (titles, companies and skills only,
no typo tolerance) and the UI says it is in simplified mode. Paging uses an opaque cursor so
the strategy can change without breaking clients.

## Measured on real data (10,535 listed jobs, laptop)
| Query | Meilisearch | Database fallback |
|---|---|---|
| "python" | 35 ms | 51 ms (after limiting it to titles, companies and skills; was 11.7 s) |
| "backend" + remote | 6 ms | 51 ms |
| typo "kuberntes" | 947 hits | 0 hits (no typo tolerance: degraded mode) |

## Consequences
- ✅ Legal and fair use of data; stable, typed sources; admin controls everything (sources,
  schedules, rate limits, companies, jobs, duplicates, re-index), and all of it is audited.
- ✅ Outages degrade gracefully at every layer: per board, per source, and for search.
- ⚠️ Work mode and seniority are heuristics: about 49% of jobs are "unknown" work mode. Phase 4's
  LLM enrichment can classify the unknowns.
- ⚠️ Dedup by exact normalised key misses fuzzy duplicates (e.g. "Sr." vs "Senior"); good
  enough for now, revisit with embeddings in Phase 4.
