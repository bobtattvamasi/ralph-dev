#!/usr/bin/env bash
set -euo pipefail

# Ralph v3 — Project-agnostic AI dev team orchestrator
# RALPH_DIR = where ralph.sh lives (ralph-dev/)
# PROJECT_DIR = where the project lives (has tasks.json, AGENTS.md)

MODE="${1:-status}"
TARGET="${2:-}"
EXTRA="${3:-}"

RALPH_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "./tasks.json" ]; then
    PROJECT_DIR="$(pwd)"
elif [ -f "$RALPH_DIR/../tasks.json" ]; then
    PROJECT_DIR="$(cd "$RALPH_DIR/.." && pwd)"
else
    echo "❌ No tasks.json found. Run from project dir or run ralph-init.sh first."
    exit 1
fi

cd "$PROJECT_DIR"
export RALPH_PROJECT_DIR="$PROJECT_DIR"

kill_tree() {
    local pid="${1:-}"

    # Guard rails: ignore empty/non-numeric/system pids.
    [ -n "$pid" ] || return 0
    case "$pid" in
        ''|*[!0-9]*) return 0 ;;
    esac
    [ "$pid" -gt 1 ] 2>/dev/null || return 0
    kill -0 "$pid" 2>/dev/null || return 0

    # Preferred path: recurse by direct children (pgrep -P).
    if command -v pgrep >/dev/null 2>&1; then
        local child
        for child in $(pgrep -P "$pid" 2>/dev/null || true); do
            kill_tree "$child"
        done
    fi

    # Hard kill with retries to avoid stale lingering processes.
    local attempt
    for attempt in 1 2 3; do
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
        kill -0 "$pid" 2>/dev/null || return 0
    done
    kill -9 "$pid" 2>/dev/null || true
}

CLEANUP_RUNNING=0
cleanup() {
    # Prevent recursive cleanup (explicit call + trap).
    if [ "${CLEANUP_RUNNING:-0}" -eq 1 ]; then
        return 0
    fi
    CLEANUP_RUNNING=1

    local codex_pid=""
    local main_pid=""

    if [ -f "$PROJECT_DIR/ralph_codex.pid" ]; then
        codex_pid=$(cat "$PROJECT_DIR/ralph_codex.pid" 2>/dev/null || echo "")
    fi
    if [ -f "$PROJECT_DIR/ralph_main.pid" ]; then
        main_pid=$(cat "$PROJECT_DIR/ralph_main.pid" 2>/dev/null || echo "")
    fi

    # 1) Kill codex tree first.
    [ -n "$codex_pid" ] && kill_tree "$codex_pid"

    # 2) Kill all direct children of current orchestrator shell.
    if command -v pgrep >/dev/null 2>&1; then
        local child
        for child in $(pgrep -P "$$" 2>/dev/null || true); do
            kill_tree "$child"
        done
    fi

    # 3) Kill main tree from pid-file if it points to another process.
    # If it is this shell, only children are killed to allow clean EXIT flow.
    if [ -n "$main_pid" ] && [ "$main_pid" != "$$" ]; then
        kill_tree "$main_pid"
    fi

    rm -f "$PROJECT_DIR/ralph_codex.pid"
    rm -f "$PROJECT_DIR/ralph_main.pid"
}
handle_interrupt() {
    log "⛔ Interrupt signal received, stopping Ralph..."
    write_state "stopped" "" "" "Interrupted by signal"
    notify "⛔ Ralph interrupted by signal and stopped"
    cleanup
    exit 130
}
trap cleanup EXIT
trap handle_interrupt INT TERM

MAX_FIX_RETRIES=2
MAX_ATTEMPTS=$((MAX_FIX_RETRIES + 1))
MAX_CODEX_RETRIES=3
CODEX_RETRY_DELAYS=(60 120 300)
RATE_LIMIT_PAUSE=1800
CONSECUTIVE_FAILURES=0
MAX_CONSECUTIVE_FAILURES=3
DEFAULT_MODEL=""
MINI_MODEL="codex-mini"
SESSION_TOKENS=0
SESSION_TASKS=0
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
RALPH_LOG="$LOG_DIR/ralph_$(date +%Y-%m-%d).log"
METRICS_FILE="$LOG_DIR/metrics.csv"
[ ! -f "$METRICS_FILE" ] && echo "timestamp,task_id,status,duration_s,attempts,files_changed,quality,cost_est" > "$METRICS_FILE"
find "$LOG_DIR" -name "ralph_*.log" -mtime +2 -delete 2>/dev/null || true
echo "$$" > "$PROJECT_DIR/ralph_main.pid"

log() {
    local msg="[ralph] $(date +%H:%M:%S) $*"
    echo "$msg"
    echo "$msg" >> "$RALPH_LOG"
}

extract_tokens() {
    local output_file="$1"
    local tokens
    tokens=$(grep -A1 "tokens used" "$output_file" 2>/dev/null | tail -1 | tr -cd '0-9')
    echo "${tokens:-0}"
}

format_tokens() {
    python3 -c "print(f'{int(${1:-0}):,}')"
}

estimate_cost() {
    python3 -c "print(f'{(int(${1:-0}) * 3 / 1000000):.2f}')"
}

log_metrics() {
    local status="$1"
    local end_time=$(date +%s)
    local duration=$((end_time - TASK_START))
    local files=$(git diff --name-only "$PRE_HASH" HEAD 2>/dev/null | wc -l | tr -d ' ')
    local cost=$(estimate_cost "$TASK_TOKENS")
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),$TASK_ID,$status,$duration,$FIX_RETRY,$files,$QUALITY,$cost" >> "$METRICS_FILE"
}

