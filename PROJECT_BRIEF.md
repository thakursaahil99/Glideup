# GlideUp — Full Build Prompt

> Paste this entire file into your AI coding assistant (Claude Code, Cursor, etc.) at the start of the project. Keep it in the repo root as `PROJECT_BRIEF.md` so the assistant can refer back to it in every session.

---

## 0. Your role

You are a senior full-stack engineer and product designer helping me build **GlideUp**, a production-quality portfolio project. Write clean, well-structured, tested code that a Principal Engineer at Microsoft would approve in code review. Explain important design decisions briefly as you go, and record major ones as ADRs (see Section 12).

Build **incrementally, phase by phase** (Section 13). Do not try to generate the whole project in one go. At the end of each phase, make sure everything runs with `docker compose up`, tests pass, and summarize what was built and what comes next. If something in this brief is unclear or a better approach exists, tell me before deviating.

---

## 1. About me and the project

- **Builder:** Sahil Thakur — full-stack developer with 10 years of experience, preparing for senior-level interviews at Microsoft.
- **My other project:** *Glide in Bir* — a paragliding e-commerce/booking site. GlideUp's name and flying theme intentionally connect to it.
- **Project name:** **GlideUp**
- **Tagline:** *Find jobs. Practice interviews. Get hired.*
- **One-line description:** GlideUp is an AI-powered platform that matches your resume to real jobs, shows your skill gaps, runs job-specific mock interviews and coding tests in many languages and frameworks, and tracks your applications — from job search to offer.
- **Credit:** Footer on every page: "Built by Sahil Thakur". An About page with a short bio and links (GitHub, LinkedIn, Glide in Bir) — leave placeholder URLs for me to fill.

### Goals
1. Show senior-level engineering depth: system design, scalability, security, AI integration, data pipelines, observability.
2. Be a genuinely useful product I can use for my own job search.
3. **Local-first:** for now everything must run on my laptop with free, open-source tools. I will deploy it publicly in about 3 months, so design it to be cloud-ready (Azure preferred) without code changes — only config.
4. **Zero cost:** use only free and open-source tools and free API tiers.
5. **Fully admin-managed:** the entire platform (users, jobs, job sources, questions, tests, interviews, AI prompts and models, features, site content) must be controllable from the Admin Console (Module 8) without code changes or redeploys.

---

## 2. Core user journey

**Upload resume → see matching jobs → understand skill gaps → take a mock interview and coding test for that job → get a feedback report → apply → track the application.**

Every module should connect to this journey (e.g., from a job page, one click starts a mock interview tailored to that job description).

---

## 3. Tech stack (use exactly this unless you justify a change)

### Frontend (TypeScript)
- **Next.js (App Router) + React + TypeScript**
- **Tailwind CSS + shadcn/ui** for components
- **TanStack Query** for server state
- **Monaco Editor** for the code editor
- **Auth.js** with Google OAuth (works on localhost)
- **PWA** support (installable on mobile)
- Charts: **Recharts**

### Backend (Python — this is the core of the project)
- **Python 3.12+**, managed with **uv**
- **FastAPI** (async), **Pydantic v2**
- **SQLAlchemy 2.0 (async) + Alembic** migrations
- **Celery + Celery Beat** for background and scheduled jobs (Redis broker)
- **pypdf / pdfplumber** for resume parsing
- **httpx** for external API calls
- **Ruff** (lint + format), **mypy** (type checks), **pytest** + **pytest-asyncio**
- Structured JSON logging

### Data & infrastructure (all in Docker Compose)
| Service | Tool | Purpose |
|---|---|---|
| Database | PostgreSQL + **pgvector** | All app data + embeddings |
| Cache / broker | Redis | Rate limiting, caching, Celery broker |
| Search | **Meilisearch** | Fast job search with typo tolerance and filters |
| File storage | **MinIO** | S3-compatible storage for resumes (easy switch to Azure Blob/S3 later) |
| Code execution | **Judge0** (self-hosted; **Piston** as fallback) | Sandboxed multi-language code runner |
| Email (dev) | **Mailpit** | Catch reminder/notification emails locally |
| Monitoring | **Prometheus + Grafana** | Metrics dashboards (Phase 7) |

### AI (free)
- **Ollama** running on the host machine (not in Docker) for local LLM (e.g., a Qwen or Llama model that fits my RAM) and embeddings (e.g., `nomic-embed-text`).
- **GitHub Models** free tier for higher-quality responses in demos.
- **OpenRouter** free models as an additional option.
- A **Mock LLM provider** (configurable delay and error rate) for tests and load testing.
- All providers sit behind one `LLMProvider` interface with **routing and automatic fallback**, so switching to Azure OpenAI later is one config change.

