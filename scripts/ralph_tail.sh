#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-coder}"
OS_NAME="$(uname -s)"
CURRENT_FILE=""
TAIL_PID=""

case "$MODE" in
    coder)
        PATTERNS=("/tmp/ralph_coder_"*.txt)
        ;;
    lead)
        PATTERNS=("/tmp/ralph_lead_"*.txt)
        ;;
    all)
        PATTERNS=("/tmp/ralph_coder_"*.txt "/tmp/ralph_lead_"*.txt)
        ;;
    *)
        echo "Usage: $0 [coder|lead|all]" >&2
        exit 1
        ;;
esac

mtime() {
    local file="$1"
    if [ "$OS_NAME" = "Darwin" ]; then
        stat -f %m "$file"
    else
        stat -c %Y "$file"
    fi
}

file_age() {
    local file="$1"
    local now
    now=$(date +%s)
    echo $((now - $(mtime "$file")))
}

mode_label() {
    local file="$1"
    case "$(basename "$file")" in
        ralph_coder_*.txt) echo "🤖 CODER" ;;
        ralph_lead_*.txt) echo "👔 LEAD" ;;
        *) echo "📡 OUTPUT" ;;
    esac
}

latest_file() {
    local files=()
    local pattern
    local file
    shopt -s nullglob
    for pattern in "${PATTERNS[@]}"; do
        for file in $pattern; do
            [ -f "$file" ] && files+=("$file")
        done
    done
    shopt -u nullglob

    [ "${#files[@]}" -gt 0 ] || return 1

    local latest=""
    local latest_mtime=-1
    local current_mtime
    for file in "${files[@]}"; do
        current_mtime=$(mtime "$file" 2>/dev/null || echo 0)
        if [ "$current_mtime" -gt "$latest_mtime" ]; then
            latest="$file"
            latest_mtime="$current_mtime"
        fi
    done

    [ -n "$latest" ] || return 1
    printf '%s\n' "$latest"
}

stop_tail() {
    if [ -n "${TAIL_PID:-}" ]; then
        kill "$TAIL_PID" 2>/dev/null || true
        wait "$TAIL_PID" 2>/dev/null || true
        TAIL_PID=""
    fi
}

start_tail() {
    local file="$1"
    local age
    age=$(file_age "$file")
    echo "━━━ $(mode_label "$file") | $(basename "$file") | age: ${age}s ━━━"
    tail -n 40 -f "$file" &
    TAIL_PID=$!
    CURRENT_FILE="$file"
}

cleanup() {
    stop_tail
}
trap cleanup EXIT INT TERM

while true; do
    newest=""
    if newest=$(latest_file 2>/dev/null); then
        if [ "$CURRENT_FILE" != "$newest" ]; then
            stop_tail
            if [ -n "$CURRENT_FILE" ]; then
                echo "🔄 Switched to: $(basename "$newest")"
            fi
            start_tail "$newest"
        fi
        sleep 5
    else
        stop_tail
        CURRENT_FILE=""
        echo "Waiting for ralph..."
        sleep 3
    fi
done
