# ADR 0005 — Local stack: Docker Compose, profiles and a memory budget

- **Status:** Accepted (Phase 1)
- **Date:** 2026-10-01

## Context
Everything must run on a 16 GB laptop, together with Ollama on the host, and start with one
command. Some services (Judge0, Prometheus/Grafana) are heavy and only needed later.

## Decision
- `docker compose up --build` starts the core stack: Postgres+pgvector, Redis, Meilisearch,
  MinIO (+ bucket init), Mailpit, a one-shot `migrate`, API, Celery worker, Celery beat, web.
- Each service has a **memory limit**; the core stack is capped at roughly 4 GB.
- Optional groups use **Compose profiles**: `--profile monitoring` adds Prometheus + Grafana.
  The code sandbox gets its own profile in Phase 6 (Judge0 needs privileged containers and
  cgroup settings that must be validated on Docker Desktop/WSL2, with Piston as the fallback).
- Migrations run in a dedicated one-shot service the API waits for, so app containers never
  race to migrate.
- All host ports are configurable (`WEB_PORT`, `API_PORT`, …) because developer machines often
  already use 3000/8000.
- Backend and web images run as non-root users with health checks.

## Consequences
- ✅ One command, predictable RAM, and production-like images (standalone Next.js, slim Python).
- ⚠️ No hot reload inside containers. For day-to-day coding run infra in Docker and the apps
  natively (`uv run uvicorn …`, `npm run dev`) — see the README.
- ⚠️ MinIO's community edition stopped publishing new images in late 2025; the last published
  image is used locally. Storage sits behind an S3 interface, so swapping to another
  S3-compatible server (e.g. SeaweedFS, Garage) or Azure Blob is configuration only.
