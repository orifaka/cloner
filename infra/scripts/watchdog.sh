#!/usr/bin/env bash
# Shared hosting cron: restart builder if dead
# crontab -e:
# */5 * * * * /bin/bash /path/to/cloner/infra/scripts/watchdog.sh

set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
LOG="$ROOT/bot.log"
PY="${PYTHON:-python3}"

if [ -x "$ROOT/../venv/bin/python" ]; then
  PY="$ROOT/../venv/bin/python"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/venv/bin/python" ]; then
  PY="$ROOT/venv/bin/python"
fi

if ! pgrep -f "python.*main.py" >/dev/null 2>&1; then
  echo "$(date -Is) watchdog: restarting main.py" >> "$LOG"
  nohup "$PY" main.py >> "$LOG" 2>&1 &
fi
