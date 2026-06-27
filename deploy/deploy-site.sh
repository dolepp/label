#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/dolepp/label}"
DEPLOY_USER="${DEPLOY_USER:-dolepp}"
BRANCH="${BRANCH:-main}"
SERVICE="${SERVICE:-label-site}"
LOCK_FILE="${LOCK_FILE:-/tmp/label-site-deploy.lock}"
DEPLOY_KEY="${DEPLOY_KEY:-/home/${DEPLOY_USER}/.ssh/github_label_deploy_ed25519}"

if [[ -z "${GIT_SSH_COMMAND:-}" && -f "$DEPLOY_KEY" ]]; then
  export GIT_SSH_COMMAND="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes"
fi

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

cd "$PROJECT_DIR"

git_cmd() {
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u "$DEPLOY_USER" env GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-}" git "$@"
  else
    git "$@"
  fi
}

before="$(git_cmd rev-parse HEAD)"
git_cmd fetch --quiet origin "$BRANCH"
after="$(git_cmd rev-parse "origin/$BRANCH")"

if [[ "$before" == "$after" ]]; then
  echo "No changes: $before"
  exit 0
fi

git_cmd reset --hard "$after"

if command -v systemctl >/dev/null 2>&1; then
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl restart "$SERVICE"
  else
    sudo -n systemctl restart "$SERVICE"
  fi
fi

echo "Deployed $before -> $after"
