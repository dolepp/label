#!/bin/bash
set -u
LOG="/home/dolepp/label/healthcheck.log"
BOT_PATTERN='^/home/dolepp/label/bot0/venv/bin/python /home/dolepp/label/bot0/main.py$'

if ! pgrep -f "$BOT_PATTERN" >/dev/null; then
    echo "$(date): ⚠️ Бот не запущен. Перезапуск через systemd..." >> "$LOG"
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user restart label-bot 2>>"$LOG" || systemctl restart label-bot 2>>"$LOG" || true
    fi
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://twaslabel.ru/api/health 2>/dev/null)
if [ "$HTTP_CODE" != "200" ]; then
    echo "$(date): ⚠️ API недоступен (код $HTTP_CODE)." >> "$LOG"
    if command -v sudo >/dev/null 2>&1; then
        sudo -n systemctl restart label-site 2>>"$LOG" || true
    fi
fi