# State management
write_state() {
    local status="$1" task="${2:-}" step="${3:-}" message="${4:-}"
    python3 -c "
import json, os, tempfile
from datetime import datetime, timezone
state = {
    'status': '$status',
    'current_task': '$task',
    'current_phase_step': '$step',
    'last_update': datetime.now(timezone.utc).isoformat(),
    'message': '''$message''',
}
fd, tmp_path = tempfile.mkstemp(prefix='ralph_state_', suffix='.tmp', dir='.')
with os.fdopen(fd, 'w', encoding='utf-8') as f:
    f.write(json.dumps(state, indent=2))
os.replace(tmp_path, 'ralph_state.json')
"
}

CONTROL_ACTION="continue"
CONTROL_TARGET=""
check_control() {
    while true; do
        if [ -f ralph_control.json ]; then
            local control_data
            control_data=$(python3 -c "
import json
try:
    d = json.load(open('ralph_control.json'))
    print(d.get('action', 'continue'))
    print(d.get('comment', ''))
except:
    print('continue')
    print('')
" 2>/dev/null || printf "continue\n\n")
            CONTROL_ACTION=$(printf '%s\n' "$control_data" | sed -n '1p')
            CONTROL_TARGET=$(printf '%s\n' "$control_data" | sed -n '2p')
            if [ "$CONTROL_ACTION" = "stop" ] || [ "$CONTROL_ACTION" = "stop_now" ]; then
                return 1
            fi
            if [ "$CONTROL_ACTION" = "skip" ]; then
                return 2
            fi
            if [ "$CONTROL_ACTION" = "pause" ]; then
                log "⏸ Paused by user, waiting for resume..."
                write_state "paused" "" "" "Paused by user"
                while [ "$CONTROL_ACTION" = "pause" ]; do
                    sleep 5
                    control_data=$(python3 -c "
import json
try:
    d = json.load(open('ralph_control.json'))
    print(d.get('action', 'continue'))
    print(d.get('comment', ''))
except:
    print('continue')
    print('')
" 2>/dev/null || printf "continue\n\n")
                    CONTROL_ACTION=$(printf '%s\n' "$control_data" | sed -n '1p')
                    CONTROL_TARGET=$(printf '%s\n' "$control_data" | sed -n '2p')
                done
                if [ "$CONTROL_ACTION" = "continue" ]; then
                    write_state "running" "${TASK_ID:-}" "" "Resumed by user"
                    CONTROL_TARGET=""
                    return 0
                fi
                continue
            fi
        fi
        CONTROL_ACTION="continue"
        CONTROL_TARGET=""
        return 0
    done
}

clear_control_action() {
    python3 -c "
import json
from pathlib import Path
p = Path('ralph_control.json')
if p.exists():
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        d = {}
    d['action'] = 'continue'
    d['comment'] = ''
    p.write_text(json.dumps(d, indent=2), encoding='utf-8')
" 2>/dev/null || true
}

skip_current_task() {
    local reason="Skipped by user via Telegram"
    log "⏭ Skip signal received for $TASK_ID"
    python3 "$RALPH_DIR/scripts/update_task.py" "$TASK_ID" skipped "$reason" >/dev/null 2>&1 || true
    write_state "running" "$TASK_ID" "skipped" "$reason"
    notify "⏭ $TASK_ID skipped by user"
    clear_control_action
}

get_human_comment() {
    if [ -f ralph_control.json ]; then
        python3 -c "
import json
try:
    d = json.load(open('ralph_control.json'))
    c = d.get('comment', '')
    if c:
        print(c)
        d['comment'] = ''
        open('ralph_control.json','w').write(json.dumps(d))
except: pass
" 2>/dev/null || true
    fi
}

notify() {
    python3 "$RALPH_DIR/scripts/ralph_notify.py" "$*" >/dev/null 2>&1 || true
}

RECOVERY_MODE=0
PREV_STATUS=""
check_and_recover_state() {
    local state_file=""
    local stale_main_pid=""
    local stale_codex_pid=""

    # Prefer hidden state file if present, then regular state file.
    if [ -f ".ralph_state.json" ]; then
        state_file=".ralph_state.json"
    elif [ -f "ralph_state.json" ]; then
        state_file="ralph_state.json"
    fi

    if [ -n "$state_file" ]; then
        PREV_STATUS=$(python3 -c "
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    d = json.loads(p.read_text(encoding='utf-8'))
    print(d.get('status', 'unknown'))
except Exception:
    print('unknown')
" "$state_file" 2>/dev/null || echo "unknown")
    fi

    if [ -n "$PREV_STATUS" ] && [ "$PREV_STATUS" != "idle" ] && [ "$PREV_STATUS" != "stopped" ]; then
        RECOVERY_MODE=1
        log "⚠️ Auto-recovery: previous non-idle state detected ('$PREV_STATUS')"
        notify "⚠️ Auto-recovery: previous run detected as crashed. Resuming..."
    else
        RECOVERY_MODE=0
    fi

    # If previous run appears crashed/hung, kill stale process trees from pid files.
    if [ -f "$PROJECT_DIR/ralph_main.pid" ]; then
        stale_main_pid=$(cat "$PROJECT_DIR/ralph_main.pid" 2>/dev/null || echo "")
        case "$stale_main_pid" in
            ''|*[!0-9]*) stale_main_pid="" ;;
        esac
        if [ -n "$stale_main_pid" ] && [ "$stale_main_pid" != "$$" ]; then
            if kill -0 "$stale_main_pid" 2>/dev/null; then
                if [ "$RECOVERY_MODE" -eq 1 ]; then
                    log "⚠️ Found stale ralph_main.pid=$stale_main_pid, killing process tree"
                    kill_tree "$stale_main_pid"
                else
                    log "ℹ️ Found active ralph_main.pid=$stale_main_pid (leaving as-is)"
                fi
            else
                log "ℹ️ Removing dead ralph_main.pid ($stale_main_pid)"
            fi
        fi
    fi

    if [ -f "$PROJECT_DIR/ralph_codex.pid" ]; then
        stale_codex_pid=$(cat "$PROJECT_DIR/ralph_codex.pid" 2>/dev/null || echo "")
        case "$stale_codex_pid" in
            ''|*[!0-9]*) stale_codex_pid="" ;;
        esac
        if [ -n "$stale_codex_pid" ]; then
            if kill -0 "$stale_codex_pid" 2>/dev/null; then
                if [ "$RECOVERY_MODE" -eq 1 ]; then
                    log "⚠️ Found stale ralph_codex.pid=$stale_codex_pid, killing process tree"
                    kill_tree "$stale_codex_pid"
                fi
            else
                log "ℹ️ Removing dead ralph_codex.pid ($stale_codex_pid)"
            fi
        fi
    fi

    # Ensure stale pid files are removed after recovery check.
    rm -f "$PROJECT_DIR/ralph_codex.pid"
    rm -f "$PROJECT_DIR/ralph_main.pid"
    echo "$$" > "$PROJECT_DIR/ralph_main.pid"
}

file_mtime() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo 0
        return 0
    fi
    stat -f %m "$file" 2>/dev/null || stat -c %Y "$file" 2>/dev/null || echo 0
}

