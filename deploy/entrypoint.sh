#!/bin/sh
# Apply DB migrations, then start the API. Runs migrations on every boot (safe:
# Alembic only applies what's pending). Seeding is a one-off, run manually.
set -e

echo "[entrypoint] Applying database migrations..."
alembic upgrade head

echo "[entrypoint] Starting uvicorn (single worker)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips='*'
