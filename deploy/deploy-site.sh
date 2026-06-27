#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/dolepp/label}"
BRANCH="${BRANCH:-main}"
SERVICE="${SERVICE:-label-site}"
LOCK_FILE="${LOCK_FILE:-/tmp/label-site-deploy.lock}"

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

cd "$PROJECT_DIR"

before="$(git rev-parse HEAD)"
git fetch --quiet origin "$BRANCH"
after="$(git rev-parse "origin/$BRANCH")"

if [[ "$before" == "$after" ]]; then
  echo "No changes: $before"
  exit 0
fi

git reset --hard "$after"

if command -v systemctl >/dev/null 2>&1; then
  sudo -n systemctl restart "$SERVICE" 2>/dev/null || systemctl restart "$SERVICE"
fi

echo "Deployed $before -> $after"
