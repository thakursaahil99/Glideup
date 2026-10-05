# Deploying GlideUp on Vercel + Render + Neon (all free)

| Piece | Host | Free-tier notes |
|---|---|---|
| Web app (Next.js) | Vercel Hobby | region `sin1` (vercel.json) |
| API (FastAPI) | Render free web service | sleeps after 15 idle min; `keepalive` workflow pings it |
| Database (Postgres + pgvector) | Neon free | 0.5 GB; resumes are stored here too |
| AI + embeddings | GitHub Models token | per-day request limits; set budgets in Admin → AI / LLM |

Not available on this setup: the **code sandbox**. The public Piston API became whitelist-only
in Feb 2026, and Render free cannot run a privileged sandbox. Coding problems open, but
Run/Submit report the sandbox as unavailable. Everything else works. The Oracle VM setup
([deploy.md](deploy.md)) includes the sandbox.

## 1. Neon (database)
neon.tech → sign in with GitHub → New project, region **AWS Singapore**. Copy the
**direct** connection string (turn off "Connection pooling"; asyncpg needs the direct one):
`postgresql://user:pass@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
The pgvector extension is created by the first migration.

## 2. Render (API)
render.com → sign in with GitHub → **New → Blueprint** → pick this repo. It reads `render.yaml`.
Fill in when asked:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon string from step 1 |
| `GITHUB_MODELS_TOKEN` | GitHub → Settings → Developer settings → fine-grained token with **Models: read** |
| `GOOGLE_CLIENT_ID` | from step 4 |
| `ADMIN_EMAILS` | your Google email |
| `API_PUBLIC_URL` | `https://glideup-api.onrender.com` (the URL Render shows) |
| `CORS_ORIGINS`, `WEB_URL` | your Vercel URL from step 3, e.g. `https://glideup.vercel.app` |
| others (`ADZUNA_*`, `SMTP_*`) | optional; leave empty |

The first deploy builds the image, runs migrations and seeds companies, problems and framework
tests. Then job ingestion starts by itself. Check `https://glideup-api.onrender.com/healthz`.

## 3. Vercel (web)
Vercel → Add New Project → import this repo → **Root Directory: `frontend`**. Environment variables:

| Variable | Value |
|---|---|
| `API_INTERNAL_URL` | `https://glideup-api.onrender.com` |
| `AUTH_URL` | `https://<project>.vercel.app` |
| `AUTH_SECRET` | `openssl rand -hex 32` |
| `AUTH_TRUST_HOST` | `true` |
| `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET` | from step 4 |

## 4. Google sign-in
console.cloud.google.com → APIs & Services → Credentials → Create OAuth client ID (Web):
- Authorized JavaScript origin: `https://<project>.vercel.app`
- Authorized redirect URI: `https://<project>.vercel.app/api/auth/callback/google`

Put the client ID in Vercel (`AUTH_GOOGLE_ID`) **and** Render (`GOOGLE_CLIENT_ID`), and the
secret in Vercel only. On the OAuth consent screen, publish the app, or add test users.

## 5. Keep the API awake
GitHub repo → Settings → Secrets and variables → Actions → **Variables** → `API_URL` =
`https://glideup-api.onrender.com`. The `keepalive` workflow pings it every 10 minutes.

## Match-score calibration
Live uses `text-embedding-3-small` (768 dims) instead of local nomic. `MATCH_SEMANTIC_FLOOR`
and `MATCH_SEMANTIC_CEILING` (0.25 / 0.60) are provisional. Re-run `python -m app.llm.evals.match`
against real data and adjust them in Render.