run_codex_watchdog() {
    local output_file="$1"
    local target_pid="$2"
    local stale_timeout="${3:-300}"
    local fired_flag="$4"
    local last_activity
    local last_mtime
    local now

    # Keep a tail follower running so output stream activity is continuously observed.
    tail -n 0 -f "$output_file" >/dev/null 2>&1 &
    local tail_pid=$!

    last_activity=$(date +%s)
    last_mtime=$(file_mtime "$output_file")

    while kill -0 "$target_pid" 2>/dev/null; do
        sleep 5
        now=$(date +%s)

        local current_mtime
        current_mtime=$(file_mtime "$output_file")
        if [ "$current_mtime" -gt "$last_mtime" ]; then
            last_mtime="$current_mtime"
            last_activity="$now"
        fi

        # 300s watchdog timeout window.
        if [ $((now - last_activity)) -ge "$stale_timeout" ]; then
            log "Watchdog timeout - killing stale codex process"
            notify "🚨 Watchdog timeout - killing stale codex process. Task: ${TASK_ID:-unknown}"

            if [ -f "$PROJECT_DIR/ralph_codex.pid" ]; then
                local stale_pid
                stale_pid=$(cat "$PROJECT_DIR/ralph_codex.pid" 2>/dev/null || echo "")
                if [ -n "$stale_pid" ]; then
                    kill -KILL "$stale_pid" 2>/dev/null || true
                    pkill -P "$stale_pid" 2>/dev/null || true
                fi
            fi

            kill -KILL "$target_pid" 2>/dev/null || true
            pkill -P "$target_pid" 2>/dev/null || true
            echo "watchdog_fired" > "$fired_flag"
            break
        fi
    done

    kill "$tail_pid" 2>/dev/null || true
    wait "$tail_pid" 2>/dev/null || true
}

