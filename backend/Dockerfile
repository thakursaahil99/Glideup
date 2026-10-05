# syntax=docker/dockerfile:1.7
# One image runs the API, Celery worker, Celery beat and migrations (different commands).

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app

# --- dependencies (cached layer: only re-runs when the lockfile changes) ---
FROM base AS deps
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# --- runtime ---
FROM base AS runtime
RUN groupadd --system --gid 10001 glideup \
    && useradd --system --uid 10001 --gid glideup --no-create-home glideup
COPY --from=deps /opt/venv /opt/venv
COPY --chown=glideup:glideup alembic.ini ./
COPY --chown=glideup:glideup app ./app
COPY --chown=glideup:glideup --chmod=755 start.sh ./
USER glideup
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
