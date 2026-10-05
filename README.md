<p align="center">
  <img src="frontend/public/icons/logo.svg" width="64" alt="GlideUp logo" />
</p>

<h1 align="center">GlideUp</h1>
<p align="center"><strong>Find jobs. Practice interviews. Get hired.</strong></p>

GlideUp is an AI-powered platform that matches your resume to real jobs, shows your skill gaps,
runs job-specific mock interviews and coding tests in many languages and frameworks, and tracks
your applications — from job search to offer.

> **Status:** Phase 6 of 10. Coding tests in six languages graded in a sandbox against hidden
> tests, with an admin question bank and an AI generation queue whose questions are validated
> by running their reference solutions. Before that: AI mock interviews with reports (Phase 5),
> match scores and a skill-gap coach (Phase 4), the job board (Phase 3), resume parsing
> (Phase 2) and the foundation (Phase 1). See the
> [build plan](PROJECT_BRIEF.md#13-build-plan-follow-this-order).

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

### Admin accounts

There are two ways to make someone an admin, both recorded in the audit log:

1. **`ADMIN_EMAILS`** in `.env`: these emails become `super_admin` when they sign in.
2. **The command line** (works in production, where dev login is off):

```bash
cd backend
uv run python -m app.scripts.manage_admins grant you@example.com                 # super_admin
uv run python -m app.scripts.manage_admins grant helper@example.com --role support
uv run python -m app.scripts.manage_admins revoke old-admin@example.com
uv run python -m app.scripts.manage_admins list

# with Docker
docker compose exec api python -m app.scripts.manage_admins list
```

After that, admins manage everyone else from **Admin → Users**. The last `super_admin` can't be removed.

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

### AI models (free)

GlideUp works with **no AI at all** (a heuristic fallback parser), but a real model is far better:

```bash
# Ollama on the host (https://ollama.com): ~2.2 GB of downloads, runs comfortably on 16 GB RAM
ollama pull qwen2.5:3b          # resume parsing
ollama pull nomic-embed-text    # embeddings for job matching
```

On a laptop CPU, a resume takes about 10–70 s to parse. For faster demos, add a free
`GITHUB_MODELS_TOKEN`; it's used automatically as a fallback, or first via `LLM_ROUTES`.
Measure any model or prompt change with the golden-set evals:

```bash
cd backend && uv run python -m app.llm.evals.run --route ollama:qwen2.5:3b
cd backend && uv run python -m app.llm.evals.match --route ollama:nomic-embed-text   # match scoring
```

### Jobs

Jobs come only from official public APIs: company job boards on Greenhouse, Lever, Ashby and
SmartRecruiters, the Arbeitnow job board, plus Adzuna with a free key. Nothing is scraped,
and every job links to the company's own apply page. Sources, schedules, rate limits and the company list are managed in **Admin → Jobs &
Sources**.

```bash
cd backend
uv run python -m app.scripts.seed        # sources + the verified company list (Compose runs this)
# then click "Run now" in Admin → Jobs & Sources, or wait for the schedule (every 6 hours)
```

### Matching

Each job's match score blends three things: how closely your resume reads like the job
(embeddings in pgvector), how many of its skills you have (from your resume and GitHub), and
whether your years fit its level. The job page shows the breakdown, your matched, related
and missing skills, and an **AI skill-gap coach** that explains each gap with a concrete way
to close it. **Recommended for you** ranks the nearest jobs by that score, nudged by your
preferred locations and remote preference. How it works and how it was calibrated:
[ADR 0009](docs/adr/0009-matching-and-skill-gap.md).

New jobs are embedded automatically after each ingestion run (`nomic-embed-text` via Ollama:
`ollama pull nomic-embed-text`). The first backfill of ~15k jobs takes about an hour on a
laptop CPU; progress and a "run now" button are in **Admin → Jobs & Sources**.

### Mock interviews

Pick a type (or click **Practice interview for this job** on a job page), press Start, and
answer in the chat; coding and design rounds add a code / notes panel. The interviewer streams
its follow-ups, gives hints on request and keeps time. When you finish, a report scores you
against the rubric with quotes from your answers. Interview types and rubrics are edited in
**Admin → Interviews**, and every LLM prompt in **Admin → Prompt Templates**. Design:
[ADR 0010](docs/adr/0010-mock-interviews.md).

The browser connects to the API's WebSocket directly, so set `API_PUBLIC_URL` to where
browsers reach the API (default `http://localhost:8000`) and include the web origin in
`CORS_ORIGINS`.

### Coding tests

Problems read standard input and print standard output, in Python, JavaScript, TypeScript,
Java, C++ or Go. **Run** checks the examples; **Submit** grades against hidden tests in a
sandbox. Start the sandbox and install its runtimes once:

```bash
docker compose --profile sandbox up -d piston
cd backend && uv run python -m app.scripts.install_sandbox_runtimes
```

Admins manage problems, languages and limits in **Admin → Question Bank**, and generate new
problems in **Admin → AI Generation Queue**: the model writes the problem and a reference
solution, and the sandbox produces the expected outputs. Design:
[ADR 0011](docs/adr/0011-code-sandbox-and-question-bank.md).

### Running without Docker

Everything except the job board (Phase 3) runs on Windows/macOS/Linux without Docker:

```bash
# any Postgres with pgvector: DATABASE_URL=postgresql+asyncpg://...
cd backend
uv run alembic upgrade head
TASK_EXECUTION=inline STORAGE_BACKEND=local uv run uvicorn app.main:app --port 8000
```

`TASK_EXECUTION=inline` runs background jobs inside the API, and `STORAGE_BACKEND=local` stores
files under `backend/var/storage`. Docker Compose always uses Celery and MinIO.

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
