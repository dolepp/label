#!/usr/bin/env bash
set -euo pipefail

cd /home/dolepp/label

if [ -f /home/dolepp/label/bot0/.env ]; then
  set -a
  . /home/dolepp/label/bot0/.env
  set +a
fi

export POSTGRES_DB="${DB_NAME:-${POSTGRES_DB:-label}}"
export POSTGRES_USER="${DB_USER:-${POSTGRES_USER:-postgres}}"
export POSTGRES_PASSWORD="${DB_PASSWORD:-${POSTGRES_PASSWORD:-}}"
export POSTGRES_HOST="${DB_HOST:-${POSTGRES_HOST:-localhost}}"
export POSTGRES_PORT="${DB_PORT:-${POSTGRES_PORT:-5432}}"
export BOT_USERNAME="${BOT_USERNAME:-twaslabel_bot}"
export TELEGRAM_STORAGE_CHAT_ID="${TELEGRAM_STORAGE_CHAT_ID:--1003933025157}"
export MEDIA_STORAGE_ROOT="${MEDIA_STORAGE_ROOT:-/home/dolepp/label/storage}"
export BOT_TOKEN="${BOT_TOKEN:-$(/home/dolepp/label/bot0/venv/bin/python -c "import sys; sys.path.insert(0, '/home/dolepp/label/bot0'); from core.config import BOT_TOKEN; print(BOT_TOKEN)")}"

exec /home/dolepp/label/bot0/venv/bin/python -c "import sys; sys.path.insert(0, '/home/dolepp/label/site'); import api; api.app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)"
