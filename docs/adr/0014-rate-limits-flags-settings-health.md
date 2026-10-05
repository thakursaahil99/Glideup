# ADR 0014 — Rate limits, LLM cache and budgets, feature flags, health and hardening

- **Status:** Accepted (Phase 9)
- **Date:** 2026-10-05

## Context
Before going live, three risks matter most: one user (or a script) burning the free LLM quota,
admins needing to change models or switch features off without a deploy, and nobody seeing
an outage until users report it.

## Decision

**Rate limiting.** A Redis token bucket (one Lua script, atomic) per *user* and bucket:
`default`, `llm`, `code`, `upload`, `interview`. Limits are per user, not per IP, because
every browser request reaches the API through the Next.js BFF, which shares one IP.
A 429 carries `retry_after`. If Redis is down the limiter falls back to an in-process
bucket and retries Redis after a cool-off, so an outage degrades limits instead of the site.

**LLM cache and budget.** Deterministic tasks (low temperature, structured output) are cached
in Redis by an exact hash of task, model and messages. Conversational tasks are never cached.
Cache hits are logged in `llm_usage` with `cached=true`, so cost reports stay honest.
An optional daily token budget per user turns into `BudgetExceededError`, which callers
already handle as "AI unavailable" and fall back to heuristics.

**Runtime settings.** `site_settings` holds LLM route overrides per task, cache on/off and TTL,
and the budget. Every process re-reads them at most every 30 seconds. Edits are validated:
providers must be configured, and embeddings get exactly one model so vector spaces never mix.
Every edit is audited.

**Feature flags.** Each flag is on/off globally, with a rollout percentage (stable hash of
flag + user) and an allow-list of testers. Flags are enforced on the server
(`feature_disabled`, 403) and mirrored in the UI via `/me/flags`. Unknown or loading flags are
treated as on, so the UI never flickers features away.

**Health.** `/admin/system/health` checks Postgres, Redis, workers, LLM providers and
circuit breakers, the code sandbox and email live. It lists failed background jobs from the
last 7 days with a one-click retry (`system:manage`). Prometheus metrics cover LLM calls,
latency, tokens, cache, 429s, submissions and jobs, and Grafana ships a provisioned dashboard.

**Hardening.** A security-headers middleware sets nosniff, frame DENY, referrer policy,
CSP `default-src 'none'` on the API, and HSTS in production. Request bodies are capped
(2 MB, or 6 MB on upload) with a 413. The web app sends its own CSP. See
[docs/security.md](../security.md) for the OWASP checklist.

## Consequences
- Limits survive restarts and scale across API replicas, because state lives in Redis.
- Cache keys include the model, so changing a route never serves another model's answer.
- A 30-second settings delay is the price of not adding pub/sub.
