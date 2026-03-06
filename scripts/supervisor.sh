#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# AudioBook Supervisor
# Keeps BOTH the Telegram bot AND the audiobook backend
# running forever. Auto-restarts on crash.
#
# Usage:
#   nohup ./scripts/supervisor.sh > /dev/null 2>&1 &
#
# To stop everything:
#   kill $(cat data/logs/supervisor.pid)
#   # or:  pkill -f supervisor.sh
#
# Logs:
#   tail -f data/logs/telegram_bot.log
#   tail -f data/logs/epub_backend.log
#   tail -f data/logs/supervisor.log
# ─────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/apps"
EPUB_APP_DIR="$APP_DIR/epubToAudioBook"
LOG_DIR="$REPO_ROOT/data/logs"
PYTHON="/lhome/ahmadfn/.pyenv/versions/3.11.9/envs/Audio/bin/python"

EPUB_PORT="${EPUB_SERVICE_PORT:-8001}"

mkdir -p "$LOG_DIR" "$REPO_ROOT/data/books" "$REPO_ROOT/data/generated" "$LOG_DIR/generator"

SUP_LOG="$LOG_DIR/supervisor.log"
BOT_LOG="$LOG_DIR/telegram_bot.log"
BACKEND_LOG="$LOG_DIR/epub_backend.log"
PID_FILE="$LOG_DIR/supervisor.pid"

log() {
    echo "$(date '+%F %T') [supervisor] $*" | tee -a "$SUP_LOG"
}

# Save our PID so we can be killed cleanly
echo $$ > "$PID_FILE"
log "Supervisor started (PID $$)"

# Track child PIDs
BOT_PID=""
BACKEND_PID=""

cleanup() {
    log "Shutting down..."
    [[ -n "$BOT_PID" ]]     && kill "$BOT_PID" 2>/dev/null && log "Killed bot (PID $BOT_PID)"
    [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null && log "Killed backend (PID $BACKEND_PID)"
    wait 2>/dev/null
    rm -f "$PID_FILE"
    log "Supervisor stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ─── Start / monitor the audiobook backend ───
start_backend() {
    export ABS_WORKSPACE_ROOT="$REPO_ROOT"
    export ABS_DATA_DIR="$REPO_ROOT/data"
    export ABS_BOOKS_DIR="$REPO_ROOT/data/books"
    export ABS_OUTPUT_DIR="$REPO_ROOT/data/generated"
    export ABS_GENERATOR_LOG_DIR="$LOG_DIR/generator"

    log "Starting audiobook backend on port $EPUB_PORT ..."
    cd "$EPUB_APP_DIR"
    "$PYTHON" -m uvicorn app.backend.main:app \
        --host 0.0.0.0 \
        --port "$EPUB_PORT" \
        >> "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    log "Backend started (PID $BACKEND_PID)"
}

# ─── Start / monitor the telegram bot ───
start_bot() {
    log "Starting Telegram bot ..."
    cd "$APP_DIR"
    EPUB_SERVICE_PORT="$EPUB_PORT" "$PYTHON" telegram_bot.py \
        >> "$BOT_LOG" 2>&1 &
    BOT_PID=$!
    log "Bot started (PID $BOT_PID)"
}

# ─── Initial launch ───
start_backend
start_bot

# ─── Watchdog loop: check every 5s, restart crashed processes ───
while true; do
    sleep 5

    # Check backend
    if [[ -n "$BACKEND_PID" ]] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        wait "$BACKEND_PID" 2>/dev/null
        EXIT_CODE=$?
        log "Backend crashed (exit code $EXIT_CODE). Restarting in 3s..."
        sleep 3
        start_backend
    fi

    # Check bot
    if [[ -n "$BOT_PID" ]] && ! kill -0 "$BOT_PID" 2>/dev/null; then
        wait "$BOT_PID" 2>/dev/null
        EXIT_CODE=$?
        log "Bot crashed (exit code $EXIT_CODE). Restarting in 3s..."
        sleep 3
        start_bot
    fi
done
