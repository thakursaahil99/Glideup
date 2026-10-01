<p align="center">
  <img src="frontend/public/icons/logo.svg" width="64" alt="GlideUp logo" />
</p>

<h1 align="center">GlideUp</h1>
<p align="center"><strong>Find jobs. Practice interviews. Get hired.</strong></p>

GlideUp is an AI-powered platform that matches your resume to real jobs, shows your skill gaps,
runs job-specific mock interviews and coding tests in many languages and frameworks, and tracks
your applications — from job search to offer.

> **Status:** Phase 1 of 10 — foundation (monorepo, Docker stack, Google sign-in, RBAC, admin
> console shell with overview, users and audit log). See the [build plan](PROJECT_BRIEF.md#13-build-plan-follow-this-order).

## Architecture

```mermaid
flowchart LR
    B[Browser / PWA] --> W[Next.js + Auth.js<br/>BFF proxy]
    W --> A[FastAPI<br/>modular monolith]
    A --> P[(Postgres + pgvector)]
    A --> R[(Redis)]
    A --> M[(Meilisearch)]
    A --> S[(MinIO)]
    R --> C[Celery workers + beat]
    C --> L[[LLM gateway]]
```

More: [docs/architecture.md](docs/architecture.md) · decisions in [docs/adr](docs/adr).

## Tech stack

| Layer | Tools |
|---|---|
| Web | Next.js 16 (App Router), React 19, TypeScript (strict), Tailwind CSS 4, shadcn-style components, TanStack Query, Auth.js v5, Recharts |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, Celery, structlog |
| Data | PostgreSQL 17 + pgvector, Redis, Meilisearch, MinIO |
| Quality | pytest (+ coverage), Ruff, mypy strict, Vitest + Testing Library, ESLint, GitHub Actions, pre-commit |
| Ops | Docker Compose, Prometheus + Grafana (opt-in profile), JSON logs with request IDs |

## Run it locally

Prerequisites: **Docker Desktop** (with WSL2 on Windows). Optional: Ollama on the host (Phase 2).

```bash
cp .env.example .env
# 1. Set ADMIN_EMAILS to your email (you become super_admin on first sign-in).
# 2. Set AUTH_SECRET and JWT_SECRET to two different random strings (npx auth secret).
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:3000 | GlideUp web app |
| http://localhost:8000/docs | API docs (OpenAPI) |
| http://localhost:8025 | Mailpit (caught emails) |
| http://localhost:9001 | MinIO console |
| http://localhost:3001 | Grafana (`docker compose --profile monitoring up`) |

Ports already taken? Change `WEB_PORT`, `API_PORT`, … in `.env` (and keep `AUTH_URL` /
`CORS_ORIGINS` in sync with `WEB_PORT`).

### Signing in
- **Without Google setup:** `AUTH_DEV_LOGIN_ENABLED=true` (default in `.env.example`) shows a
  developer sign-in form on `/login`. Local only — the API refuses it in staging/production.
- **With Google:** create an OAuth client (type *Web application*) in Google Cloud Console, add
  the redirect URI `http://localhost:3000/api/auth/callback/google`, then set `AUTH_GOOGLE_ID`,
  `AUTH_GOOGLE_SECRET` and `GOOGLE_CLIENT_ID` (same value as `AUTH_GOOGLE_ID`).

### Developing without containers for the apps (hot reload)

```bash
docker compose up postgres redis meilisearch minio minio-init mailpit   # infra only

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload             # reads ../.env

cd frontend
cp ../.env .env.local                            # Next.js reads env from its own folder
npm install
npm run dev
```

## Tests and checks

```bash
cd backend
uv run pytest --cov=app                         # SQLite by default
TEST_DATABASE_URL=postgresql+asyncpg://glideup:glideup@localhost:5432/glideup_test uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests

cd frontend
npm test && npm run lint && npm run typecheck && npm run build
```

After changing an API route, regenerate the typed client:

```bash
cd backend && uv run python -m app.scripts.export_openapi ../frontend/openapi.json
cd ../frontend && npm run gen:api
```

## Environment variables
Every variable is documented in [`.env.example`](.env.example). No secrets or URLs are hardcoded.

## Project layout

```
backend/    FastAPI app (core, db, api/v1, modules, workers) + tests
frontend/   Next.js app (app router pages, components, typed API client)
docs/       architecture.md and ADRs
infra/      Prometheus / Grafana provisioning
```

## Built by Sahil Thakur

Full-stack developer (10 years). GlideUp's name and paraglider logo come from
*Glide in Bir*, my paragliding booking site in Bir Billing. Links on the [About page](frontend/src/app/(marketing)/about/page.tsx).
