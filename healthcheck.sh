#!/bin/bash
set -u
LOG="/home/dolepp/label/healthcheck.log"
BOT_PATTERN='^/home/dolepp/label/bot0/venv/bin/python /home/dolepp/label/bot0/main.py$'

if ! pgrep -f "$BOT_PATTERN" >/dev/null; then
    echo "$(date): ⚠️ Бот не запущен. Перезапуск через tmux..." >> "$LOG"
    if tmux has-session -t label-bot 2>/dev/null; then
        tmux send-keys -t label-bot C-c
        tmux send-keys -t label-bot 'cd /home/dolepp/label/bot0 && /home/dolepp/label/bot0/venv/bin/python /home/dolepp/label/bot0/main.py >> /home/dolepp/label/bot0/bot.runtime.log 2>&1' C-m
    else
        tmux new-session -d -s label-bot 'cd /home/dolepp/label/bot0 && /home/dolepp/label/bot0/venv/bin/python /home/dolepp/label/bot0/main.py >> /home/dolepp/label/bot0/bot.runtime.log 2>&1'
    fi
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:5000/api/health 2>/dev/null)
if [ "$HTTP_CODE" != "200" ]; then
    echo "$(date): ⚠️ API недоступен (код $HTTP_CODE). Нужен restart label-site." >> "$LOG"
    if command -v sudo >/dev/null 2>&1; then
        sudo -n systemctl restart label-site 2>>"$LOG" || true
    fi
fi