### Dev tooling
- Docker Compose (one command: `docker compose up`)
- GitHub Actions CI: lint, type-check, tests for backend and frontend
- pre-commit hooks
- `.env.example` with every variable documented — **no hardcoded secrets or URLs anywhere**

---

## 4. Architecture

```
Browser / PWA (Next.js)
        │  REST + WebSocket
        ▼
   FastAPI API server ──► Redis (cache, rate limits, Celery broker)
        │                     │
        ├──► PostgreSQL       ▼
        │    + pgvector   Celery workers + Celery Beat
        ├──► Meilisearch   ├─ job ingestion (every 6 hours)
        ├──► MinIO         ├─ resume parsing + embeddings
        │                  ├─ feedback report generation
        │                  └─ code/test evaluation → Judge0
        ▼
   LLM gateway layer (Ollama / GitHub Models / OpenRouter / Mock)
   with routing, fallback, caching, token + cost tracking
```

Principles:
- Modular monolith for the backend (clear module boundaries, one deployable). Explain in an ADR why this beats microservices at this stage.
- **Plugin architecture** for languages, frameworks and job sources: adding a new one should be a config entry (+ Docker image if needed), not a code change.
- 12-factor app: config via environment, stateless API, logs to stdout.

---

## 5. Modules and features

### Module 1 — Auth, Profile & Resume
- Google login via Auth.js; backend issues/validates JWTs (access + refresh).
- Profile: name, headline, years of experience, target roles, preferred locations, remote preference.
- Resume upload (PDF) → stored in MinIO → Celery job parses it → LLM extracts structured JSON (skills, experience, education, years per skill) → validated with Pydantic → stored → embedding generated.
- User can view and edit the parsed result.

### Module 2 — Job Search
- **Ingestion pipeline** (Celery Beat, every 6 hours):
  - Public ATS job board APIs: **Greenhouse**, **Lever**, **Ashby** — from a configurable list of tech companies (start with ~50, design for 200+).
  - Aggregator APIs with free tiers: **Adzuna** (India support), **Jooble**, **Remotive**, **Arbeitnow**.
  - Each source is a plugin implementing a common `JobSource` interface.
  - **Normalization** into one schema; **deduplication** via a hash of normalized title + company + location; mark stale jobs inactive.
  - Respect each API's terms and rate limits; retries with exponential backoff; per-source health tracking.
- **Strict rule:** do NOT scrape LinkedIn, Naukri, Indeed or any site whose terms forbid it. For big companies with custom career sites (Microsoft, Google), only store/link to the official apply URL.
- Search UI backed by Meilisearch: keyword, location, remote, experience level, skills, date posted, company.
- Saved jobs.

### Module 3 — Matching & Skill Gap
- Job description embeddings (pgvector) vs resume embedding → **match score** (e.g., "82% match"), combined with skill overlap.
- "Recommended for you" feed.
- **Skill gap analysis** per job: LLM lists missing/weak skills with short learning suggestions.
- One-click buttons: **"Practice interview for this job"** and **"Take a skill test"** (pre-selects relevant languages/frameworks from the job description).

### Module 4 — AI Mock Interview
- Interview types: **DSA/coding**, **system design**, **behavioral**, and **job-specific** (generated from a job description + my resume).
- Real-time chat over **WebSocket** with token streaming.
- **Voice mode** using the browser Web Speech API (free) for speech-to-text and text-to-speech.
- AI behaves like a real interviewer: asks follow-ups, gives hints only when asked, keeps time.
- Behavioral round evaluates answers in **STAR** format and Microsoft-style values (growth mindset, ownership, collaboration).
- System design round: a simple whiteboard (e.g., Excalidraw embed or a basic diagram tool) whose content the AI can review.
- **Feedback report** (Celery job): overall score, per-question scores, strengths, weaknesses, improvement tips, suggested next practice — stored and viewable later.

### Module 5 — Coding & Skill Tests (multi-language, multi-framework)
- **Language tests (DSA style):** start with Python, JavaScript, TypeScript, Java, C++, C#; design so Go, Rust and others are just config. Code runs in **Judge0** with time/memory limits; visible and hidden test cases; runtime and memory reported.
- **Framework tests (real-world style):** start with React, Node/Express, FastAPI, Django; later Next.js, Spring Boot, .NET, Angular.
  - **Mini-project tasks:** a multi-file starter project (e.g., "add pagination to this API", "fix this React component bug"). The user edits files in a multi-tab Monaco editor; the backend runs the framework's real test suite (pytest / Jest / JUnit / xUnit) in an isolated container; score = tests passed.
  - **Code review tasks:** buggy code; user identifies issues; LLM evaluates.
  - **Concept MCQs** per framework.
  - **AI viva** after a test: "Why did you choose this approach?"