run_codex() {
    local prompt="$1"
    local output_file="$2"
    local review_file="${3:-}"
    local timeout="$4"
    local model="${5:-}"
    local retry=0
    local exit_code=0
    local watchdog_timeout=300

    while [ $retry -le $MAX_CODEX_RETRIES ]; do
        : > "$output_file"
        local watchdog_flag
        watchdog_flag="/tmp/ralph_watchdog_${$}_${retry}.flag"
        rm -f "$watchdog_flag"
        set +e
        if [ -n "$review_file" ]; then
            (
                export GIT_EDITOR=true
                export GIT_TERMINAL_PROMPT=0
                export GIT_AUTHOR_NAME='Ralph Coder'
                export GIT_AUTHOR_EMAIL='ralph@dev'
                gtimeout --foreground --kill-after=10 "$timeout" \
                    codex exec -s danger-full-access ${model:+-m "$model"} -o "$review_file" "$prompt" \
                    > "$output_file" 2>&1
            ) &
        else
            (
                export GIT_EDITOR=true
                export GIT_TERMINAL_PROMPT=0
                export GIT_AUTHOR_NAME='Ralph Coder'
                export GIT_AUTHOR_EMAIL='ralph@dev'
                gtimeout --foreground --kill-after=10 "$timeout" \
                    codex exec -s danger-full-access ${model:+-m "$model"} "$prompt" \
                    > "$output_file" 2>&1
            ) &
        fi
        local codex_pid=$!
        echo "$codex_pid" > "$PROJECT_DIR/ralph_codex.pid"
        run_codex_watchdog "$output_file" "$codex_pid" "$watchdog_timeout" "$watchdog_flag" &
        local watchdog_pid=$!

        wait "$codex_pid"
        exit_code=$?
        kill "$watchdog_pid" 2>/dev/null || true
        wait "$watchdog_pid" 2>/dev/null || true
        set -e

        local watchdog_fired=0
        if [ -s "$watchdog_flag" ]; then
            watchdog_fired=1
        fi
        rm -f "$watchdog_flag"

        rm -f "$PROJECT_DIR/ralph_codex.pid"
        pkill -P "$$" 2>/dev/null || true

        # Watchdog timeout - retry with backoff like other recoverable errors.
        if [ "$watchdog_fired" -eq 1 ]; then
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            if [ $retry -lt $MAX_CODEX_RETRIES ]; then
                local wd_delay=${CODEX_RETRY_DELAYS[$retry]}
                log "⚠️ Watchdog triggered. Retry $((retry+1))/$MAX_CODEX_RETRIES in ${wd_delay}s..."
                notify "⚠️ Watchdog timeout on ${TASK_ID:-unknown}. Retrying in ${wd_delay}s..."
                sleep "$wd_delay"
                retry=$((retry + 1))
                continue
            fi
            return 1
        fi

        # Success
        if [ $exit_code -eq 0 ]; then
            CONSECUTIVE_FAILURES=0
            return 0
        fi

        # Timeout (124) - no retry, return as-is
        if [ $exit_code -eq 124 ]; then
            log "⏰ TIMEOUT: codex exceeded ${timeout}s"
            return 124
        fi

        # Check for rate limit in output
        if grep -qi 'rate.limit\|429\|throttl\|too many requests\|capacity' "$output_file" 2>/dev/null; then
            log "🚦 RATE LIMIT detected! Pausing ${RATE_LIMIT_PAUSE}s (30 min)..."
            notify "🚦 Rate limit hit. Pausing 30 min. Task: ${TASK_ID:-unknown}"
            write_state "paused" "${TASK_ID:-}" "rate_limit" "Rate limit - pausing 30 min"
            sleep $RATE_LIMIT_PAUSE
            write_state "running" "${TASK_ID:-}" "retry" "Resuming after rate limit pause"
            retry=$((retry + 1))
            continue
        fi

        # Other error - exponential backoff
        if [ $retry -lt $MAX_CODEX_RETRIES ]; then
            local delay=${CODEX_RETRY_DELAYS[$retry]}
            log "⚠️ Codex failed (exit $exit_code). Retry $((retry+1))/$MAX_CODEX_RETRIES in ${delay}s..."
            notify "⚠️ Codex error on ${TASK_ID:-unknown}. Retrying in ${delay}s..."
            sleep $delay
            retry=$((retry + 1))
        else
            log "❌ Codex failed after $MAX_CODEX_RETRIES retries"
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            return $exit_code
        fi
    done
    CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
    return 1
}

alert_human() {
    local reason="${1:-Unknown}"
    log ""
    log "🚨🚨🚨 HUMAN ATTENTION NEEDED 🚨🚨🚨"
    log "Task: ${TASK_ID:-N/A}"
    log "Reason: $reason"
    log "Last decision: ${DECISION:-N/A}"
    log "Review file: $(cat /tmp/ralph_review_$$.txt 2>/dev/null | head -5)"
    log ""
    notify "🚨 HUMAN NEEDED: ${TASK_ID:-N/A} — $reason"
    write_state "waiting_human" "${TASK_ID:-}" "alert" "$reason"
    printf '\a'
    echo "$(date): $reason" >> ralph_alerts.log
    osascript -e "display notification \"$reason\" with title \"Ralph Alert\"" 2>/dev/null || true
}

# ─── Status ───
if [ "$MODE" = "status" ]; then
    echo "=== Test Status ==="
    python3 -m pytest --tb=no -q 2>/dev/null | tail -1 || echo "tests not run"
    echo ""
    echo "=== Task Progress ==="
    python3 -c "
import json
d = json.load(open('tasks.json'))
tasks = d['tasks']
done = sum(1 for t in tasks if t['status'] == 'done')
total = len(tasks)
print(f'  Total: {done}/{total} tasks done')
for phase in sorted(set(str(t['phase']) for t in tasks)):
    pt = [t for t in tasks if str(t['phase']) == phase]
    pd = sum(1 for t in pt if t['status'] == 'done')
    print(f'  Phase {phase}: {pd}/{len(pt)}')
print()
pending = [t for t in tasks if t['status'] == 'pending']
if pending:
    print('Next pending:')
    for t in pending[:5]:
        print('  {} [{}] {}'.format(t['id'], t['priority'], t['title']))
"
    exit 0
fi

# ─── Redo ───
if [ "$MODE" = "redo" ]; then
    if [ -z "$TARGET" ]; then
        echo "Usage: ralph.sh redo <task_id> [revision notes]"
        exit 1
    fi
    python3 "$RALPH_DIR/scripts/update_task.py" "$TARGET" pending "${EXTRA:-Redo requested}"
    log "Task $TARGET reset to pending"
    exit 0
fi

# ─── Smoke test ───
check_and_recover_state

log "🔍 Smoke test..."
if ! make test > /tmp/ralph_test.log 2>&1; then
    log "❌ Tests failing!"
    tail -20 /tmp/ralph_test.log
    alert_human "Tests broken before start. Fix manually."
fi
log "✅ Tests pass"
if [ "$RECOVERY_MODE" -eq 1 ]; then
    write_state "running" "" "recovery" "Recovered from previous non-idle state ($PREV_STATUS)"
