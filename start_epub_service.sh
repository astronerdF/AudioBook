#!/usr/bin/env bash
# Launch the EPUB-to-audiobook web service on port 8000.
# Activates the local virtualenv if present, then starts uvicorn.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$REPO_ROOT/epubToAudioBook"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Cannot find epubToAudioBook directory relative to this script." >&2
  exit 1
fi

cd "$APP_DIR"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

UVICORN_BIN="${UVICORN_BIN:-uvicorn}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-0}"
EXTRA_ARGS=()

if [[ "$RELOAD" == "1" ]]; then
  EXTRA_ARGS+=("--reload")
fi

exec "$UVICORN_BIN" epubToAudioBook.app.backend.main:app \
  --host "$HOST" \
  --port "$PORT" \
  "${EXTRA_ARGS[@]}"
