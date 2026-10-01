# GlideUp architecture

GlideUp is a **modular monolith** (one FastAPI deployable with strict module boundaries), a
**Next.js** web app that also acts as a **backend-for-frontend**, and **Celery** workers for
anything slow or scheduled. Everything runs locally in Docker Compose; every external address
and secret comes from environment variables, so moving to Azure is a configuration change.

## System context

```mermaid
flowchart LR
    user([Job seeker / Admin])
    subgraph web[Next.js web app]
        pages[Pages & Server Components]
        authjs[Auth.js<br/>encrypted session cookie]
        bff["/api/backend/* proxy (BFF)"]
    end
    subgraph api[FastAPI modular monolith]
        auth[auth]
        users[users]
        admin[admin + audit]
        later["profile · jobs · matching · interviews · tests · tracker<br/>(phases 2–8)"]
    end
    workers[Celery workers + beat]
    pg[(PostgreSQL + pgvector)]
    redis[(Redis)]
    meili[(Meilisearch)]
    minio[(MinIO / S3)]
    mail[Mailpit]
    llm[[LLM gateway<br/>Ollama · GitHub Models · OpenRouter · Mock]]
    google[[Google OAuth]]

    user -- HTTPS --> pages
    user -- same-origin fetch --> bff
    authjs -- id_token --> google
    authjs -- "POST /auth/google, /auth/refresh" --> auth
    bff -- "Bearer access token" --> api
    api --> pg
    api --> redis
    api --> meili
    api --> minio
    redis --> workers
    workers --> pg
    workers --> llm
    workers --> mail
```

## Sign-in and token flow

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant N as Next.js (Auth.js)
    participant G as Google
    participant A as FastAPI
    B->>N: Continue with Google
    N->>G: OAuth code flow
    G-->>N: id_token
    N->>A: POST /api/v1/auth/google {id_token}
    A->>A: Verify signature (Google JWKS), aud, iss, exp, email_verified
    A->>A: Find/create user, apply ADMIN_EMAILS allowlist (audited)
    A-->>N: access (15 min) + refresh (14 days, single-use)
    N-->>B: Encrypted httpOnly session cookie (tokens never reach browser JS)
    B->>N: GET /api/backend/users/me
    N->>N: Token expiring? Refresh (deduplicated) and re-set cookie
    N->>A: GET /api/v1/users/me (Authorization: Bearer …)
    A-->>N: 200 JSON
    N-->>B: 200 JSON
```

Details and trade-offs: [ADR 0003](adr/0003-auth-tokens-and-bff.md).

## Backend layout

| Path | Responsibility |
|---|---|
| `app/core` | Settings, structured logging, error envelope, JWT, RBAC, request-ID middleware |
| `app/db` | SQLAlchemy base/mixins, async session, models, Alembic migrations |
| `app/api/v1` | HTTP routers — thin: validate, call a module service, shape the response |
| `app/modules/<name>` | Use-cases (services). Modules talk to each other only through service functions |
| `app/workers` | Celery app, schedules, cross-cutting tasks |

Rules: routers never contain business logic; services never import FastAPI; every privileged
change writes an `audit_logs` row **in the same transaction**.

## Request lifecycle (API)

1. `RequestContextMiddleware` assigns/propagates `X-Request-ID`, binds it to every log line.
2. `get_current_user` decodes the access token and **loads the user on every request**, so
   suspensions and role changes take effect immediately (not when the token expires).
3. `require_permission(...)` checks permissions (never role names) on the server.
4. `get_session` opens one transaction per request: commit on success, roll back on error.
5. Errors leave as `{"error": {code, message, details, request_id}}`.

## Data model (Phase 1)

```mermaid
erDiagram
    users ||--o{ user_roles : has
    roles ||--o{ user_roles : grants
    users ||--o{ refresh_tokens : owns
    users ||--o{ audit_logs : "acted (actor_id, nullable)"
    users {
        uuid id PK
        string email UK
        string google_sub UK
        enum status
        timestamptz last_login_at
    }
    roles { uuid id PK
        string name UK }
    user_roles { uuid user_id PK
        uuid role_id PK
        uuid granted_by_id }
    refresh_tokens { uuid id PK "= jti"
        uuid user_id FK
        timestamptz revoked_at
        uuid replaced_by_id }
    audit_logs { uuid id PK
        string action
        jsonb before
        jsonb after
        string request_id }
```

The `vector` extension is enabled in the first migration; embedding columns arrive in Phases 2 and 4.

## Cloud mapping (target, ~3 months)

| Local | Azure |
|---|---|
| Docker Compose services | Azure Container Apps (api, worker, beat, web) |
| PostgreSQL + pgvector | Azure Database for PostgreSQL Flexible Server (pgvector extension) |
| Redis | Azure Cache for Redis |
| MinIO | Azure Blob Storage (S3-compatible adapter or Blob client behind the storage interface) |
| Meilisearch | Meilisearch container on Container Apps (or Azure AI Search behind the search interface) |
| Ollama / GitHub Models | Azure OpenAI behind the same `LLMProvider` interface |
| Prometheus/Grafana + JSON logs | Azure Monitor / Application Insights |