- **Question bank rules:**
  - Do NOT copy questions from LeetCode, HackerRank or any copyrighted source. Write original questions.
  - AI-generated questions must ship with a reference solution and test cases, and are only added to the bank after the reference solution passes all tests in the sandbox (**auto-validation pipeline**). Keep an admin review flag.
- Seed the bank with ~10 original problems per starting language and ~3 tasks per starting framework.
- **Skill scores and badges:** per language/framework score shown on the profile ("Verified: React — 85").

### Module 6 — Application Tracker
- Kanban board: Saved → Applied → Interviewing → Offer / Rejected (drag and drop).
- Notes, contacts, dates, and reminders (emails go to Mailpit locally).
- Linked to the job and to any mock interviews done for it.

### Module 7 — Dashboard
- Applications by status, interview score trend, skill radar chart, weak topics, practice streak, recommended next step.

### Module 8 — Admin Console (manage everything without touching code)
A separate, protected admin area (`/admin`) from which the whole platform can be run. Principle: **anything that might need changing after launch must be manageable from the admin console, not hardcoded.**

**Roles (RBAC):**
| Role | Can do |
|---|---|
| `super_admin` | Everything, including managing other admins, LLM/provider settings and feature flags |
| `admin` | Users, jobs, question bank, interviews, content, announcements |
| `content_editor` | Questions, tests, prompt templates, MCQs — no user management |
| `support` | Read-only access to users, reports and logs to help users |
| `user` | Normal app access only |

Permissions are checked on the backend for every admin endpoint (not just hidden in the UI). Admin access is granted only via an allowlist or by a `super_admin`. **Every admin action is written to `audit_logs`** (who, what, when, before/after values).

**Admin features:**
1. **Overview dashboard:** total/active users, new signups, interviews and tests taken, applications tracked, jobs ingested, LLM usage and estimated cost, error rate, charts over time with date filters.
2. **User management:** search/filter users, view profile, resume, activity, scores; change role; suspend/unsuspend; reset usage limits; set per-user quotas (e.g., interviews per day); export or permanently delete a user's data (privacy request); read-only "view as user" with an audit log entry.
3. **Job management:**
   - Enable/disable each job source; edit its schedule and rate limits.
   - Manage the company list for Greenhouse / Lever / Ashby (add, remove, bulk import via CSV).
   - "Run ingestion now" button per source; source health (last run, jobs added, errors).
   - View, edit, hide or feature individual jobs; review and merge suspected duplicates.
4. **Question bank & tests:**
   - Create, edit, archive questions (DSA, framework mini-projects, code review, MCQ) with a rich editor, starter code per language, test cases (visible/hidden) and reference solutions.
   - "Run reference solution" button to validate in the sandbox.
   - **AI generation queue:** generate questions by topic/difficulty → auto-validated → admin approves, edits or rejects.
   - Enable/disable languages and frameworks; set time/memory limits per language.
   - Usage stats per question (attempts, pass rate, average time) to spot too-easy/too-hard questions.
5. **Interview configuration:** manage interview types, duration, number of questions, difficulty, and scoring rubrics (e.g., STAR rubric for behavioral).
6. **Prompt templates:** edit all LLM prompts from the UI with **versioning**, a diff view, rollback, and a "test this prompt" playground before publishing.
7. **AI / LLM settings (`super_admin`):** which provider and model to use for each task, fallback order, timeouts, cache on/off, global and per-user token budgets, and a usage/cost/latency report per provider and model.
8. **Feature flags:** turn features on/off globally or for specific users (e.g., voice mode, framework tests, new job sources) without redeploying.
9. **Content & site settings:** landing page text, tagline, About page content, FAQ, email templates, branding colors/logo — stored in the database and editable.
10. **Announcements & notifications:** show a banner or send an in-app/email announcement to all users or a segment.
11. **User feedback & reports:** users can report a wrong question, bad AI feedback, or a broken job link; admins see a queue, resolve, and reply.
12. **System health:** status of API, PostgreSQL, Redis, Celery workers and queue lengths, Meilisearch, MinIO, Judge0 and each LLM provider; list of failed background jobs with "retry" button; link to Grafana.
13. **Audit log viewer:** searchable and filterable history of all admin actions.

