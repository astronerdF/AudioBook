#!/usr/bin/env bash
# Start the Audiobookshelf Node server in the background with log capture.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/apps/audiobookshelf"
DATA_DIR="${DATA_DIR:-$REPO_ROOT/data}"
APP_DATA_DIR="$DATA_DIR/audiobookshelf"
LOG_DIR="$DATA_DIR/logs/audiobookshelf"
PID_FILE="$LOG_DIR/audiobookshelf.pid"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/audiobookshelf-$TIMESTAMP.log"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Cannot find audiobookshelf directory relative to this script." >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$APP_DATA_DIR/config" "$APP_DATA_DIR/metadata" "$APP_DATA_DIR/backups"

cd "$APP_DIR"

if [[ ! -d node_modules ]]; then
  echo "Installing dependencies (npm ci)..."
  npm ci
fi

if [[ ! -d client/dist ]]; then
  echo "Building client bundle (npm run client)..."
  npm run client
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-3333}"

if [[ -f "$PID_FILE" ]] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
  echo "Audiobookshelf appears to be running already (PID $(cat "$PID_FILE"))." >&2
  exit 1
fi

export CONFIG_PATH="$APP_DATA_DIR/config"
export METADATA_PATH="$APP_DATA_DIR/metadata"
export BACKUP_PATH="$APP_DATA_DIR/backups"
export LOG_OUTPUT_DIR="$LOG_DIR"

nohup npm start -- --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

echo "Audiobookshelf started on $HOST:$PORT (PID $PID). Logs: $LOG_FILE"