else
    write_state "idle" "" "idle" "Ready"
fi

# ─── Task selection args ───
NEXT_ARGS=""
case "$MODE" in
    task)
        [ -z "$TARGET" ] && { echo "Usage: ralph.sh task <id>"; exit 1; }
        NEXT_ARGS="--task $TARGET"
        ;;
    phase)
        [ -z "$TARGET" ] && { echo "Usage: ralph.sh phase <num>"; exit 1; }
        NEXT_ARGS="--phase $TARGET"
        ;;
    auto)
        NEXT_ARGS=""
        ;;
    *)
        echo "Usage: ralph.sh {task|phase|auto|redo|status} [target]"
        exit 1
        ;;
esac

# ─── Main loop ───
while true; do
    CONTROL_STATUS=0
    check_control || CONTROL_STATUS=$?
    if [ $CONTROL_STATUS -eq 1 ]; then
        log "⏹ Stop signal received"
        write_state "stopped" "" "" "Stopped by user"
        notify "⏹ Ralph stopped by user"
        cleanup
        exit 0
    elif [ $CONTROL_STATUS -eq 2 ]; then
        clear_control_action
    fi

    TASK_JSON=$(python3 "$RALPH_DIR/scripts/next_task.py" $NEXT_ARGS 2>/dev/null || echo "null")

    if [ "$TASK_JSON" = "null" ] || [ -z "$TASK_JSON" ]; then
        log "🎉 No more pending tasks!"
        break
    fi

    TASK_ID=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    TASK_TITLE=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['title'])")
    # Extract timeout from task (default 180s)
    TASK_TIMEOUT=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
print(task.get('timeout', 180))
" 2>/dev/null || echo "180")

    # Extract complexity (default: moderate)
    TASK_COMPLEXITY=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
print(task.get('complexity', 'moderate'))
" 2>/dev/null || echo "moderate")

    # Extract required_context files
    TASK_CONTEXT_FILES=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
files = task.get('required_context', [])
print(' '.join(files) if files else '')
" 2>/dev/null || echo "")

    # Select model based on complexity
    CODEX_MODEL=""
    if [ "$TASK_COMPLEXITY" = "simple" ]; then
        CODEX_MODEL="$MINI_MODEL"
        log "🧠 Model: codex-mini (simple task)"
    else
        log "🧠 Model: default (complexity: $TASK_COMPLEXITY)"
    fi

    log "📋 Complexity: $TASK_COMPLEXITY"
    TASK_START=$(date +%s)

    log "📋 Task: $TASK_ID — $TASK_TITLE"
    log "📋 TASK_START task_id=$TASK_ID title=\"$TASK_TITLE\" timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "⏱  Timeout: ${TASK_TIMEOUT}s"

    FIX_RETRY=0
    TASK_DONE=false
    TASK_SKIPPED=false
    FIX_INSTRUCTIONS=""
    TASK_TOKENS=0

    while [ "$FIX_RETRY" -le "$MAX_FIX_RETRIES" ] && [ "$TASK_DONE" = false ]; do
        CONTROL_STATUS=0
        check_control || CONTROL_STATUS=$?
        if [ $CONTROL_STATUS -eq 1 ]; then
            log "⏹ Stop signal received"
            write_state "stopped" "" "" "Stopped by user"
            notify "⏹ Ralph stopped by user"
            cleanup
            exit 0
        elif [ $CONTROL_STATUS -eq 2 ] && { [ -z "$CONTROL_TARGET" ] || [ "$CONTROL_TARGET" = "$TASK_ID" ]; }; then
            skip_current_task
            TASK_DONE=true
            TASK_SKIPPED=true
            break
        fi

        # ═══ CODER ═══
        CURRENT_ATTEMPT=$((FIX_RETRY + 1))
        log "═══════════════════════════════════════════"
        log "🤖 CODER — Attempt ${CURRENT_ATTEMPT}/${MAX_ATTEMPTS}"
        log "Task: ${TASK_ID} — ${TASK_TITLE}"
        log "═══════════════════════════════════════════"
        log "🤖 [CODER] Attempt $((FIX_RETRY+1))..."
        write_state "running" "$TASK_ID" "coder" "Coder implementing..."
        notify "🤖 [CODER] Starting: $TASK_ID — $TASK_TITLE"
        CODER_START=$(date +%s)

        # Inject memory context
        MEMORY_CORE=""
        MEMORY_RECENT=""
        if [ -f ".ralph/memory/core.md" ]; then
            MEMORY_CORE=$(cat .ralph/memory/core.md 2>/dev/null || true)
        fi
        if [ -f ".ralph/memory/recent.md" ]; then
            MEMORY_RECENT=$(cat .ralph/memory/recent.md 2>/dev/null || true)
        fi

        # Read required_context files
        CONTEXT_CONTENT=""
        if [ -n "$TASK_CONTEXT_FILES" ]; then
            for ctx_file in $TASK_CONTEXT_FILES; do
                if [ -f "$ctx_file" ]; then
                    CONTEXT_CONTENT="${CONTEXT_CONTENT}
## File: $ctx_file
$(cat "$ctx_file" 2>/dev/null | head -200)
"
                fi
            done
        fi

        PROJECT_ARCHITECTURE=""
        PROJECT_MEMORY_SYSTEM=""
        if [ -f "ARCHITECTURE.md" ]; then
            PROJECT_ARCHITECTURE=$(cat ARCHITECTURE.md 2>/dev/null || true)
        fi
        if [ -f "MEMORY_SYSTEM.md" ]; then
            PROJECT_MEMORY_SYSTEM=$(cat MEMORY_SYSTEM.md 2>/dev/null || true)
        fi

        CODER_PROMPT="Read AGENTS.md, ARCHITECTURE.md, MEMORY_SYSTEM.md, and AGENTS_CODER.md first. Then read progress.md.