**Admin UI:** same design system as the app, data tables with search, filters, sorting, pagination, bulk actions and CSV export; confirmation dialogs for destructive actions; clear success/error toasts.

---

## 6. Database (main tables — refine as needed)
`users`, `profiles`, `resumes`, `resume_skills`, `companies`, `job_sources`, `jobs` (with embedding vector), `saved_jobs`, `job_matches`, `interviews`, `interview_messages`, `reports`, `languages`, `frameworks`, `questions` (type: dsa / project / mcq / review), `question_templates` (starter code per language), `test_cases`, `test_suites`, `submissions`, `attempts`, `skill_scores`, `applications`, `application_events`, `reminders`, `llm_usage` (tokens, cost, latency, provider per call), `audit_logs`, `roles` / `user_roles`, `user_quotas`, `feature_flags`, `site_settings`, `prompt_templates` + `prompt_template_versions`, `llm_routing_rules`, `announcements`, `user_reports` (feedback/issue queue), `question_generation_queue`.

Use UUID primary keys, `created_at`/`updated_at` everywhere, proper indexes (including vector indexes), and foreign keys with sensible cascade rules.

---

## 7. API design
- REST under `/api/v1`, WebSocket under `/ws`.
- Auto-generated OpenAPI docs; generate a typed TypeScript client for the frontend from the OpenAPI schema.
- Consistent error format, pagination (cursor-based for jobs), filtering and sorting.
- **Idempotency keys** on submissions and other non-repeatable POSTs.
- Main groups: `auth`, `users/me`, `resumes`, `jobs`, `matches`, `interviews`, `problems`, `submissions`, `tests`, `reports`, `applications`, `dashboard`, `admin`.

---

## 8. Security
- Code sandbox: no network, CPU/memory/time limits, non-root user, read-only filesystem except a temp dir, output size limits.
- JWT auth with short-lived access tokens + refresh tokens; RBAC roles: `super_admin`, `admin`, `content_editor`, `support`, `user` (see Module 8), enforced on the backend for every endpoint.
- All admin actions audited; destructive admin actions require confirmation.
- Redis rate limiting per user and per endpoint (token bucket); stricter limits on LLM and code-execution endpoints.
- Input validation everywhere (Pydantic); file upload limits and type checks for resumes.
- Basic prompt-injection defenses for content coming from resumes and job descriptions (treat them as data, never as instructions).
- Secrets only via environment variables; OWASP Top 10 checklist in docs.

---

## 9. AI layer requirements
- One `LLMProvider` interface; implementations: Ollama, GitHub Models, OpenRouter, Mock.
- Router: pick provider/model by task (cheap/local for parsing, stronger for interviews and reports); automatic **fallback** on error or timeout; **circuit breaker** per provider.
- **Caching:** exact-match cache in Redis; optional semantic cache with pgvector.
- Log every call to `llm_usage` (provider, model, tokens, latency, estimated cost, success).
- All prompts live in versioned template files, not inline strings.
- Structured outputs validated with Pydantic, with retry on invalid JSON.
- A small **evals** suite (golden examples) for resume parsing, match scoring and report generation.

---

## 10. Design and UI

- **Brand feel:** clean, modern, calm and confident — inspired by flight and open sky (connects to Glide in Bir), but professional, not playful.
- **Colors:** a deep sky blue primary, a warm sunrise orange accent for calls to action, neutral slate grays; define them as design tokens. Full **light and dark mode**.
- **Typography:** one modern sans-serif (e.g., Inter or Geist) with a clear type scale.
- **Logo:** a simple wordmark "GlideUp" with a minimal upward glider/wing shape (original design, SVG).
- **Layout:** responsive (mobile first), sidebar navigation on desktop, bottom nav on mobile (PWA).
- **Pages:** Landing page (hero with tagline, feature highlights, how-it-works journey, CTA), Login, Onboarding (resume upload + preferences), Dashboard, Jobs (search + filters), Job detail (match score, skill gap, practice buttons), Interview room (chat/voice, timer, code editor or whiteboard panel), Tests (language and framework catalog), Test runner, Reports, Application tracker (Kanban), Profile (skills, badges), About (Sahil Thakur), Settings, and the **Admin Console** (Overview, Users, Jobs & Sources, Question Bank, AI Generation Queue, Interviews, Prompt Templates, AI/LLM Settings, Feature Flags, Site Content, Announcements, User Reports, System Health, Audit Logs).
- Polished states everywhere: loading skeletons, empty states with helpful guidance, error states with retry.
- Accessibility: keyboard navigation, focus states, proper contrast, ARIA labels.

---

## 11. Engineering standards

