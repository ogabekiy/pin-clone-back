#!/bin/sh
set -e

echo "=== Pinterest Clone API Starting ==="

# Automatically run database migrations on server boot
echo "Applying database migrations (Alembic)..."
alembic upgrade head

echo "Starting FastAPI server on port 8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

