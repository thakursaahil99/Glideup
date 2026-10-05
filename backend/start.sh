#!/bin/sh
# Single-container start for PaaS hosts (Render): migrate, seed reference data, serve on $PORT.
set -e
alembic upgrade head
python -m app.scripts.seed
export FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
