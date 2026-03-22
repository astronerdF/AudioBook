#!/usr/bin/env bash
# Keepalive wrapper for the Telegram bot.
# Automatically restarts the bot if it crashes.
# Run with: nohup ./scripts/start_telegram_bot.sh &
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/apps"
PYTHON="/lhome/ahmadfn/.pyenv/versions/3.11.9/envs/Audio/bin/python"
LOG_FILE="$REPO_ROOT/data/logs/telegram_bot.log"

mkdir -p "$(dirname "$LOG_FILE")"

if [[ ! -x "$PYTHON" ]]; then
  echo "Error: Python not found at $PYTHON" >&2
  exit 1
fi

echo "$(date): Bot keepalive wrapper starting..." >> "$LOG_FILE"

while true; do
    echo "$(date): Starting telegram_bot.py ..." >> "$LOG_FILE"
    cd "$APP_DIR/telegram_bot"
    "$PYTHON" main.py >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    echo "$(date): Bot exited with code $EXIT_CODE. Restarting in 5s..." >> "$LOG_FILE"
    sleep 5
done