### Repository structure (monorepo)
```
glideup/
├── frontend/                 # Next.js app
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/             # config, security, rate limiting, logging
│   │   ├── db/               # models, session, migrations
│   │   ├── api/v1/           # routers
│   │   ├── ws/               # WebSocket handlers
│   │   ├── modules/          # profile, jobs, matching, interviews, tests, tracker, dashboard, admin
│   │   ├── llm/              # providers, router, prompts, cache, evals
│   │   ├── jobsources/       # Greenhouse, Lever, Ashby, Adzuna, ... plugins
│   │   ├── sandbox/          # Judge0/Piston client, framework test runners
│   │   └── workers/          # Celery tasks and schedules
│   └── tests/
├── sandbox-images/           # Dockerfiles for framework test runners
├── loadtest/                 # Locust scripts
├── docs/
│   ├── architecture.md       # diagrams (Mermaid)
│   └── adr/                  # Architecture Decision Records
├── docker-compose.yml
├── .env.example
└── README.md
```

### Quality
- Backend test coverage target: 80%+ on core modules (unit + integration, using test containers or a test DB).
- Frontend: component tests for key flows, plus a few Playwright end-to-end tests (login → upload resume → search job → start interview).
- Type-safe end to end (mypy, TypeScript strict mode).
- Meaningful commit messages; small, reviewable changes.

---

## 12. Documentation (part of the deliverable)
- **README:** what GlideUp is, screenshots/GIFs, architecture diagram, tech stack, how to run locally in one command, environment variables, and a "Built by Sahil Thakur" section.
- **ADRs** for key decisions, e.g.: modular monolith vs microservices; Postgres + pgvector vs a separate vector DB; Celery for background jobs; Judge0 for sandboxing; token bucket rate limiting; LLM provider abstraction and fallback.
- **Load test results** (Locust): requests/sec, p50/p95 latency, error rate, cache hit rate, and how fallback behaved when a provider was killed (chaos test).
- A short **"What I'd change at 10x / 100x scale"** section.

---

## 13. Build plan (follow this order)

| Phase | Scope | Done when |
|---|---|---|
| 1 | Monorepo, Docker Compose with all services, FastAPI + Next.js skeletons, Google login, DB + migrations, CI | I can log in and see an empty dashboard |
| 2 | Profile, resume upload to MinIO, Celery parsing, LLM provider layer (Ollama + Mock + fallback) | Uploading my resume shows parsed skills |
| 3 | Job source plugins (Greenhouse, Lever, Adzuna first), normalization, dedup, Meilisearch search UI | I can search real jobs with filters |
| 4 | Embeddings, match score, skill gap, recommendations | Each job shows a match % and missing skills |
| 5 | AI mock interview over WebSocket with streaming, interview types, feedback reports | I can finish a mock interview and read a report |
| 6 | Judge0 integration, language tests, question bank + auto-validation pipeline | I can solve a problem in 6 languages with hidden tests |
| 7 | Framework tests (mini-projects, review, MCQ, viva), skill scores and badges | I can take a React and a FastAPI test and get scored |
| 8 | Application tracker, reminders, dashboard, voice mode, PWA | Full user journey works end to end |
| 9 | Rate limiting, caching, observability (Prometheus/Grafana), security hardening | Grafana shows live metrics |
| 10 | Load and chaos tests, Playwright E2E, README, ADRs, polish UI, demo seed data | Project is portfolio-ready |

**Admin is built alongside each module, not at the end:** Phase 1 sets up roles, the `/admin` layout, audit logging and the overview page; every later phase adds the admin screens for the module it builds (e.g., Phase 3 adds Jobs & Sources admin, Phase 6 adds the Question Bank and AI Generation Queue). Phase 9 adds Feature Flags, AI/LLM Settings, System Health and Announcements.

**MVP priority:** Phases 1–5 first. A complete smaller product is better than a half-finished big one.

---

## 14. Later (not now — keep the design ready for it)
- Deploy to Azure (Container Apps or AKS, Azure Database for PostgreSQL, Azure Blob Storage, Azure OpenAI, Application Insights) — target in ~3 months.
- More languages and frameworks, more job sources.
- Optional React Native (Expo) mobile app using the same API.

---

## 15. How to work with me
- Before each phase, give a short plan (files to create, decisions to make). Then implement.
- After each phase: how to run it, what to test manually, and what's next.
- Ask me before adding any paid service or anything that can't run locally for free.
- Keep my laptop limits in mind: everything must run comfortably on 16 GB RAM (if I have less, prefer GitHub Models over local Ollama models).
