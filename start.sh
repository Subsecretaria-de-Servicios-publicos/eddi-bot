#!/usr/bin/env bash
set -e

echo "Aplicando migraciones..."
alembic upgrade head

echo "Iniciando Gunicorn + Uvicorn..."
exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 120