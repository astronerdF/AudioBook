#!/usr/bin/env bash
# Start the Chrome Reader TTS server
# Uses the same venv as epubToAudioBook (shared Kokoro + torch deps)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV="$PROJECT_ROOT/apps/epubToAudioBook/.venv"

if [ -d "$VENV" ]; then
    source "$VENV/bin/activate"
fi

export KOKORO_DEVICE="${KOKORO_DEVICE:-cuda:0}"
export PORT="${PORT:-8008}"

echo "Starting Chrome Reader TTS server on port $PORT (device: $KOKORO_DEVICE)"
python "$SCRIPT_DIR/tts_server.py"
