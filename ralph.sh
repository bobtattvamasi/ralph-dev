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

kill_process_group() {
    local pid="${1:-}"

    [ -n "$pid" ] || return 0
    case "$pid" in
        ''|*[!0-9]*) return 0 ;;
    esac
    [ "$pid" -gt 1 ] 2>/dev/null || return 0

    local attempt
    for attempt in 1 2 3; do
        kill -TERM -"$pid" 2>/dev/null || true
        sleep 1
        kill -0 -"$pid" 2>/dev/null || return 0
    done
    kill -KILL -"$pid" 2>/dev/null || true
}

CLEANUP_RUNNING=0
cleanup() {
    # Prevent recursive cleanup (explicit call + trap).
    if [ "${CLEANUP_RUNNING:-0}" -eq 1 ]; then
        return 0
    fi
    CLEANUP_RUNNING=1

    local codex_pid=""
    local codex_pgid=""
    local main_pid=""

    if [ -f "$PROJECT_DIR/ralph_codex.pid" ]; then
        codex_pid=$(cat "$PROJECT_DIR/ralph_codex.pid" 2>/dev/null || echo "")
    fi
    if [ -f "$PROJECT_DIR/ralph_codex.pgid" ]; then
        codex_pgid=$(cat "$PROJECT_DIR/ralph_codex.pgid" 2>/dev/null || echo "")
    fi
    if [ -f "$PROJECT_DIR/ralph_main.pid" ]; then
        main_pid=$(cat "$PROJECT_DIR/ralph_main.pid" 2>/dev/null || echo "")
    fi

    # 1) Kill codex tree first.
    [ -n "$codex_pgid" ] && kill_process_group "$codex_pgid"
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
    rm -f "$PROJECT_DIR/ralph_codex.pgid"
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
RALPH_TIMEOUT_LEAD="${RALPH_TIMEOUT_LEAD:-300}"
CODEX_RETRY_DELAYS=(${RALPH_CODEX_RETRY_DELAYS:-60 120 300})
RATE_LIMIT_PAUSE="${RALPH_RATE_LIMIT_PAUSE:-1800}"
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
read_control_file() {
    if [ -f ralph_control.json ]; then
        python3 -c "
import json
try:
    d = json.load(open('ralph_control.json'))
    print(d.get('action', 'continue'))
    print(d.get('comment', ''))
except Exception:
    print('continue')
    print('')
" 2>/dev/null || printf "continue\n\n"
    else
        printf "continue\n\n"
    fi
}

apply_timeout_override() {
    local control_data action raw_value
    control_data=$(read_control_file)
    action=$(printf '%s\n' "$control_data" | sed -n '1p')
    raw_value=$(printf '%s\n' "$control_data" | sed -n '2p')

    case "$raw_value" in
        ''|*[!0-9]*) return 0 ;;
    esac

    if [ "$action" = "timeout" ] && [ -n "$raw_value" ]; then
        TASK_TIMEOUT="$raw_value"
        TASK_LEAD_TIMEOUT="$raw_value"
        log "⏱ Timeout override applied: coder=${TASK_TIMEOUT}s lead=${TASK_LEAD_TIMEOUT}s"
        clear_control_action
    fi
}