Run make test to verify current state.

## Architecture Doc
${PROJECT_ARCHITECTURE:-No ARCHITECTURE.md provided. Use AGENTS.md and the repository structure.}

## Memory System Doc
${PROJECT_MEMORY_SYSTEM:-No MEMORY_SYSTEM.md provided. Use AGENTS.md and .ralph/memory/.}

## Project Context (from memory)
${MEMORY_CORE:-No core context yet. Read ARCHITECTURE.md and AGENTS.md for project info.}

## Recent Tasks (what was done before you)
${MEMORY_RECENT:-No recent tasks yet. This may be the first task.}

## Required Context Files
${CONTEXT_CONTENT:-No specific files required.}

## Your Task
$TASK_JSON"

        if [ -n "$FIX_INSTRUCTIONS" ]; then
            CODER_PROMPT="$CODER_PROMPT

## Fix Instructions from Tech Lead (MUST address)
$FIX_INSTRUCTIONS"
        fi

        HUMAN_COMMENT=$(get_human_comment)
        if [ -n "$HUMAN_COMMENT" ]; then
            CODER_PROMPT="$CODER_PROMPT

## Human Comment (from project owner via Telegram)
$HUMAN_COMMENT"
        fi

        CODER_PROMPT="$CODER_PROMPT

## Rules
- **Think before coding**: You MUST wrap your plan inside <thinking> tags before writing any code blocks. Briefly analyze the requirements and file structure there.
- Implement ONLY this task
- Follow acceptance_criteria exactly
- make test must pass
- Do NOT modify tasks.json or progress.md
- Commit: feat($TASK_ID): $TASK_TITLE

