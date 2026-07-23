#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SITE_DIR="${PROJECT_DIR}/site"
BOT_DIR="${PROJECT_DIR}/bot0"
PYTHON_BIN="${PYTHON_BIN:-${BOT_DIR}/venv/bin/python}"
GUNICORN_BIN="${GUNICORN_BIN:-${BOT_DIR}/venv/bin/gunicorn}"

cd "$PROJECT_DIR"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  . "$PROJECT_DIR/.env"
  set +a
fi

export POSTGRES_DB="${DB_NAME:-${POSTGRES_DB:-label}}"
export POSTGRES_USER="${DB_USER:-${POSTGRES_USER:-postgres}}"
export POSTGRES_PASSWORD="${DB_PASSWORD:-${POSTGRES_PASSWORD:-}}"
export POSTGRES_HOST="${DB_HOST:-${POSTGRES_HOST:-localhost}}"
export POSTGRES_PORT="${DB_PORT:-${POSTGRES_PORT:-5432}}"
export BOT_USERNAME="${BOT_USERNAME:-twaslabel_bot}"
export TELEGRAM_STORAGE_CHAT_ID="${TELEGRAM_STORAGE_CHAT_ID:--1003933025157}"
export MEDIA_STORAGE_ROOT="${MEDIA_STORAGE_ROOT:-${PROJECT_DIR}/storage}"
export BOT_TOKEN="${BOT_TOKEN:-$("$PYTHON_BIN" -c "import sys; sys.path.insert(0, '${BOT_DIR}'); from core.config import BOT_TOKEN; print(BOT_TOKEN)")}"

exec "$GUNICORN_BIN" \
  --chdir "$SITE_DIR" \
  --bind "${WEB_BIND:-127.0.0.1:5000}" \
  --workers "${WEB_WORKERS:-2}" \
  --threads "${WEB_THREADS:-4}" \
  --timeout "${WEB_TIMEOUT:-300}" \
  --access-logfile - \
  --error-logfile - \
  api:app
