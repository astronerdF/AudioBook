#!/usr/bin/env bash
# Stop the Audiobookshelf server started via start_audiobookshelf.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$REPO_ROOT/data/logs/audiobookshelf/audiobookshelf.pid"

find_pids() {
  local pids=()
  if [[ -f "$PID_FILE" ]]; then
    local file_pid
    file_pid="$(tr -d '[:space:]' < "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$file_pid" ]]; then
      pids+=("$file_pid")
    fi
  fi

  # Fallback: search for the Audiobookshelf node process if PID file missing/stale
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(pgrep -f "node\s\+index\.js\s+--host" || true)

  # Remove duplicates
  printf '%s\n' "${pids[@]}" | awk '!seen[$0]++'
}

PIDS=($(find_pids))

if [[ ${#PIDS[@]} -eq 0 ]]; then
  echo "No running Audiobookshelf process found." >&2
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping Audiobookshelf (PIDs: ${PIDS[*]})..."
kill "${PIDS[@]}"

for _ in {1..10}; do
  alive=0
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      alive=1
      break
    fi
  done
  if [[ $alive -eq 0 ]]; then
    rm -f "$PID_FILE"
    echo "Audiobookshelf stopped."
    exit 0
  fi
  sleep 1
done

echo "Audiobookshelf did not exit gracefully; sending SIGKILL." >&2
kill -9 "${PIDS[@]}" 2>/dev/null || true
rm -f "$PID_FILE"

for pid in "${PIDS[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    echo "Warning: unable to terminate Audiobookshelf (PID $pid)." >&2
    exit 1
  fi
done

echo "Audiobookshelf stopped forcefully."
