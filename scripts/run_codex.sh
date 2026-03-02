#!/usr/bin/env bash
set -euo pipefail

# Usage: run_codex.sh <timeout_sec> <output_file> <codex_args...>
TIMEOUT="${1:-}"
OUTPUT_FILE="${2:-}"
shift 2 || true

if [ -z "${TIMEOUT}" ] || [ -z "${OUTPUT_FILE}" ] || [ "$#" -eq 0 ]; then
    echo "Usage: run_codex.sh <timeout_sec> <output_file> <codex_args...>" >&2
    exit 2
fi

kill_session() {
    local sid="$1"
    pkill -TERM -s "$sid" 2>/dev/null || true
    sleep 5
    pkill -KILL -s "$sid" 2>/dev/null || true
}

setsid codex "$@" >"$OUTPUT_FILE" 2>&1 &
CODEX_PID=$!

(
    sleep "$TIMEOUT"
    if kill -0 "$CODEX_PID" 2>/dev/null; then
        kill_session "$CODEX_PID"
    fi
) &
WATCHDOG_PID=$!

set +e
wait "$CODEX_PID"
EXIT_CODE=$?
set -e

kill "$WATCHDOG_PID" 2>/dev/null || true
wait "$WATCHDOG_PID" 2>/dev/null || true

if [ "$EXIT_CODE" -gt 128 ]; then
    exit 124
fi
exit "$EXIT_CODE"
