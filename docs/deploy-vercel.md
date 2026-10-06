# Deploying GlideUp on Vercel + Neon (all free)

| Piece | Host | Free-tier notes |
|---|---|---|
| Web app (Next.js) | Vercel project `glideup` (root `frontend`) | region `sin1` |
| API (FastAPI) | Vercel project `glideup-api` (root `backend`, `index.py`) | Python function, 300 s max per request |
| Database (Postgres + pgvector) | Neon `glideup-db`, via the Vercel integration | 0.5 GB; resumes are stored here too |
| AI + embeddings | GitHub Models token | per-day request limits; set budgets in Admin → AI / LLM |
| Periodic jobs | GitHub Actions `cron` workflow, every 30 min | calls `POST /api/v1/internal/cron` |

How the API fits serverless:
- Background jobs run inline and the request stays open until they finish (`INLINE_JOBS_IN_REQUEST`).
- Interviews stream over plain HTTP instead of WebSockets (`INTERVIEW_TRANSPORT=http`).
- The Neon integration sets `DATABASE_URL` to its pooler; the API uses `DATABASE_URL_UNPOOLED` instead.

Not available on this setup: the **code sandbox**. Coding problems open, but Run/Submit report
the sandbox as unavailable. The Oracle VM setup ([deploy.md](deploy.md)) includes it.

## 1. Database
Created with `vercel integration add neon` from `backend/`, so `DATABASE_URL*` are already in
`glideup-api`. Migrations and seed data run from a laptop (not on each cold start):

```sh
cd backend
vercel env pull /tmp/neon.env --environment production
DATABASE_URL="$(grep ^DATABASE_URL_UNPOOLED= /tmp/neon.env | cut -d= -f2- | tr -d '"')" \
  ENVIRONMENT=local sh -c 'alembic upgrade head && python -m app.scripts.seed'
```

Run this again whenever a release adds a migration.

## 2. Environment variables
Set these in each Vercel project (Settings → Environment Variables, Production), then redeploy.
API (`glideup-api`):

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `TASK_EXECUTION`, `INLINE_JOBS_IN_REQUEST`, `INLINE_SCHEDULER_MINUTES` | `inline`, `true`, `0` |
| `STORAGE_BACKEND`, `SEARCH_BACKEND`, `REDIS_URL` | `database`, `database`, `none` |
| `INTERVIEW_TRANSPORT` | `http` |
| `CORS_ORIGINS`, `WEB_URL` | `https://glideup-ashen.vercel.app` |
| `API_PUBLIC_URL` | `https://glideup-api.vercel.app` |
| `JWT_SECRET`, `CRON_SECRET` | random, 32+ chars |
| `GOOGLE_CLIENT_ID`, `ADMIN_EMAILS`, `GITHUB_MODELS_TOKEN` | same as the root `.env` |
| `LLM_ROUTES` | GitHub Models for every task, embeddings included (value below) |

`LLM_ROUTES`:

```json
{"resume_parse": ["github:openai/gpt-4.1-mini", "github:openai/gpt-4.1-nano"], "portfolio_parse": ["github:openai/gpt-4.1-mini", "github:openai/gpt-4.1-nano"], "skill_gap": ["github:openai/gpt-4.1-mini", "github:openai/gpt-4.1-nano"], "interview_plan": ["github:openai/gpt-4.1-mini", "github:openai/gpt-4.1-nano"], "interviewer": ["github:openai/gpt-4.1-mini", "github:openai/gpt-4.1-nano"], "interview_hint": ["github:openai/gpt-4.1-mini", "github:openai/gpt-4.1-nano"], "interview_report": ["github:openai/gpt-4.1-mini", "github:openai/gpt-4.1-nano"], "question_generate": ["github:openai/gpt-4.1-mini"], "framework_grade": ["github:openai/gpt-4.1-mini", "github:openai/gpt-4.1-nano"], "embedding": ["github:openai/text-embedding-3-small"]}
```

Web (`glideup`): `API_INTERNAL_URL=https://glideup-api.vercel.app`, `AUTH_URL`, `AUTH_SECRET`,
`AUTH_TRUST_HOST=true`, `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`.

## 3. Sign-in
Until Google sign-in is set up, email sign-in works with one shared password: set
`AUTH_DEV_LOGIN_ENABLED=true` in **both** projects and `AUTH_DEV_LOGIN_PASSWORD` (12+ chars) in
`glideup-api`. Anyone with the password can sign in as any email, including `ADMIN_EMAILS`, so
share it only with people you trust and switch it off once Google works.

### Google
console.cloud.google.com → APIs & Services → Credentials → the OAuth client:
- Authorized JavaScript origin: `https://glideup-ashen.vercel.app`
- Authorized redirect URI: `https://glideup-ashen.vercel.app/api/auth/callback/google`

On the OAuth consent screen, publish the app, or add test users.

## 4. Periodic jobs
GitHub repo → Settings → Secrets and variables → Actions: variable `API_URL` =
`https://glideup-api.vercel.app`, secret `CRON_SECRET`.

## Match-score calibration
Live uses `text-embedding-3-small` instead of local nomic. `MATCH_SEMANTIC_FLOOR` and
`MATCH_SEMANTIC_CEILING` (0.25 / 0.60) are provisional. Re-run `python -m app.llm.evals.match`
against real data and adjust them in Vercel.