Expected response structure:
<thinking>
1. Need to modify app.py to add login route.
2. Will use flask-login library.
3. Need to update requirements.txt first.
</thinking>
\`\`\`python
... code ...
\`\`\`"

        PRE_HASH=$(git rev-parse HEAD)

        CODER_OUTPUT="/tmp/ralph_coder_$$.txt"
        set +e
        # run_codex handles retries/backoff for codex execution
        run_codex "$CODER_PROMPT" "$CODER_OUTPUT" "" "$TASK_TIMEOUT" "$CODEX_MODEL"
        CODEX_EXIT=$?
        set -e
        CONTROL_STATUS=0
        check_control || CONTROL_STATUS=$?
        if [ $CONTROL_STATUS -eq 1 ]; then
            log "⏹ Stop signal received"
            write_state "stopped" "" "" "Stopped by user"
            notify "⏹ Ralph stopped by user"
            cleanup
            exit 0
        elif [ $CONTROL_STATUS -eq 2 ] && { [ -z "$CONTROL_TARGET" ] || [ "$CONTROL_TARGET" = "$TASK_ID" ]; }; then
            skip_current_task
            TASK_DONE=true
            TASK_SKIPPED=true
            break
        fi
        CODER_TOKENS=$(extract_tokens "$CODER_OUTPUT")
        TASK_TOKENS=$((TASK_TOKENS + ${CODER_TOKENS:-0}))
        SESSION_TOKENS=$((SESSION_TOKENS + ${CODER_TOKENS:-0}))
        log "💰 [CODER] Tokens: $(format_tokens "$CODER_TOKENS") | Task total: $(format_tokens "$TASK_TOKENS") | Session total: $(format_tokens "$SESSION_TOKENS")"

        # Commit any unstaged changes the coder left behind
        if [ -n "$(git diff --name-only 2>/dev/null)" ] || [ -n "$(git diff --cached --name-only 2>/dev/null)" ]; then
            git add -A
            git commit -m "wip($TASK_ID): coder changes" 2>/dev/null || true
        fi
        CODER_DURATION=$(( $(date +%s) - CODER_START ))
        log "⏱️ Coder took ${CODER_DURATION}s"

        POST_HASH=$(git rev-parse HEAD)
        if [ "$PRE_HASH" = "$POST_HASH" ]; then
            GIT_DIFF="(no changes committed)"
        else
            GIT_DIFF=$(git diff "$PRE_HASH" HEAD -- ':!ralph.sh' ':!.ralph_state.json' ':!ralph_control.json' ':!ralph_alerts.log' 2>/dev/null | head -500 || echo "diff error")
        fi
        TEST_OUTPUT=$(make test 2>&1 | tail -40 || echo "tests failed")

        REVIEW_FILE="/tmp/ralph_review_$$.txt"
        LEAD_OUTPUT="/tmp/ralph_lead_$$.txt"

        # Skip lead review for trivial tasks
        SKIP_LEAD=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
tags = task.get('tags', [])
if 'trivial' in tags or task.get('skip_lead', False):
    print('true')
else:
    print('false')
" 2>/dev/null || echo "false")

        if [ "$SKIP_LEAD" = "true" ]; then
            log "⏭️ Skipping lead review (trivial task)"
            DECISION="approve"
            QUALITY="auto"
            REVIEW='{"decision":"approve","quality_score":"auto","progress_note":"Auto-approved trivial task"}'
            # Jump to decision handling — set vars that approve block needs
            LEAD_TOKENS=0
            LEAD_DURATION=0
        else
            # ═══ TECH LEAD ═══
            log "───────────────────────────────────────────"
            log "👔 TECH LEAD — Reviewing"
            log "───────────────────────────────────────────"
            log "👔 [TECH LEAD] Reviewing..."
            write_state "running" "$TASK_ID" "tech_lead" "Tech Lead reviewing..."
            LEAD_START=$(date +%s)

            LEAD_PROMPT="Read AGENTS.md, ARCHITECTURE.md, MEMORY_SYSTEM.md, and AGENTS_LEAD.md first.

## Task
$TASK_JSON

## Diff
\`\`\`diff
$GIT_DIFF
\`\`\`

## Tests
\`\`\`
$TEST_OUTPUT
\`\`\`

## Progress
$(head -30 progress.md 2>/dev/null || echo 'none')

Output ONLY a JSON object with your decision."

            set +e
            # run_codex handles retries/backoff for codex execution
            run_codex "$LEAD_PROMPT" "$LEAD_OUTPUT" "$REVIEW_FILE" "$TASK_TIMEOUT" "$CODEX_MODEL"
            CODEX_EXIT=$?
            set -e
            LEAD_TOKENS=$(extract_tokens "$LEAD_OUTPUT")
            TASK_TOKENS=$((TASK_TOKENS + ${LEAD_TOKENS:-0}))
            SESSION_TOKENS=$((SESSION_TOKENS + ${LEAD_TOKENS:-0}))
            log "💰 [LEAD]  Tokens: $(format_tokens "$LEAD_TOKENS") | Task total: $(format_tokens "$TASK_TOKENS") | Session total: $(format_tokens "$SESSION_TOKENS")"
            LEAD_DURATION=$(( $(date +%s) - LEAD_START ))
            log "⏱️ Tech Lead took ${LEAD_DURATION}s"
            REVIEW=$(cat "$REVIEW_FILE" 2>/dev/null || echo '{"decision":"alert","alert_reason":"No output"}')
            log "🔍 DEBUG: Review first 200 chars: $(echo "$REVIEW" | head -c 200)"
        fi

        CONTROL_STATUS=0
        check_control || CONTROL_STATUS=$?
        if [ $CONTROL_STATUS -eq 1 ]; then
            log "⏹ Stop signal received"
            write_state "stopped" "" "" "Stopped by user"
            notify "⏹ Ralph stopped by user"
            cleanup
            exit 0
        elif [ $CONTROL_STATUS -eq 2 ] && { [ -z "$CONTROL_TARGET" ] || [ "$CONTROL_TARGET" = "$TASK_ID" ]; }; then
            skip_current_task
            TASK_DONE=true
            TASK_SKIPPED=true
            break
        fi

        DECISION=$(echo "$REVIEW" | python3 -c "
import sys, json, re
text = sys.stdin.read().strip()
try:
    d = json.loads(text)
    print(d.get('decision', 'alert'))
    sys.exit(0)
except Exception:
    pass
m = re.search(r'\"decision\"\s*:\s*\"(\w+)\"', text)
if m:
    print(m.group(1))
else:
    print('alert')
" 2>/dev/null)
        DECISION="${DECISION:-alert}"
        DECISION=$(echo "$DECISION" | head -1)
        DECISION=$(echo "$DECISION" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        QUALITY=$(echo "$REVIEW" | python3 -c "
import sys, json
text = sys.stdin.read().strip()
try:
    d = json.loads(text)
    print(d.get('quality_score', '?'))
    sys.exit(0)
except Exception:
    pass
print('?')
" 2>/dev/null)
        QUALITY="${QUALITY:-?}"
        log "🔍 DEBUG: Raw DECISION='$DECISION' (${#DECISION} chars)"

        log "👔 Decision: $DECISION"
        log "───────────────────────────────────────────"
        log "📋 RESULT: ${DECISION} (quality: ${QUALITY}/10)"
        log "───────────────────────────────────────────"

        case "$DECISION" in
            approve)
                TASK_DONE=true
                write_state "running" "$TASK_ID" "approved" "Task approved"
                notify "✅ $TASK_ID done — $TASK_TITLE"
                PROGRESS_NOTE=$(echo "$REVIEW" | python3 -c "
import sys,json,re
text=sys.stdin.read()
for m in re.findall(r'\{[^{}]*\}',text,re.DOTALL):
    try:
        d=json.loads(m); n=d.get('progress_note','')
        if n: print(n); sys.exit(0)
    except: pass
print('Task completed')
" 2>/dev/null || echo "done")

                python3 "$RALPH_DIR/scripts/update_task.py" "$TASK_ID" done
                python3 "$RALPH_DIR/scripts/update_progress.py" "$TASK_ID" "$PROGRESS_NOTE"
                # Update memory with task summary
                CHANGED_FILES=$(git diff --name-only "$PRE_HASH" HEAD 2>/dev/null | tr '\n' ', ' | sed 's/,$//')
                python3 "$RALPH_DIR/scripts/update_memory.py" "$TASK_ID" "$TASK_TITLE" "${CHANGED_FILES:-none}" "approved" "${FIX_INSTRUCTIONS:-}" 2>/dev/null || true
                git add -A
                git commit -m "feat($TASK_ID): $TASK_TITLE [ralph]" 2>/dev/null || true
                log_metrics "success"
                log "✅ $TASK_ID done"
                TASK_DURATION=$(( $(date +%s) - TASK_START ))
                TOTAL="$TASK_DURATION"
                log "📋 TASK_DONE task_id=$TASK_ID status=approved quality=$QUALITY duration=${TOTAL}s attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                log "╔═══════════════════════════════════════════╗"
                log "║ ✅ TASK COMPLETE                          ║"
                log "║ Task:     ${TASK_ID}                       ║"
                log "║ Title:    ${TASK_TITLE}                    ║"
                log "║ Duration: ${TASK_DURATION}s                        ║"
                log "║ Attempts: ${CURRENT_ATTEMPT}/${MAX_ATTEMPTS}                 ║"
                log "║ Quality:  ${QUALITY}/10                    ║"
                log "╚═══════════════════════════════════════════╝"
                log "💰 Task $TASK_ID cost: ~$(format_tokens "$TASK_TOKENS") tokens (~\$$(estimate_cost "$TASK_TOKENS") at \$3/1M input)"
                SESSION_TASKS=$((SESSION_TASKS + 1))
                ;;

            fix)
                FIX_INSTRUCTIONS=$(echo "$REVIEW" | python3 -c "
import sys,json,re
text=sys.stdin.read()
for m in re.findall(r'\{[^{}]*\}',text,re.DOTALL):
    try:
        d=json.loads(m); f=d.get('fix_instructions','')
        if f: print(f); sys.exit(0)
    except: pass
print('Fix failing tests and unmet criteria')
" 2>/dev/null || echo "Fix the issues")

                FIX_RETRY=$((FIX_RETRY+1))
                notify "🔧 $TASK_ID fix needed ($FIX_RETRY/$MAX_FIX_RETRIES)"
                log "🔧 Fix $FIX_RETRY/$MAX_FIX_RETRIES: $FIX_INSTRUCTIONS"
                ;;

            reorder)
                NEW_TASK=$(echo "$REVIEW" | python3 -c "
import sys,json,re
text=sys.stdin.read()
for m in re.findall(r'\{[^{}]*\}',text,re.DOTALL):
    try:
        d=json.loads(m); n=d.get('next_task','')
        if n: print(n); sys.exit(0)
    except: pass
print('')
" 2>/dev/null || echo "")

                if [ -n "$NEW_TASK" ]; then
                    log "🔀 Reorder: do $NEW_TASK first"
                    NEXT_ARGS="--task $NEW_TASK"
                fi
                TASK_DONE=true
                ;;

            alert)
                REASON=$(echo "$REVIEW" | python3 -c "
import sys,json,re
text=sys.stdin.read()
for m in re.findall(r'\{[^{}]*\}',text,re.DOTALL):
    try:
        d=json.loads(m); r=d.get('alert_reason','')
        if r: print(r); sys.exit(0)
    except: pass
print('Unknown issue')
" 2>/dev/null || echo "Unknown")

                log_metrics "failed"
                log "📋 TASK_FAIL task_id=$TASK_ID status=alert reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                write_state "waiting_human" "$TASK_ID" "alert" "$REASON"
                alert_human "$REASON"
                break
                ;;

            *)
                log "⚠️ Unknown decision: '$DECISION' (length: ${#DECISION})"
                log "⚠️ Raw review output: $(head -5 /tmp/ralph_review_$$.txt 2>/dev/null)"
                REASON="Unknown tech lead decision: '$DECISION'"
                log "📋 TASK_FAIL task_id=$TASK_ID status=alert reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                alert_human "Unknown tech lead decision: '$DECISION'"
                break
                ;;
        esac
        rm -f "$REVIEW_FILE" "$CODER_OUTPUT" "$LEAD_OUTPUT"
    done

    if [ "$TASK_SKIPPED" = true ]; then
        [ "$MODE" = "task" ] && break
        continue
    fi

    if [ "$TASK_DONE" = false ]; then
        REASON="$TASK_ID failed after $MAX_FIX_RETRIES retries"
        log_metrics "failed"
        log "📋 TASK_FAIL task_id=$TASK_ID status=alert reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        alert_human "$REASON"
        break
    fi

    [ "$MODE" = "task" ] && break

    if [ "$MODE" = "phase" ]; then
        REMAINING=$(python3 "$RALPH_DIR/scripts/next_task.py" --phase "$TARGET" 2>/dev/null || echo "null")
        [ "$REMAINING" = "null" ] && { log "🎉 Phase $TARGET complete!"; break; }
    fi
    log "DEBUG: Finished task $TASK_ID, continuing to next..."
    # Circuit breaker check
    if [ $CONSECUTIVE_FAILURES -ge $MAX_CONSECUTIVE_FAILURES ]; then
        log "🔴 CIRCUIT BREAKER: $CONSECUTIVE_FAILURES consecutive failures!"
        notify "🔴 CIRCUIT BREAKER: $CONSECUTIVE_FAILURES consecutive failures. Ralph stopped."
        write_state "circuit_breaker" "" "" "$CONSECUTIVE_FAILURES consecutive failures"
        break
    fi
    continue
done

write_state "idle" "" "idle" "All tasks complete"
notify "🎉 Ralph finished! Run /status for details."
log "════════════════════════════════════════════════════"
log "💰 SESSION TOTAL: ${SESSION_TASKS} tasks, ~$(format_tokens "$SESSION_TOKENS") tokens (~\$$(estimate_cost "$SESSION_TOKENS"))"
log "════════════════════════════════════════════════════"
log "📊 Final:"
"$RALPH_DIR"/"ralph.sh" status
