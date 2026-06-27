#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/dolepp/label}"

chmod +x "$PROJECT_DIR/deploy/deploy-site.sh"
sudo cp "$PROJECT_DIR/deploy/label-site-deploy.service" /etc/systemd/system/label-site-deploy.service
sudo cp "$PROJECT_DIR/deploy/label-site-deploy.timer" /etc/systemd/system/label-site-deploy.timer
sudo systemctl daemon-reload
sudo systemctl enable --now label-site-deploy.timer
sudo systemctl start label-site-deploy.service
sudo systemctl status label-site-deploy.timer --no-pager
