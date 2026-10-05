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

## Addendum: structured locations (2026-10-01)

Free-text locations ("Bangalore, IND", "Remote - US", "San Francisco, CA | New York City, NY")
are parsed into **places**: country (ISO 3166-1), state/region and city. A job can have several.

- **Gazetteer** (`app/jobsources/geo_data.py`): all 28 Indian states and 8 union territories with
  codes and aliases (Orissa, Pondicherry, J&K, NCT of Delhi); around 110 Indian cities with aliases
  (Bangalore → Bengaluru, Gurgaon → Gurugram, Bombay → Mumbai, Madras → Chennai); states/provinces
  for the US, Canada, UK, Australia and Germany; about 90 countries (names, alpha-2/3 codes) and
  the main tech cities elsewhere.
- **Parser** (`app/jobsources/geo.py`): context-aware token walk. Abbreviations only count
  next to a known country ("CA" after San Francisco = California, "IN" after Indianapolis =
  Indiana), and may only fill in or confirm a state, so office codes like "Bangalore - DD" are
  ignored. Names that are both city and state ("Delhi", "New York", "Washington") are the
  city unless they confirm the previous city's state. Unknown towns are kept when the next
  token identifies the state or country ("Clarks Summit, PA"). Structured source data (Adzuna's
  `area`) is used directly. **Coverage on the 10,749 real jobs: 94%** have a place, 73% a city.
- **Remote scope**: remote jobs restricted to listed countries are `country`
  ("Remote - India"); remote with no country, or explicitly worldwide/global/anywhere, is
  `worldwide`. A plain "Remote" from a US company may in practice be US-only; we don't guess.
- **Search**: `countries`, `states` and `cities` are Meilisearch facets. Counts are
  **disjunctive and hierarchical**: country counts ignore the selected country/state/city, state
  counts ignore state/city, and state/city lists are narrowed to the selected country via the
  gazetteer (a "Bengaluru; Seattle" job doesn't put Washington in India's list). One
  `multi_search` round trip computes all of it. The database fallback uses a
  `|c:IN|s:Karnataka|ci:Bengaluru|` index column.
- **Adzuna**: all 19 countries its API serves can be enabled per country from the admin console;
  config is validated server-side (unknown countries, empty search terms, out-of-range limits).

## Addendum: more free sources, metro areas and hiring signal (2026-10-01)

Users asked for more jobs per Indian city (Delhi showed only a handful). Coverage is limited by
which sources we may use, not by search.

- **Sources added**: **SmartRecruiters** public postings API (Swiggy, Freshworks, Canva, Grab, Wise
  and others). The list call carries a release date per posting, so details are only fetched for
  new or changed postings (`FetchContext.known`, `Posting.details_omitted`). **Arbeitnow**
  public job-board API (no key, attribution shown, paginated, `max_pages` admin-configurable).
  The seed list grew from 58 to 78 companies, with more India-heavy employers.
- **Rejected**: Indeed and Naukri (terms forbid scraping, no free public API); Remotive (terms
  forbid redisplay behind a signup wall, and only a few dozen jobs). Adzuna stays the main route
  to broad city coverage; it needs the operator's own free key.
- **Metro areas** (`METROS` in the gazetteer): Delhi NCR (Delhi, New Delhi, Noida, Greater Noida,
  Gurugram, Ghaziabad, Faridabad), Mumbai Metropolitan Region and San Francisco Bay Area. The
  `metro` query parameter expands to member cities; facet counts are exact (a job listed in two
  NCR cities counts once), at one extra query per relevant metro. A free-text location of
  "NCR" resolves to the metro.
- **Hiring signal**: after each ingestion run, every active job stores its company's open roles
  and roles opened in the last 7 days (`company_open_roles`, `company_new_roles_7d`), and changed
  jobs are re-indexed. Denormalised so "Most hiring" is a plain Meilisearch sort (featured first,
  then open roles, then recency) instead of a join at query time. A company is **hiring actively**
  at 25+ open roles or 10+ new this week. The UI shows a badge, a "Most hiring" sort and the
  companies with the most openings for the current search.
- **Result on real data**: 10,541 → 14,598 jobs; India 821 → 1,333; Delhi NCR 108 → 191.