check_control() {
    while true; do
        if [ -f ralph_control.json ]; then
            local control_data
            control_data=$(read_control_file)
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
                    control_data=$(read_control_file)
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

wait_for_high_risk_approval() {
    local paused_once=0

    while true; do
        local control_data
        if [ ! -f ralph_control.json ]; then
            CONTROL_ACTION="pause"
            CONTROL_TARGET=""
        else
            control_data=$(read_control_file)
            CONTROL_ACTION=$(printf '%s\n' "$control_data" | sed -n '1p')
            CONTROL_TARGET=$(printf '%s\n' "$control_data" | sed -n '2p')
        fi

        if [ "$CONTROL_ACTION" = "continue" ]; then
            clear_control_action
            write_state "running" "$TASK_ID" "risk_gate_approved" "High-risk task approved by human"
            return 0
        fi

        if [ "$CONTROL_ACTION" = "stop" ] || [ "$CONTROL_ACTION" = "stop_now" ]; then
            return 1
        fi

        if [ "$CONTROL_ACTION" = "skip" ] && { [ -z "$CONTROL_TARGET" ] || [ "$CONTROL_TARGET" = "$TASK_ID" ]; }; then
            return 2
        fi

        if [ $paused_once -eq 0 ]; then
            log "⚠️ High-risk task $TASK_ID approved by Tech Lead. Paused for human review. Send /resume to commit."
            notify "⚠️ High-risk task $TASK_ID approved by Tech Lead. Paused for human review. Send /resume to commit."
            write_state "waiting_human" "$TASK_ID" "risk_gate" "Waiting for human to approve high-risk changes"
            paused_once=1
        fi

        sleep 5
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

set_control_action() {
    local action="$1"
    local comment="${2:-}"
    python3 -c "
import json
from pathlib import Path
p = Path('ralph_control.json')
payload = {'action': '$action', 'comment': '''$comment'''}
p.write_text(json.dumps(payload, indent=2), encoding='utf-8')
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

defer_blocked_task() {
    local reason="${1:-Blocked without reason}"
    log "⚠️ Task $TASK_ID blocked: $reason — skipping, continuing queue"
    notify "⚠️ $TASK_ID blocked (auto-skipped): $reason"
    python3 "$RALPH_DIR/scripts/update_task.py" "$TASK_ID" blocked "$reason" >/dev/null 2>&1 || true
    write_state "running" "$TASK_ID" "blocked" "$reason"
    TASK_BLOCKED=true
    TASK_DONE=true
}

resolve_agent_prompt_file() {
    local role="${1:-coder}"
    local fallback_file="$2"
    local role_upper
    role_upper=$(printf '%s' "$role" | tr '[:lower:]' '[:upper:]')
    local role_file="AGENTS_${role_upper}.md"

    if [ -f "$role_file" ]; then
        printf '%s\n' "$role_file"
    else
        printf '%s\n' "$fallback_file"
    fi
}

clip_chars() {
    local max_chars="$1"
    python3 -c "
import sys
limit = int(sys.argv[1])
data = sys.stdin.read()
if len(data) <= limit:
    sys.stdout.write(data)
else:
    sys.stdout.write(data[:limit].rstrip() + '\n... [truncated]')
" "$max_chars"
}

read_file_for_prompt() {
    local file_path="$1"
    local max_chars="$2"

    if [ ! -f "$file_path" ]; then
        return 0
    fi

    clip_chars "$max_chars" < "$file_path"
}

enforce_prompt_budget() {
    local max_chars="${1:-${RALPH_PROMPT_MAX_CHARS:-40000}}"
    clip_chars "$max_chars"
}

extract_task_keywords() {
    python3 -c "
import json
import re
import sys

task = json.load(sys.stdin)
parts = [
    task.get('id', ''),
    task.get('title', ''),
    task.get('description', ''),
    ' '.join(task.get('acceptance_criteria', []) or []),
]
text = ' '.join(parts).lower()
tokens = re.findall(r'[a-z0-9_./-]{4,}', text)
stopwords = {
    'task', 'tasks', 'phase', 'high', 'medium', 'low', 'done', 'pending',
    'with', 'from', 'that', 'this', 'into', 'only', 'must', 'then', 'than',
    'when', 'uses', 'use', 'read', 'file', 'files', 'coder', 'prompt',
    'before', 'after', 'based', 'large', 'overly', 'size', 'guard', 'includes',
    'include', 'inject', 'injection', 'context', 'relevant', 'source',
    'keyword', 'keywords', 'matching', 'project', 'agent', 'quality'
}
seen = []
for token in tokens:
    if token in stopwords:
        continue
    if token.startswith('r') and '-' in token:
        continue
    if token not in seen:
        seen.append(token)
for token in seen[:12]:
    print(token)
" 2>/dev/null || true
}

build_relevant_context() {
    local task_json="$1"
    local max_files="${RALPH_CONTEXT_MAX_FILES:-6}"
    local max_chars="${RALPH_CONTEXT_MAX_CHARS:-12000}"
    python3 - "$PROJECT_DIR" "$max_files" "$max_chars" "$task_json" <<'PY'
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

project_dir = pathlib.Path(sys.argv[1]).resolve()
max_files = int(sys.argv[2])
max_chars = int(sys.argv[3])
task_payload = sys.argv[4]
per_file_limit = max(800, max_chars // 2)

try:
    task = json.loads(task_payload)
except Exception:
    sys.exit(0)

parts = [
    task.get("id", ""),
    task.get("title", ""),
    task.get("description", ""),
    " ".join(task.get("acceptance_criteria", []) or []),
]
text = " ".join(parts).lower()
tokens = re.findall(r"[a-z0-9_./-]{4,}", text)
stopwords = {
    "task", "tasks", "phase", "high", "medium", "low", "done", "pending",
    "with", "from", "that", "this", "into", "only", "must", "then", "than",
    "when", "uses", "use", "read", "file", "files", "coder",
    "before", "after", "based", "large", "overly", "size", "guard", "includes",
    "include", "inject", "injection", "context", "relevant", "source",
    "project", "agent", "quality", "acceptance_criteria", "criteria",
}

keywords: list[str] = []
for token in tokens:
    if token in stopwords:
        continue
    if token.startswith("r") and "-" in token:
        continue
    if token not in keywords:
        keywords.append(token)

keywords = keywords[:16]
if not keywords:
    sys.exit(0)

keyword_regexes = [re.compile(re.escape(keyword), re.IGNORECASE) for keyword in keywords]
ignore_globs = [
    "!node_modules/**", "!.git/**", "!dist/**", "!build/**", "!.next/**",
    "!coverage/**", "!logs/**", "!*.lock", "!tasks.json", "!progress.md", "!AGENTS*.md",
]

candidate_paths: dict[pathlib.Path, dict[str, int]] = {}
rg_available = True
for keyword in keywords:
    if rg_available:
        try:
            result = subprocess.run(
                ["rg", "-l", "-i", "-m", "1", *sum([["--glob", g] for g in ignore_globs], []), "--", keyword, str(project_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            rg_available = False
            result = None
    else:
        result = None

    if result is None:
        continue

    for raw_path in result.stdout.splitlines():
        raw_path = raw_path.strip()
        if not raw_path:
            continue
        path = pathlib.Path(raw_path).resolve()
        if not path.is_file():
            continue
        entry = candidate_paths.setdefault(path, {"content_hits": 0, "path_hits": 0})
        entry["content_hits"] += 1

for path in project_dir.rglob("*"):
    if not path.is_file():
        continue
    rel = path.relative_to(project_dir)
    rel_text = str(rel).lower()
    if any(part in rel.parts for part in ("node_modules", ".git", "dist", "build", ".next", "coverage", "logs")):
        continue
    if rel.name.endswith(".lock") or rel.name in {"tasks.json", "progress.md"} or rel.name.startswith("AGENTS"):
        continue
    matched = sum(1 for regex in keyword_regexes if regex.search(rel_text))
    if matched:
        entry = candidate_paths.setdefault(path.resolve(), {"content_hits": 0, "path_hits": 0})
        entry["path_hits"] += matched

def path_priority(rel_path: pathlib.Path) -> int:
    rel_text = str(rel_path)
    score = 0
    if "/src/" in f"/{rel_text}/" or rel_text.startswith("src/"):
        score += 5
    if "/scripts/" in f"/{rel_text}/" or rel_text.startswith("scripts/"):
        score += 3
    if "/tests/" in f"/{rel_text}/" or rel_text.startswith("tests/"):
        score -= 2
    return score

ranked_paths = sorted(
    candidate_paths.items(),
    key=lambda item: (
        item[1]["content_hits"] * 10 + item[1]["path_hits"] * 4 + path_priority(item[0].relative_to(project_dir)),
        -len(str(item[0].relative_to(project_dir))),
    ),
    reverse=True,
)[:max_files]

if not ranked_paths:
    sys.exit(0)

output_parts: list[str] = ["Selected by keyword match:", ", ".join(keywords), ""]

for path, _score in ranked_paths:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    except Exception:
        continue

    lines = content.splitlines()
    hit_lines: list[int] = []
    for index, line in enumerate(lines, start=1):
        if any(regex.search(line) for regex in keyword_regexes):
            hit_lines.append(index)
        if len(hit_lines) >= 6:
            break

    ranges: list[tuple[int, int]] = []
    for hit_line in hit_lines[:3]:
        start = max(1, hit_line - 4)
        end = min(len(lines), hit_line + 4)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))

    if not ranges and lines:
        ranges.append((1, min(len(lines), 40)))

    snippet_lines: list[str] = []
    for start, end in ranges:
        for line_no in range(start, end + 1):
            snippet_lines.append(f"{line_no}: {lines[line_no - 1]}")
        snippet_lines.append("...")
    if snippet_lines and snippet_lines[-1] == "...":
        snippet_lines.pop()

    rel = path.relative_to(project_dir)
    file_section = f"## File: {rel}\n```text\n" + "\n".join(snippet_lines) + "\n```"
    if len(file_section) > per_file_limit:
        file_section = file_section[:per_file_limit].rstrip() + "\n... [truncated file snippet]"
    output_parts.append(file_section)
    output_parts.append("")

output = "\n".join(output_parts).rstrip()
if len(output) > max_chars:
    output = output[:max_chars].rstrip() + "\n... [truncated]"
sys.stdout.write(output)
PY
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
    local stale_codex_pgid=""

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
    if [ -f "$PROJECT_DIR/ralph_codex.pgid" ]; then
        stale_codex_pgid=$(cat "$PROJECT_DIR/ralph_codex.pgid" 2>/dev/null || echo "")
        case "$stale_codex_pgid" in
            ''|*[!0-9]*) stale_codex_pgid="" ;;
        esac
        if [ -n "$stale_codex_pgid" ] && [ "$RECOVERY_MODE" -eq 1 ]; then
            log "⚠️ Found stale ralph_codex.pgid=$stale_codex_pgid, killing process group"
            kill_process_group "$stale_codex_pgid"
        fi
    fi

    # Ensure stale pid files are removed after recovery check.
    rm -f "$PROJECT_DIR/ralph_codex.pid"
    rm -f "$PROJECT_DIR/ralph_codex.pgid"
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

terminate_codex_run() {
    local target_pid="${1:-}"
    local target_pgid="${2:-}"
    local stale_pid=""
    local stale_pgid=""

    if [ -f "$PROJECT_DIR/ralph_codex.pid" ]; then
        stale_pid=$(cat "$PROJECT_DIR/ralph_codex.pid" 2>/dev/null || echo "")
        case "$stale_pid" in
            ''|*[!0-9]*) stale_pid="" ;;
        esac
    fi
    if [ -f "$PROJECT_DIR/ralph_codex.pgid" ]; then
        stale_pgid=$(cat "$PROJECT_DIR/ralph_codex.pgid" 2>/dev/null || echo "")
        case "$stale_pgid" in
            ''|*[!0-9]*) stale_pgid="" ;;
        esac
    fi

    if [ -n "$stale_pgid" ]; then
        kill_process_group "$stale_pgid"
    fi
    if [ -n "$target_pgid" ] && [ "$target_pgid" != "$stale_pgid" ]; then
        kill_process_group "$target_pgid"
    fi

    if [ -n "$stale_pid" ]; then
        kill_tree "$stale_pid"
    fi

    if [ -n "$target_pid" ] && [ "$target_pid" != "$stale_pid" ]; then
        kill_tree "$target_pid"
    fi
}

run_codex_watchdog() {
    local output_file="$1"
    local target_pid="$2"
    local stale_timeout="${3:-300}"
    local fired_flag="$4"
    local poll_interval=5
    local last_activity
    local last_mtime
    local now

    if [ "$stale_timeout" -lt "$poll_interval" ] 2>/dev/null; then
        poll_interval="$stale_timeout"
    fi
    [ "$poll_interval" -lt 1 ] 2>/dev/null && poll_interval=1

    last_activity=$(date +%s)
    last_mtime=$(file_mtime "$output_file")

    while kill -0 "$target_pid" 2>/dev/null; do
        sleep "$poll_interval"
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

            terminate_codex_run "$target_pid"
            : > "$fired_flag"
            break
        fi
    done
}

run_codex() {
    local prompt="$1"
    local output_file="$2"
    local review_file="${3:-}"
    local timeout="$4"
    local model="${5:-}"
    local retry=0
    local exit_code=0
    local watchdog_timeout="${RALPH_WATCHDOG_TIMEOUT:-300}"

    while [ $retry -le $MAX_CODEX_RETRIES ]; do
        : > "$output_file"
        local watchdog_flag
        watchdog_flag="/tmp/ralph_watchdog_${$}_${retry}.flag"
        rm -f "$watchdog_flag"
        set +e
        local codex_cmd=(codex exec -s danger-full-access)
        if [ -n "$model" ]; then
            codex_cmd+=(-m "$model")
        fi
        if [ -n "$review_file" ]; then
            codex_cmd+=(-o "$review_file")
        fi
        codex_cmd+=("$prompt")

        local runner=(gtimeout --foreground --kill-after=10 "$timeout")
        runner+=("${codex_cmd[@]}")

        local launcher_meta="/tmp/ralph_codex_meta_${$}_${retry}.txt"
        rm -f "$launcher_meta"
        GIT_EDITOR=true \
        GIT_TERMINAL_PROMPT=0 \
        GIT_AUTHOR_NAME='Ralph Coder' \
        GIT_AUTHOR_EMAIL='ralph@dev' \
        python3 - "$output_file" "$launcher_meta" "${runner[@]}" <<'PY' &
import os
import subprocess
import sys

output_file = sys.argv[1]
meta_file = sys.argv[2]
cmd = sys.argv[3:]

with open(output_file, "wb") as out:
    proc = subprocess.Popen(
        cmd,
        stdout=out,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=os.environ.copy(),
    )
    with open(meta_file, "w", encoding="utf-8") as meta:
        meta.write(f"{proc.pid}\n")
        meta.write(f"{os.getpgid(proc.pid)}\n")
    sys.exit(proc.wait())
PY
        local launcher_pid=$!
        local codex_pid="$launcher_pid"
        local codex_pgid=""
        local meta_wait_loops=0
        while [ ! -s "$launcher_meta" ] && [ $meta_wait_loops -lt 50 ]; do
            sleep 0.1
            meta_wait_loops=$((meta_wait_loops + 1))
        done
        if [ -s "$launcher_meta" ]; then
            codex_pid=$(sed -n '1p' "$launcher_meta" 2>/dev/null || echo "$launcher_pid")
            codex_pgid=$(sed -n '2p' "$launcher_meta" 2>/dev/null || echo "")
        fi
        echo "$codex_pid" > "$PROJECT_DIR/ralph_codex.pid"
        [ -n "$codex_pgid" ] && echo "$codex_pgid" > "$PROJECT_DIR/ralph_codex.pgid" || rm -f "$PROJECT_DIR/ralph_codex.pgid"
        run_codex_watchdog "$output_file" "$codex_pid" "$watchdog_timeout" "$watchdog_flag" &
        local watchdog_pid=$!

        wait "$launcher_pid"
        exit_code=$?
        local watchdog_wait_loops=0
        while kill -0 "$watchdog_pid" 2>/dev/null; do
        if [ -f "$watchdog_flag" ] || [ $watchdog_wait_loops -ge 10 ]; then
                break
            fi
            sleep 0.1
            watchdog_wait_loops=$((watchdog_wait_loops + 1))
        done
        kill "$watchdog_pid" 2>/dev/null || true
        wait "$watchdog_pid" 2>/dev/null || true
        set -e

        local watchdog_fired=0
        if [ -f "$watchdog_flag" ]; then
            watchdog_fired=1
        fi
        rm -f "$watchdog_flag"

        rm -f "$PROJECT_DIR/ralph_codex.pid"
        rm -f "$PROJECT_DIR/ralph_codex.pgid"
        rm -f "$launcher_meta"
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
            log "❌ Codex failed after $MAX_CODEX_RETRIES retries"
            return 1
        fi

        # Success
        if [ $exit_code -eq 0 ]; then
            CONSECUTIVE_FAILURES=0
            return 0
        fi

        # Timeout (124) - clean up aggressively, then retry with backoff.
        if [ $exit_code -eq 124 ]; then
            log "⏰ TIMEOUT: codex exceeded ${timeout}s"
            notify "⏰ Codex timeout on ${TASK_ID:-unknown}. Cleaning up process tree."
            terminate_codex_run "$codex_pid" "$codex_pgid"
            if [ $retry -lt $MAX_CODEX_RETRIES ]; then
                local timeout_delay=${CODEX_RETRY_DELAYS[$retry]}
                log "⚠️ Timeout cleanup complete. Retry $((retry+1))/$MAX_CODEX_RETRIES in ${timeout_delay}s..."
                sleep "$timeout_delay"
                retry=$((retry + 1))
                continue
            fi
            log "❌ Codex timed out after $MAX_CODEX_RETRIES retries"
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            return 124
        fi

        # Check for rate limit in output
        if grep -qi 'rate.limit\|429\|throttl\|too many requests\|capacity' "$output_file" 2>/dev/null; then
            log "🚦 RATE LIMIT detected! Pausing ${RATE_LIMIT_PAUSE}s (30 min)..."
            notify "🚦 Rate limit hit. Pausing 30 min. Task: ${TASK_ID:-unknown}"
            write_state "paused" "${TASK_ID:-}" "rate_limit" "rate_limit"
            sleep "$RATE_LIMIT_PAUSE"
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

validate_lead_review_json() {
    REVIEW_JSON=$(echo "$REVIEW_JSON" | python3 -c "
import json, sys
text = sys.stdin.read().strip() or '{}'
try:
    d = json.loads(text)
except Exception:
    d = {}
decision = d.get('decision', '')
if decision not in ('approve', 'fix', 'alert'):
    d['decision'] = 'fix'
    d['fix_instructions'] = d.get('fix_instructions') or 'Tech Lead returned invalid JSON. Retry: implement the task correctly and ensure tests pass.'
    d.pop('alert_reason', None)
print(json.dumps(d, ensure_ascii=False))
")
}

run_coder_agent() {
    local project_agents=""
    local project_architecture=""
    local project_memory_system=""
    local memory_core=""
    local memory_recent=""
    local relevant_context=""
    local context_content=""
    local coder_prompt=""
    local human_comment=""
    local coder_output=""
    local pre_hash=""
    local codex_exit=0

    CODER_ROLE_FILE=$(resolve_agent_prompt_file "${TASK_ROLE:-coder}" "AGENTS_CODER.md")
    CODER_ROLE_CONTENT=$(read_file_for_prompt "$CODER_ROLE_FILE" "${RALPH_ROLE_MAX_CHARS:-8000}" || true)

    if [ -f "AGENTS.md" ]; then
        project_agents=$(read_file_for_prompt "AGENTS.md" "${RALPH_AGENTS_MAX_CHARS:-8000}" || true)
    fi
    if [ -f "ARCHITECTURE.md" ]; then
        project_architecture=$(read_file_for_prompt "ARCHITECTURE.md" "${RALPH_ARCHITECTURE_MAX_CHARS:-10000}" || true)
    fi
    if [ -f "MEMORY_SYSTEM.md" ]; then
        project_memory_system=$(read_file_for_prompt "MEMORY_SYSTEM.md" "${RALPH_MEMORY_SYSTEM_MAX_CHARS:-8000}" || true)
    fi
    if [ -f ".ralph/memory/core.md" ]; then
        memory_core=$(read_file_for_prompt ".ralph/memory/core.md" "${RALPH_MEMORY_CORE_MAX_CHARS:-8000}" || true)
    fi
    if [ -f ".ralph/memory/recent.md" ]; then
        memory_recent=$(read_file_for_prompt ".ralph/memory/recent.md" "${RALPH_MEMORY_RECENT_MAX_CHARS:-8000}" || true)
    fi

    relevant_context=$(build_relevant_context "$TASK_JSON" || true)

    if [ -n "${TASK_CONTEXT_FILES:-}" ]; then
        local ctx_file
        for ctx_file in $TASK_CONTEXT_FILES; do
            if [ -f "$ctx_file" ]; then
                context_content="${context_content}
## File: $ctx_file
$(read_file_for_prompt "$ctx_file" "${RALPH_REQUIRED_CONTEXT_MAX_CHARS:-6000}")
"
            fi
        done
    fi

    coder_prompt="Read AGENTS.md, ARCHITECTURE.md, MEMORY_SYSTEM.md, and ${CODER_ROLE_FILE} first. Then read progress.md.
Run make test to verify current state.

## Architecture Doc
${project_architecture:-No ARCHITECTURE.md provided. Use AGENTS.md and the repository structure.}

## AGENTS.md Context
${project_agents:-No AGENTS.md provided.}

## Memory System Doc
${project_memory_system:-No MEMORY_SYSTEM.md provided. Use AGENTS.md and .ralph/memory/.}

## Role Instructions (${CODER_ROLE_FILE})
${CODER_ROLE_CONTENT:-No role-specific instructions found. Fall back to AGENTS_CODER.md conventions.}

## Project Context (from memory)
${memory_core:-No core context yet. Read ARCHITECTURE.md and AGENTS.md for project info.}

## Recent Tasks (what was done before you)
${memory_recent:-No recent tasks yet. This may be the first task.}

## Required Context Files
${context_content:-No specific files required.}

## Relevant Source Snippets
${relevant_context:-No keyword-matched source snippets found.}

## Your Task
$TASK_JSON

## Rules
- **Think before coding**: You MUST wrap your plan inside <thinking> tags before writing any code blocks. Briefly analyze the requirements and file structure there.
- Implement ONLY this task
- make test must pass
- Do NOT modify tasks.json or progress.md"

    human_comment=$(get_human_comment)
    if [ -n "$human_comment" ]; then
        coder_prompt="$coder_prompt

## Human Comment (from project owner via Telegram)
$human_comment"
    fi

    coder_prompt=$(printf '%s' "$coder_prompt" | enforce_prompt_budget "${RALPH_CODER_PROMPT_MAX_CHARS:-40000}")
    coder_output="/tmp/ralph_coder_$$.txt"
    pre_hash=$(git rev-parse HEAD)

    set +e
    run_codex "$coder_prompt" "$coder_output" "" "${TASK_TIMEOUT:-180}" "$CODEX_MODEL"
    codex_exit=$?
    set -e

    CODER_TOKENS=$(extract_tokens "$coder_output")
    TASK_TOKENS=$(( ${TASK_TOKENS:-0} + ${CODER_TOKENS:-0} ))
    SESSION_TOKENS=$(( ${SESSION_TOKENS:-0} + ${CODER_TOKENS:-0} ))

    if [ -n "$(git diff --name-only 2>/dev/null)" ] || [ -n "$(git diff --cached --name-only 2>/dev/null)" ]; then
        git add -A
        git commit -m "wip(${TASK_ID}): coder changes" 2>/dev/null || true
    fi

    PRE_HASH="$pre_hash"
    return $codex_exit
}

self_heal_environment() {
    log '🩹 Tests broken before start. Attempting self-heal...'
    notify '🩹 Tests broken before start. Ralph will try to fix automatically.'

    local HEAL_TASK_JSON
    HEAL_TASK_JSON='{
      "id": "ENV-FIX",
      "phase": "R0",
      "title": "Fix broken tests",
      "description": "Before starting the task queue, make test is failing. Find the root cause and fix it so all tests pass. Do NOT change tasks.json or progress.md. Do NOT add new features.",
      "status": "pending",
      "priority": "critical",
      "complexity": "moderate",
      "timeout": 300,
      "required_context": []
    }'

    local OLD_TASK_JSON OLD_TASK_ID OLD_TASK_TITLE OLD_TASK_TIMEOUT OLD_TASK_LEAD_TIMEOUT
    local OLD_TASK_COMPLEXITY OLD_TASK_CONTEXT_FILES OLD_TASK_RISK OLD_TASK_ROLE
    OLD_TASK_JSON="${TASK_JSON:-}"
    OLD_TASK_ID="${TASK_ID:-}"
    OLD_TASK_TITLE="${TASK_TITLE:-}"
    OLD_TASK_TIMEOUT="${TASK_TIMEOUT:-}"
    OLD_TASK_LEAD_TIMEOUT="${TASK_LEAD_TIMEOUT:-}"
    OLD_TASK_COMPLEXITY="${TASK_COMPLEXITY:-}"
    OLD_TASK_CONTEXT_FILES="${TASK_CONTEXT_FILES:-}"
    OLD_TASK_RISK="${TASK_RISK:-}"
    OLD_TASK_ROLE="${TASK_ROLE:-}"

    TASK_JSON="$HEAL_TASK_JSON"
    TASK_ID="ENV-FIX"
    TASK_TITLE="Fix broken tests"
    TASK_TIMEOUT=300
    TASK_LEAD_TIMEOUT=120
    TASK_COMPLEXITY="moderate"
    TASK_CONTEXT_FILES=""
    TASK_RISK="medium"
    TASK_ROLE="coder"

    run_coder_agent
    local heal_exit=$?

    TASK_JSON="$OLD_TASK_JSON"
    TASK_ID="$OLD_TASK_ID"
    TASK_TITLE="$OLD_TASK_TITLE"
    TASK_TIMEOUT="$OLD_TASK_TIMEOUT"
    TASK_LEAD_TIMEOUT="$OLD_TASK_LEAD_TIMEOUT"
    TASK_COMPLEXITY="$OLD_TASK_COMPLEXITY"
    TASK_CONTEXT_FILES="$OLD_TASK_CONTEXT_FILES"
    TASK_RISK="$OLD_TASK_RISK"
    TASK_ROLE="$OLD_TASK_ROLE"

    if [ $heal_exit -ne 0 ]; then
        log '❌ Self-heal failed. Coder run did not complete cleanly.'
    fi

    if make test > /tmp/ralph_heal_verify.log 2>&1; then
        log '✅ Self-heal succeeded! Tests are green. Continuing queue.'
        notify '✅ Self-heal succeeded! Continuing task queue.'
        return 0
    else
        log '❌ Self-heal failed. Tests still broken.'
        notify '🚨 Self-heal failed. Tests still broken. Manual fix needed.'
        alert_human 'Self-heal failed: tests still broken after ENV-FIX attempt'
        return 1
    fi
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
    self_heal_environment || exit 1
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
    # Extract coder timeout from task (default 180s)
    TASK_TIMEOUT=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
print(task.get('timeout', 180))
" 2>/dev/null || echo "180")

    # Extract lead timeout with a higher default for heavier review tasks.
    TASK_LEAD_TIMEOUT=$(echo "$TASK_JSON" | python3 -c "
import os, sys, json
task = json.load(sys.stdin)
default_lead = int(os.environ.get('RALPH_TIMEOUT_LEAD', '300'))
print(task.get('lead_timeout', task.get('timeout', default_lead)))
" 2>/dev/null || echo "$RALPH_TIMEOUT_LEAD")

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

    TASK_RISK=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
print(task.get('risk', 'medium'))
" 2>/dev/null || echo "medium")

    TASK_ROLE=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
print(task.get('role', 'coder'))
" 2>/dev/null || echo "coder")

    CODER_ROLE_FILE=$(resolve_agent_prompt_file "$TASK_ROLE" "AGENTS_CODER.md")
    LEAD_ROLE_FILE=$(resolve_agent_prompt_file "$TASK_ROLE" "AGENTS_LEAD.md")
    CODER_ROLE_CONTENT=$(read_file_for_prompt "$CODER_ROLE_FILE" "${RALPH_ROLE_MAX_CHARS:-8000}" || true)
    LEAD_ROLE_CONTENT=$(read_file_for_prompt "$LEAD_ROLE_FILE" "${RALPH_ROLE_MAX_CHARS:-8000}" || true)

    # Select model based on complexity
    CODEX_MODEL=""
    if [ "$TASK_COMPLEXITY" = "simple" ]; then
        CODEX_MODEL="$MINI_MODEL"
        log "🧠 Model: codex-mini (simple task)"
    else
        log "🧠 Model: default (complexity: $TASK_COMPLEXITY)"
    fi

    log "📋 Complexity: $TASK_COMPLEXITY"
    log "⚠️ Risk: $TASK_RISK"
    log "🧩 Role: $TASK_ROLE (coder instructions: $CODER_ROLE_FILE, lead instructions: $LEAD_ROLE_FILE)"
    apply_timeout_override
    TASK_START=$(date +%s)

    log "📋 Task: $TASK_ID — $TASK_TITLE"
    log "📋 TASK_START task_id=$TASK_ID title=\"$TASK_TITLE\" timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "⏱  Timeout: coder=${TASK_TIMEOUT}s lead=${TASK_LEAD_TIMEOUT}s"

    FIX_RETRY=0
    TASK_DONE=false
    TASK_SKIPPED=false
    TASK_BLOCKED=false
    TASK_ALERTED=false
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
        apply_timeout_override

        # Inject memory context
        PROJECT_AGENTS=""
        PROJECT_ARCHITECTURE=""
        PROJECT_MEMORY_SYSTEM=""
        MEMORY_CORE=""
        MEMORY_RECENT=""
        RELEVANT_CONTEXT=""
        if [ -f "AGENTS.md" ]; then
            PROJECT_AGENTS=$(read_file_for_prompt "AGENTS.md" "${RALPH_AGENTS_MAX_CHARS:-8000}" || true)
        fi
        if [ -f "ARCHITECTURE.md" ]; then
            PROJECT_ARCHITECTURE=$(read_file_for_prompt "ARCHITECTURE.md" "${RALPH_ARCHITECTURE_MAX_CHARS:-10000}" || true)
        fi
        if [ -f "MEMORY_SYSTEM.md" ]; then
            PROJECT_MEMORY_SYSTEM=$(read_file_for_prompt "MEMORY_SYSTEM.md" "${RALPH_MEMORY_SYSTEM_MAX_CHARS:-8000}" || true)
        fi
        if [ -f ".ralph/memory/core.md" ]; then
            MEMORY_CORE=$(read_file_for_prompt ".ralph/memory/core.md" "${RALPH_MEMORY_CORE_MAX_CHARS:-8000}" || true)
        fi
        if [ -f ".ralph/memory/recent.md" ]; then
            MEMORY_RECENT=$(read_file_for_prompt ".ralph/memory/recent.md" "${RALPH_MEMORY_RECENT_MAX_CHARS:-8000}" || true)
        fi
        RELEVANT_CONTEXT=$(build_relevant_context "$TASK_JSON" || true)

        # Read required_context files
        CONTEXT_CONTENT=""
        if [ -n "$TASK_CONTEXT_FILES" ]; then
            for ctx_file in $TASK_CONTEXT_FILES; do
                if [ -f "$ctx_file" ]; then
                    CONTEXT_CONTENT="${CONTEXT_CONTENT}
## File: $ctx_file
$(read_file_for_prompt "$ctx_file" "${RALPH_REQUIRED_CONTEXT_MAX_CHARS:-6000}")
"
                fi
            done
        fi

        CODER_PROMPT="Read AGENTS.md, ARCHITECTURE.md, MEMORY_SYSTEM.md, and ${CODER_ROLE_FILE} first. Then read progress.md.
Run make test to verify current state.

## Architecture Doc
${PROJECT_ARCHITECTURE:-No ARCHITECTURE.md provided. Use AGENTS.md and the repository structure.}

## AGENTS.md Context
${PROJECT_AGENTS:-No AGENTS.md provided.}

## Memory System Doc
${PROJECT_MEMORY_SYSTEM:-No MEMORY_SYSTEM.md provided. Use AGENTS.md and .ralph/memory/.}

## Role Instructions (${CODER_ROLE_FILE})
${CODER_ROLE_CONTENT:-No role-specific instructions found. Fall back to AGENTS_CODER.md conventions.}

## Project Context (from memory)
${MEMORY_CORE:-No core context yet. Read ARCHITECTURE.md and AGENTS.md for project info.}

## Recent Tasks (what was done before you)
${MEMORY_RECENT:-No recent tasks yet. This may be the first task.}

## Required Context Files
${CONTEXT_CONTENT:-No specific files required.}

## Relevant Source Snippets
${RELEVANT_CONTEXT:-No keyword-matched source snippets found.}

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
        CODER_PROMPT=$(printf '%s' "$CODER_PROMPT" | enforce_prompt_budget "${RALPH_CODER_PROMPT_MAX_CHARS:-40000}")

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
        REVIEW_JSON='{}'

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
            REVIEW_JSON="$REVIEW"
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
            apply_timeout_override

            LEAD_PROMPT="Read AGENTS.md, ARCHITECTURE.md, MEMORY_SYSTEM.md, and ${LEAD_ROLE_FILE} first.

## Task
$TASK_JSON

## Role Instructions (${LEAD_ROLE_FILE})
${LEAD_ROLE_CONTENT:-No role-specific instructions found. Fall back to AGENTS_LEAD.md conventions.}

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
            run_codex "$LEAD_PROMPT" "$LEAD_OUTPUT" "$REVIEW_FILE" "$TASK_LEAD_TIMEOUT" "$CODEX_MODEL"
            CODEX_EXIT=$?
            set -e
            LEAD_TOKENS=$(extract_tokens "$LEAD_OUTPUT")
            TASK_TOKENS=$((TASK_TOKENS + ${LEAD_TOKENS:-0}))
            SESSION_TOKENS=$((SESSION_TOKENS + ${LEAD_TOKENS:-0}))
            log "💰 [LEAD]  Tokens: $(format_tokens "$LEAD_TOKENS") | Task total: $(format_tokens "$TASK_TOKENS") | Session total: $(format_tokens "$SESSION_TOKENS")"
            LEAD_DURATION=$(( $(date +%s) - LEAD_START ))
            log "⏱️ Tech Lead took ${LEAD_DURATION}s"
            REVIEW=$(cat "$REVIEW_FILE" 2>/dev/null || echo '{"decision":"alert","alert_reason":"No output"}')
            REVIEW_JSON=$(python3 "$RALPH_DIR/scripts/extract_json.py" < "$LEAD_OUTPUT" 2>/dev/null || true)
            if [ -z "$REVIEW_JSON" ] || [ "$REVIEW_JSON" = "{}" ]; then
                REVIEW_JSON=$(python3 "$RALPH_DIR/scripts/extract_json.py" < "$REVIEW_FILE" 2>/dev/null || echo '{}')
            fi
            validate_lead_review_json
            log "🔍 DEBUG: Review first 200 chars: $(echo "$REVIEW" | head -c 200)"
            log "🔍 DEBUG: Parsed review JSON: $(echo "$REVIEW_JSON" | head -c 200)"
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

        DECISION=$(echo "$REVIEW_JSON" | python3 -c "
import sys, json
text = sys.stdin.read().strip() or '{}'
try:
    d = json.loads(text)
    print(d.get('decision', 'alert'))
except Exception:
    print('alert')
" 2>/dev/null)
        DECISION="${DECISION:-alert}"
        DECISION=$(echo "$DECISION" | head -1)
        DECISION=$(echo "$DECISION" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        QUALITY=$(echo "$REVIEW_JSON" | python3 -c "
import sys, json
text = sys.stdin.read().strip() or '{}'
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
                PROGRESS_NOTE=$(echo "$REVIEW_JSON" | python3 -c "
import sys, json
text = sys.stdin.read().strip() or '{}'
try:
    d = json.loads(text)
    print(d.get('progress_note', 'Task completed'))
except Exception:
    print('Task completed')
" 2>/dev/null || echo "done")

                python3 "$RALPH_DIR/scripts/update_task.py" "$TASK_ID" done
                python3 "$RALPH_DIR/scripts/update_progress.py" "$TASK_ID" "$PROGRESS_NOTE"
                # Update memory with task summary
                CHANGED_FILES=$(git diff --name-only "$PRE_HASH" HEAD 2>/dev/null | tr '\n' ', ' | sed 's/,$//')
                python3 "$RALPH_DIR/scripts/update_memory.py" "$TASK_ID" "$TASK_TITLE" "${CHANGED_FILES:-none}" "approved" "${FIX_INSTRUCTIONS:-}" 2>/dev/null || true

                if [ "$TASK_RISK" = "high" ]; then
                    set_control_action "pause" ""
                    CONTROL_STATUS=0
                    wait_for_high_risk_approval || CONTROL_STATUS=$?
                    if [ $CONTROL_STATUS -eq 1 ]; then
                        log "⏹ Stop signal received during high-risk review gate"
                        write_state "stopped" "$TASK_ID" "risk_gate" "Stopped by user during high-risk review"
                        notify "⏹ Ralph stopped by user during high-risk review for $TASK_ID"
                        cleanup
                        exit 0
                    elif [ $CONTROL_STATUS -eq 2 ]; then
                        skip_current_task
                        TASK_SKIPPED=true
                        break
                    fi
                fi

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
                FIX_INSTRUCTIONS=$(echo "$REVIEW_JSON" | python3 -c "
import sys, json
text = sys.stdin.read().strip() or '{}'
try:
    d = json.loads(text)
    print(d.get('fix_instructions', 'Fix failing tests and unmet criteria'))
except Exception:
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
                REASON=$(echo "$REVIEW_JSON" | python3 -c "
import sys, json
text = sys.stdin.read().strip() or '{}'
try:
    d = json.loads(text)
    print(d.get('alert_reason', 'Unknown issue'))
except Exception:
    print('Unknown issue')
" 2>/dev/null || echo "Unknown")

                log_metrics "failed"
                log "📋 TASK_FAIL task_id=$TASK_ID status=alert reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                if [ "${TASK_RISK:-medium}" = "high" ]; then
                    alert_human "$REASON"
                    TASK_ALERTED=true
                    TASK_DONE=true
                else
                    defer_blocked_task "$REASON"
                fi
                rm -f "$REVIEW_FILE" "$CODER_OUTPUT" "$LEAD_OUTPUT"
                continue
                ;;

            *)
                log "⚠️ Unknown decision: '$DECISION' (length: ${#DECISION})"
                log "⚠️ Raw review output: $(head -5 /tmp/ralph_review_$$.txt 2>/dev/null)"
                FIX_INSTRUCTIONS="Tech Lead returned unknown decision '$DECISION'. Retry: implement the task correctly and ensure tests pass."
                FIX_RETRY=$((FIX_RETRY+1))
                notify "🔧 $TASK_ID invalid lead decision, retrying fix ($FIX_RETRY/$MAX_FIX_RETRIES)"
                log "🔧 Fix $FIX_RETRY/$MAX_FIX_RETRIES: $FIX_INSTRUCTIONS"
                rm -f "$REVIEW_FILE" "$CODER_OUTPUT" "$LEAD_OUTPUT"
                continue
                ;;
        esac
        rm -f "$REVIEW_FILE" "$CODER_OUTPUT" "$LEAD_OUTPUT"
    done

    if [ "$TASK_SKIPPED" = true ]; then
        [ "$MODE" = "task" ] && break
        continue
    fi

    if [ "$TASK_BLOCKED" = true ]; then
        [ "$MODE" = "task" ] && break
        continue
    fi

    if [ "$TASK_ALERTED" = true ]; then
        break
    fi

    if [ "$TASK_DONE" = false ]; then
        REASON="$TASK_ID failed after $MAX_FIX_RETRIES retries"
        log_metrics "failed"
        log "📋 TASK_FAIL task_id=$TASK_ID status=alert reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        if [ "${TASK_RISK:-medium}" = "high" ]; then
            alert_human "$REASON"
            break
        else
            defer_blocked_task "$REASON"
            [ "$MODE" = "task" ] && break
            continue
        fi
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
