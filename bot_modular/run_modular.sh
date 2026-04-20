#!/bin/bash
# Запуск модульной версии бота на сервере
cd "$(dirname "$0")"
echo "Stopping any existing bot..."
pkill -9 -f "python.*label" 2>/dev/null
pkill -9 -f "python.*main" 2>/dev/null
sleep 2
echo "Starting modular bot..."
nohup python3.11 main.py > bot_modular.out 2>&1 &
sleep 2
ps aux | grep -E "python.*main" | grep -v grep
echo "Log: tail -f $(pwd)/bot_modular.out"
