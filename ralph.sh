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

cleanup() {
    rm -f "$PROJECT_DIR/ralph_codex.pid"
    rm -f "$PROJECT_DIR/ralph_main.pid"
}
trap cleanup EXIT

MAX_FIX_RETRIES=2
MAX_ATTEMPTS=$((MAX_FIX_RETRIES + 1))
SESSION_TOKENS=0
SESSION_TASKS=0
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
RALPH_LOG="$LOG_DIR/ralph_$(date +%Y-%m-%d).log"
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

# State management
write_state() {
    local status="$1" task="${2:-}" step="${3:-}" message="${4:-}"
    python3 -c "
import json
from datetime import datetime, timezone
state = {
    'status': '$status',
    'current_task': '$task',
    'current_phase_step': '$step',
    'last_update': datetime.now(timezone.utc).isoformat(),
    'message': '''$message''',
}
open('ralph_state.json','w').write(json.dumps(state, indent=2))
"
}

check_control() {
    if [ -f ralph_control.json ]; then
        ACTION=$(python3 -c "
import json
try:
    d = json.load(open('ralph_control.json'))
    print(d.get('action', 'continue'))
except: print('continue')
" 2>/dev/null || echo "continue")
        if [ "$ACTION" = "stop" ] || [ "$ACTION" = "stop_now" ]; then
            return 1
        fi
    fi
    return 0
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
log "🔍 Smoke test..."
if ! make test > /tmp/ralph_test.log 2>&1; then
    log "❌ Tests failing!"
    tail -20 /tmp/ralph_test.log
    alert_human "Tests broken before start. Fix manually."
fi
log "✅ Tests pass"
write_state "idle" "" "" "Ready"

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
    if ! check_control; then
        log "⏹ Stop signal received"
        write_state "stopped" "" "" "Stopped by user"
        notify "⏹ Ralph stopped by user"
        exit 0
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
    TASK_START=$(date +%s)

    log "📋 Task: $TASK_ID — $TASK_TITLE"
    log "📋 TASK_START task_id=$TASK_ID title=\"$TASK_TITLE\" timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "⏱  Timeout: ${TASK_TIMEOUT}s"

    FIX_RETRY=0
    TASK_DONE=false
    FIX_INSTRUCTIONS=""
    TASK_TOKENS=0

    while [ "$FIX_RETRY" -le "$MAX_FIX_RETRIES" ] && [ "$TASK_DONE" = false ]; do

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

        CODER_PROMPT="Read AGENTS.md and AGENTS_CODER.md first. Then read progress.md.
Run make test to verify current state.

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
- Implement ONLY this task
- Follow acceptance_criteria exactly
- make test must pass
- Do NOT modify tasks.json or progress.md
- Commit: feat($TASK_ID): $TASK_TITLE"

        PRE_HASH=$(git rev-parse HEAD)

        CODER_OUTPUT="/tmp/ralph_coder_$$.txt"
        # Run codex, capture PID of gtimeout for kill support
        gtimeout --foreground --kill-after=10 "$TASK_TIMEOUT" \
            codex exec -s danger-full-access "$CODER_PROMPT" \
            > >(tee "$CODER_OUTPUT") 2>&1 &
        CODEX_PID=$!
        echo "$CODEX_PID" > "$PROJECT_DIR/ralph_codex.pid"
        log "Codex PID: $CODEX_PID"
        set +e
        wait $CODEX_PID
        CODEX_EXIT=$?
        set -e
        rm -f "$PROJECT_DIR/ralph_codex.pid"
        if [ "$CODEX_EXIT" -eq 124 ]; then
            log "⏰ TIMEOUT: codex exceeded ${TASK_TIMEOUT}s"
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

        # ═══ TECH LEAD ═══
        log "───────────────────────────────────────────"
        log "👔 TECH LEAD — Reviewing"
        log "───────────────────────────────────────────"
        log "👔 [TECH LEAD] Reviewing..."
        write_state "running" "$TASK_ID" "tech_lead" "Tech Lead reviewing..."
        LEAD_START=$(date +%s)

        LEAD_PROMPT="Read AGENTS_LEAD.md first.

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

        REVIEW_FILE="/tmp/ralph_review_$$.txt"
        LEAD_OUTPUT="/tmp/ralph_lead_$$.txt"
        gtimeout --foreground --kill-after=10 "$TASK_TIMEOUT" \
            codex exec -s danger-full-access -o "$REVIEW_FILE" "$LEAD_PROMPT" \
            > >(tee "$LEAD_OUTPUT") 2>&1 &
        CODEX_PID=$!
        echo "$CODEX_PID" > "$PROJECT_DIR/ralph_codex.pid"
        log "Lead PID: $CODEX_PID"
        set +e
        wait $CODEX_PID
        CODEX_EXIT=$?
        set -e
        rm -f "$PROJECT_DIR/ralph_codex.pid"
        if [ "$CODEX_EXIT" -eq 124 ]; then
            log "⏰ TIMEOUT: codex exceeded ${TASK_TIMEOUT}s"
        fi
        LEAD_TOKENS=$(extract_tokens "$LEAD_OUTPUT")
        TASK_TOKENS=$((TASK_TOKENS + ${LEAD_TOKENS:-0}))
        SESSION_TOKENS=$((SESSION_TOKENS + ${LEAD_TOKENS:-0}))
        log "💰 [LEAD]  Tokens: $(format_tokens "$LEAD_TOKENS") | Task total: $(format_tokens "$TASK_TOKENS") | Session total: $(format_tokens "$SESSION_TOKENS")"
        LEAD_DURATION=$(( $(date +%s) - LEAD_START ))
        log "⏱️ Tech Lead took ${LEAD_DURATION}s"
        REVIEW=$(cat "$REVIEW_FILE" 2>/dev/null || echo '{"decision":"alert","alert_reason":"No output"}')
        log "🔍 DEBUG: Review first 200 chars: $(echo "$REVIEW" | head -c 200)"

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
                git add -A
                git commit -m "feat($TASK_ID): $TASK_TITLE [ralph]" 2>/dev/null || true
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

    if [ "$TASK_DONE" = false ]; then
        REASON="$TASK_ID failed after $MAX_FIX_RETRIES retries"
        log "📋 TASK_FAIL task_id=$TASK_ID status=alert reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        alert_human "$REASON"
        break
    fi

    [ "$MODE" = "task" ] && break

    if [ "$MODE" = "phase" ]; then
        REMAINING=$(python3 "$RALPH_DIR/scripts/next_task.py" --phase "$TARGET" 2>/dev/null || echo "null")
        [ "$REMAINING" = "null" ] && { log "🎉 Phase $TARGET complete!"; break; }
    fi
done

write_state "idle" "" "" "All tasks complete"
notify "🎉 Ralph finished! Run /status for details."
log "════════════════════════════════════════════════════"
log "💰 SESSION TOTAL: ${SESSION_TASKS} tasks, ~$(format_tokens "$SESSION_TOKENS") tokens (~\$$(estimate_cost "$SESSION_TOKENS"))"
log "════════════════════════════════════════════════════"
log "📊 Final:"
"$RALPH_DIR"/"ralph.sh" status
