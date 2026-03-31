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
OWNS_MAIN_PID=0
cleanup_orphan_coder_outputs() {
    python3 - <<'PY' 2>/dev/null || true
from __future__ import annotations

import time
from pathlib import Path

deadline = time.time() - 3600
for path in Path("/tmp").glob("ralph_coder_*.txt"):
    try:
        if path.is_file() and path.stat().st_mtime < deadline:
            path.unlink()
    except OSError:
        pass
PY
}

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
    if [ "$OWNS_MAIN_PID" -eq 1 ] && [ -f "$PROJECT_DIR/ralph_main.pid" ]; then
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
    if [ "$OWNS_MAIN_PID" -eq 1 ] && [ -n "$main_pid" ] && [ "$main_pid" != "$$" ]; then
        kill_tree "$main_pid"
    fi

    rm -f "$PROJECT_DIR/ralph_codex.pid"
    rm -f "$PROJECT_DIR/ralph_codex.pgid"
    if [ "$OWNS_MAIN_PID" -eq 1 ]; then
        rm -f "$PROJECT_DIR/ralph_main.pid"
    fi
    rm -f "/tmp/ralph_coder_$$.txt"
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
MINI_MODEL=""
SESSION_TOKENS=0
SESSION_TASKS=0
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
RALPH_LOG="$LOG_DIR/ralph_$(date +%Y-%m-%d).log"
METRICS_FILE="$LOG_DIR/metrics.csv"
[ ! -f "$METRICS_FILE" ] && echo "timestamp,task_id,status,duration_s,attempts,files_changed,quality,cost_est,runtime_success,verified_success" > "$METRICS_FILE"
PHASE_TIMINGS_FILE="$LOG_DIR/task_phase_timings.csv"
[ ! -f "$PHASE_TIMINGS_FILE" ] && echo "timestamp,task_id,attempt,mode,phase,duration_s" > "$PHASE_TIMINGS_FILE"
FINAL_STATE_STATUS="idle"
FINAL_STATE_STEP="idle"
FINAL_STATE_MESSAGE="All tasks complete"
FINAL_NOTIFY_MESSAGE="🎉 Ralph finished! Run /status for details."
QUEUE_EXIT_LOG="🎉 All tasks complete!"
FINAL_EXIT_CODE=0
REASON=""
find "$LOG_DIR" -name "ralph_*.log" -mtime +2 -delete 2>/dev/null || true
cleanup_orphan_coder_outputs

is_single_task_mode() {
    [ "$MODE" = "task" ] || [ "$MODE" = "handoff" ]
}

detect_runtime_task_class() {
    python3 - "$RALPH_DIR" "${TASK_JSON:-null}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

ralph_dir = Path(sys.argv[1])
task = json.loads(sys.argv[2])
sys.path.insert(0, str(ralph_dir / "scripts"))

from verify_task_closure import detect_task_class, extract_command_tokens, extract_expected_test_names, extract_path_candidates  # type: ignore

expected_paths = extract_path_candidates(task)
command_tokens = extract_command_tokens(task)
expected_tests = extract_expected_test_names(task)
print(detect_task_class(task, expected_paths, command_tokens, expected_tests))
PY
}

coder_prompt_profile() {
    python3 - "$RALPH_DIR" "$1" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

ralph_dir = Path(sys.argv[1])
task = json.loads(sys.argv[2])
sys.path.insert(0, str(ralph_dir / "scripts"))

import verify_task_closure as task_closure  # type: ignore

extract_path_candidates = task_closure.extract_path_candidates
normalize_path = task_closure.normalize_path
is_bookkeeping = getattr(task_closure, "is_bookkeeping", task_closure.is_bookkeeping_file)

texts: list[str] = [task.get("title", ""), task.get("description", "")]
texts.extend(task.get("acceptance_criteria", []) or [])
texts.extend(task.get("test_steps", []) or [])
combined = "\n".join(texts).lower()

required_context = [
    normalize_path(path)
    for path in (task.get("required_context") or [])
    if isinstance(path, str) and normalize_path(path)
]
explicit_project_docs = {
    "agents.md",
    "architecture.md",
    "memory_system.md",
    "progress.md",
    ".ralph/memory/core.md",
    ".ralph/memory/recent.md",
    ".ralph/memory/patterns.md",
    ".ralph/memory/decisions.md",
}

def mentions_project_docs(marker: str, *negative_markers: str) -> bool:
    if marker not in combined:
        return False
    return not any(negative in combined for negative in negative_markers)


requires_project_docs = any(path.lower() in explicit_project_docs for path in required_context) or any(
    (
        mentions_project_docs("agents.md", "do not read agents.md", "don't read agents.md", "without agents.md")
        or mentions_project_docs(
            "architecture.md",
            "do not read architecture.md",
            "don't read architecture.md",
            "without architecture.md",
            "no architecture.md",
        )
        or mentions_project_docs(
            "memory_system.md",
            "do not read memory_system.md",
            "don't read memory_system.md",
            "without memory_system.md",
            "no memory_system.md",
        )
        or mentions_project_docs(".ralph/memory/")
        or mentions_project_docs(
            "project-wide docs",
            "no project-wide docs",
            "without project-wide docs",
            "avoid project-wide docs",
        )
        or mentions_project_docs(
            "project wide docs",
            "no project wide docs",
            "without project wide docs",
            "avoid project wide docs",
        )
        or mentions_project_docs(
            "project-wide doc",
            "no project-wide doc",
            "without project-wide doc",
            "avoid project-wide doc",
        )
        or mentions_project_docs(
            "project wide doc",
            "no project wide doc",
            "without project wide doc",
            "avoid project wide doc",
        )
    )
    for _ in [0]
)

def is_broad_required_context(path: str) -> bool:
    lowered = path.lower()
    if lowered in explicit_project_docs or lowered.endswith(".md"):
        return True
    if any(token in path for token in ("*", "?", "[")):
        return True
    return path in {".", "./"} or path.endswith("/")

broad_required_context = any(is_broad_required_context(path) for path in required_context)

candidate_paths = [
    path for path in extract_path_candidates(task) if not is_bookkeeping(path)
]
concrete_targets = [
    path for path in candidate_paths if not path.startswith("docs/") and not path.endswith(".md")
]

profile = "broad"
if (
    not broad_required_context
    and concrete_targets
    and not requires_project_docs
):
    profile = "narrow"

print(json.dumps({"profile": profile, "targets": concrete_targets}, ensure_ascii=False))
PY
}

extract_task_field() {
    local task_json="$1"
    local expression="$2"
    printf '%s' "$task_json" | python3 -c "import json,sys; task=json.load(sys.stdin); ${expression}" 2>/dev/null
}

prepare_coder_prompt_for_task_json() {
    local task_json="$1"
    local task_context_files="$2"
    local prompt_profile_json=""
    local context_content=""
    local prompt_payload=""
    local previous_landed_commit=""
    local previous_diff_bytes="0"
    local previous_diff_summary=""
    local previous_attempt_context=""
    local previous_feedback=""
    local previous_feedback_source=""
    local previous_test_output=""
    local task_complexity=""
    local web_search_policy="default"

    PROJECT_AGENTS=""
    PROJECT_ARCHITECTURE=""
    PROJECT_MEMORY_SYSTEM=""
    MEMORY_CORE=""
    MEMORY_RECENT=""
    RELEVANT_CONTEXT=""
    CODER_PROMPT_PROFILE_NAME="broad"
    CODER_PROMPT_TARGETS=""
    CODER_PROMPT_TOKENS=0
    CODER_PROMPT_BUDGET=0
    task_complexity=$(extract_task_field "$task_json" "print(task.get('complexity', 'moderate'))" || echo "moderate")

    # Web search policy: simple tasks use local-first (no web search)
    if [ "$task_complexity" = "simple" ]; then
        web_search_policy="disabled"
        log "🔍 Web search disabled for simple task (local-first policy)"
    fi
    export RALPH_WEB_SEARCH_POLICY="$web_search_policy"

    prompt_profile_json=$(coder_prompt_profile "$task_json" || echo '{"profile":"broad","targets":[]}')
    CODER_PROMPT_PROFILE_NAME=$(printf '%s' "$prompt_profile_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('profile', 'broad'))" 2>/dev/null || echo "broad")
    CODER_PROMPT_TARGETS=$(printf '%s' "$prompt_profile_json" | python3 -c "import json,sys; print('\n'.join(json.load(sys.stdin).get('targets', [])))" 2>/dev/null || echo "")
    load_coder_prompt_project_context "$CODER_PROMPT_PROFILE_NAME"
    PROJECT_AGENTS="$CODER_PROMPT_PROJECT_AGENTS"
    PROJECT_ARCHITECTURE="$CODER_PROMPT_PROJECT_ARCHITECTURE"
    PROJECT_MEMORY_SYSTEM="$CODER_PROMPT_PROJECT_MEMORY_SYSTEM"
    MEMORY_CORE="$CODER_PROMPT_MEMORY_CORE"
    MEMORY_RECENT="$CODER_PROMPT_MEMORY_RECENT"
    RELEVANT_CONTEXT=$(build_relevant_context "$task_json" "$CODER_PROMPT_PROFILE_NAME" || true)

    if [ "${FIX_RETRY:-0}" -gt 0 ] && [ -f "${DIFF_SNAPSHOT_FILE:-}" ]; then
        if [ -f "${REVIEW_TARGET_FILE:-}" ]; then
            previous_landed_commit=$(cat "$REVIEW_TARGET_FILE" 2>/dev/null || true)
        fi
        previous_diff_bytes=$(wc -c < "$DIFF_SNAPSHOT_FILE" 2>/dev/null | tr -d ' ' || echo "0")
        previous_diff_bytes="${previous_diff_bytes:-0}"
        if [ -f "${DIFF_SUMMARY_FILE:-}" ]; then
            previous_diff_summary=$(cat "$DIFF_SUMMARY_FILE" 2>/dev/null || true)
        fi
        if [ -f "${RETRY_FEEDBACK_FILE:-}" ]; then
            previous_feedback=$(cat "$RETRY_FEEDBACK_FILE" 2>/dev/null || true)
        fi
        if [ -f "${RETRY_FEEDBACK_SOURCE_FILE:-}" ]; then
            previous_feedback_source=$(cat "$RETRY_FEEDBACK_SOURCE_FILE" 2>/dev/null || true)
        fi
        if [ -f "${RETRY_TEST_OUTPUT_FILE:-}" ]; then
            previous_test_output=$(cat "$RETRY_TEST_OUTPUT_FILE" 2>/dev/null || true)
        fi
        previous_attempt_context=$(build_retry_attempt_context \
            "$FIX_RETRY" \
            "$previous_landed_commit" \
            "$previous_diff_bytes" \
            "$previous_diff_summary" \
            "$previous_feedback_source" \
            "$previous_feedback" \
            "$previous_test_output")
    fi

    context_content=$(build_required_context_content "$task_context_files" "$CODER_PROMPT_PROFILE_NAME")
    HUMAN_COMMENT=$(get_human_comment)
    prompt_payload=$(build_coder_prompt_with_budget \
        "$task_json" \
        "$CODER_ROLE_FILE" \
        "$CODER_ROLE_CONTENT" \
        "$CODER_PROMPT_PROFILE_NAME" \
        "$CODER_PROMPT_TARGETS" \
        "$context_content" \
        "$RELEVANT_CONTEXT" \
        "$PROJECT_AGENTS" \
        "$PROJECT_ARCHITECTURE" \
        "$PROJECT_MEMORY_SYSTEM" \
        "$MEMORY_CORE" \
        "$MEMORY_RECENT" \
        "${FIX_INSTRUCTIONS:-}" \
        "$HUMAN_COMMENT" \
        "$previous_attempt_context" \
        "$(get_coder_prompt_token_budget "$CODER_PROMPT_PROFILE_NAME")" \
        "${RALPH_CODER_PROMPT_MAX_CHARS:-40000}")
    CODER_PROMPT_TOKENS=$(printf '%s\n' "$prompt_payload" | sed -n '1s/^__TOKENS__://p')
    CODER_PROMPT=$(printf '%s\n' "$prompt_payload" | sed '1d')
    CODER_PROMPT_BUDGET=$(get_coder_prompt_token_budget "$CODER_PROMPT_PROFILE_NAME")
    if [ "${RALPH_WEB_SEARCH_POLICY:-default}" = "disabled" ]; then
        CODER_PROMPT="${CODER_PROMPT}
IMPORTANT: This is a simple local task. Do NOT use web search. Search locally first with rg. If a matching pattern exists in the repo, implement from local evidence only."
        log "📋 Injected local-first prompt constraint"
    fi
}

handoff_candidate_paths() {
    python3 - "$RALPH_DIR" "$1" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

ralph_dir = Path(sys.argv[1])
task = json.loads(sys.argv[2])
project_dir = Path.cwd()
sys.path.insert(0, str(ralph_dir / "scripts"))

from verify_task_closure import (  # type: ignore
    command_candidate_handlers,
    command_routed_handlers,
    extract_command_tokens,
    extract_path_candidates,
    read_text,
)
paths: set[str] = set(extract_path_candidates(task))
command_tokens = extract_command_tokens(task)

for path in list(paths):
    if path.startswith("scripts/"):
        packaged_path = f"src/ralph/resources/{path}"
        if (project_dir / packaged_path).exists():
            paths.add(packaged_path)

if command_tokens:
    bot_path = project_dir / "scripts" / "ralph_bot.py"
    bot_text = read_text(bot_path)
    paths.add("scripts/ralph_bot.py")
    packaged_bot = project_dir / "src" / "ralph" / "resources" / "scripts" / "ralph_bot.py"
    if packaged_bot.exists():
        paths.add("src/ralph/resources/scripts/ralph_bot.py")
    for token in command_tokens:
        handlers = command_candidate_handlers(token) | command_routed_handlers(bot_text, token)
        for test_file in (project_dir / "tests").glob("test_*.py"):
            test_text = read_text(test_file)
            if f"/{token}" in test_text or any(handler in test_text for handler in handlers):
                paths.add(test_file.relative_to(project_dir).as_posix())

for path in sorted(paths):
    print(path)
PY
}

handoff_worktree_evidence_paths() {
    local task_json="$1"
    local candidate_paths=""
    local path=""

    candidate_paths=$(handoff_candidate_paths "$task_json")
    [ -n "$candidate_paths" ] || return 0

    while IFS= read -r path; do
        [ -n "$path" ] || continue
        if [ -n "$(git status --porcelain --untracked-files=all -- "$path" 2>/dev/null)" ]; then
            printf '%s\n' "$path"
        fi
    done <<< "$candidate_paths"
}

handoff_empty_tree_hash() {
    printf '%s\n' "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
}

handoff_commit_parent_hash() {
    local commit_hash="$1"
    git rev-parse "${commit_hash}^" 2>/dev/null || handoff_empty_tree_hash
}

handoff_latest_repo_candidate_commit() {
    local task_json="$1"
    local candidate_paths=""
    local commit_hash=""
    local changed_paths=""
    local filtered_paths=""
    local path=""

    candidate_paths=$(handoff_candidate_paths "$task_json")
    [ -n "$candidate_paths" ] || return 0

    set --
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        set -- "$@" "$path"
    done <<< "$candidate_paths"
    [ "$#" -gt 0 ] || return 0

    while IFS= read -r commit_hash; do
        [ -n "$commit_hash" ] || continue
        changed_paths=$(git diff-tree --root --no-commit-id --name-only -r "$commit_hash" 2>/dev/null || true)
        [ -n "$changed_paths" ] || continue
        filtered_paths=""
        while IFS= read -r path; do
            [ -n "$path" ] || continue
            handoff_is_runtime_owned_path "$path" && continue
            filtered_paths="${filtered_paths}${path}"$'\n'
        done <<< "$changed_paths"
        [ -n "$filtered_paths" ] || continue

        while IFS= read -r path; do
            [ -n "$path" ] || continue
            if ! printf '%s\n' "$candidate_paths" | grep -Fxq "$path"; then
                filtered_paths=""
                break
            fi
        done <<< "$filtered_paths"

        if [ -n "$filtered_paths" ]; then
            printf '%s\n' "$commit_hash"
            return 0
        fi
    done < <(git log --format=%H -- "$@" 2>/dev/null || true)
}

handoff_stage_paths() {
    local paths="$1"
    local path=""

    while IFS= read -r path; do
        [ -n "$path" ] || continue
        git add -A -- "$path"
    done <<< "$paths"
}

handoff_is_runtime_owned_path() {
    case "${1:-}" in
        tasks.json|progress.md|audit_report.md|ralph_state.json|ralph_control.json|ralph_alerts.log|ralph_main.pid|ralph_codex.pid|ralph_codex.pgid|.ralph/memory/recent.md|.ralph/memory/decisions.md|.ralph/memory/patterns.md) return 0 ;;
        logs/*|.pytest_cache/*|__pycache__/*|.ralph/audit/*|ralph/audit/*) return 0 ;;
    esac
    return 1
}

handoff_unrelated_worktree_tracked_changes() {
    local task_json="$1"
    local candidate_paths=""
    local tracked_paths=""
    local path=""

    candidate_paths=$(handoff_candidate_paths "$task_json")
    tracked_paths=$(
        {
            git diff --name-only 2>/dev/null
            git diff --cached --name-only 2>/dev/null
        } | awk 'NF' | sort -u
    )
    [ -n "$tracked_paths" ] || return 0

    while IFS= read -r path; do
        [ -n "$path" ] || continue
        handoff_is_runtime_owned_path "$path" && continue
        if ! printf '%s\n' "$candidate_paths" | grep -Fxq "$path"; then
            printf '%s\n' "$path"
        fi
    done <<< "$tracked_paths"
}

# Prevent duplicate ralph instances
if { is_single_task_mode || [ "$MODE" = "phase" ] || [ "$MODE" = "auto" ]; } && [ -f "$PROJECT_DIR/ralph_main.pid" ]; then
    _existing_pid=$(cat "$PROJECT_DIR/ralph_main.pid" 2>/dev/null || echo "")
    if [ -n "$_existing_pid" ] && kill -0 "$_existing_pid" 2>/dev/null; then
        echo "⚠️  Ralph already running (PID $_existing_pid). Aborting duplicate launch."
        exit 1
    fi
fi
if is_single_task_mode || [ "$MODE" = "phase" ] || [ "$MODE" = "auto" ]; then
    OWNS_MAIN_PID=1
    echo "$$" > "$PROJECT_DIR/ralph_main.pid"
fi

log() {
    local msg="[ralph] $(date +%H:%M:%S) $*"
    echo "$msg"
    echo "$msg" >> "$RALPH_LOG"
}

archive_codex_output() {
    local output_file="$1"
    local attempt_index="$2"
    local task_id="${TASK_ID:-unknown}"
    local archive_file="$LOG_DIR/codex_${task_id}_${attempt_index}.txt"

    [ -f "$output_file" ] || return 0
    cp "$output_file" "$archive_file" 2>/dev/null || cat "$output_file" > "$archive_file" 2>/dev/null || true
    echo "$archive_file"
}

finalize_codex_stream_logger() {
    local stream_logger_pid="${1:-}"
    local stream_fifo="${2:-}"

    [ -n "$stream_logger_pid" ] || return 0

    if kill -0 "$stream_logger_pid" 2>/dev/null && [ -p "$stream_fifo" ]; then
        python3 - "$stream_fifo" <<'PY' 2>/dev/null || true
from __future__ import annotations

import sys

try:
    with open(sys.argv[1], "w", encoding="utf-8", errors="replace"):
        pass
except OSError:
    pass
PY
    fi

    wait "$stream_logger_pid" 2>/dev/null || true
}

extract_tokens() {
    local output_file="$1"
    local tokens
    tokens=$(grep -A1 "tokens used" "$output_file" 2>/dev/null | tail -1 | tr -cd '0-9')
    echo "${tokens:-0}"
}

format_tokens() {
    local tokens="${1:-0}"
    local formatted=""
    local status=0

    set +e
    formatted=$(python3 -c "print(f'{int(${tokens}):,}')" 2>/dev/null)
    status=$?
    set -e

    if [ "$status" -eq 0 ] && [ -n "$formatted" ]; then
        printf '%s' "$formatted"
    else
        printf '%s' "$tokens"
    fi
}

estimate_cost() {
    local tokens="${1:-0}"
    local cost=""
    local status=0

    set +e
    cost=$(python3 -c "print(f'{(int(${tokens}) * 3 / 1000000):.2f}')" 2>/dev/null)
    status=$?
    set -e

    if [ "$status" -eq 0 ] && [ -n "$cost" ]; then
        printf '%s' "$cost"
    else
        printf '0.00'
    fi
}

ensure_metrics_schema() {
    python3 - "$METRICS_FILE" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)
lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
if not lines:
    raise SystemExit(0)
old_header = "timestamp,task_id,status,duration_s,attempts,files_changed,quality,cost_est"
new_header = "timestamp,task_id,status,duration_s,attempts,files_changed,quality,cost_est,runtime_success,verified_success,web_search_policy"
if lines[0].strip() != old_header:
    raise SystemExit(0)
rewritten = [new_header]
for line in lines[1:]:
    if not line.strip():
        continue
    rewritten.append(f"{line},,")
path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
PY
}

log_metrics() {
    local status="$1"
    local runtime_success="${2:-false}"
    local verified_success="${3:-false}"
    local quality="${QUALITY:-0}"
    local end_time=$(date +%s)
    local duration=$((end_time - TASK_START))
    local files=$(git diff --name-only "$PRE_HASH" HEAD 2>/dev/null | wc -l | tr -d ' ')
    local cost=$(estimate_cost "$TASK_TOKENS")
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),$TASK_ID,$status,$duration,$FIX_RETRY,$files,$quality,$cost,$runtime_success,$verified_success,${RALPH_WEB_SEARCH_POLICY:-default}" >> "$METRICS_FILE"
}

log_phase_timing() {
    local task_id="$1"
    local attempt="$2"
    local mode_name="$3"
    local phase="$4"
    local duration="$5"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),$task_id,$attempt,$mode_name,$phase,$duration" >> "$PHASE_TIMINGS_FILE"
}

write_task_audit_artifact() {
    local audit_status="${1:-failed}"
    local runtime_success="${2:-false}"
    local verified_success="${3:-false}"
    local audit_duration="${4:-0}"
    local changed_files_json="${PRE_CLOSURE_CHANGED_FILES_JSON:-[]}"
    local verification_json_payload="${VERIFICATION_JSON:-}"

    if [ -z "$verification_json_payload" ]; then
        verification_json_payload=$(python3 - <<'PY'
import json
import os

reason = os.environ.get("RALPH_AUDIT_REASON", "").strip()
print(json.dumps({
    "result": "needs_human_review" if reason else "pass",
    "reason": reason or "Verification data unavailable",
    "task_class": "unknown",
    "changed_files_non_bookkeeping": [],
}))
PY
)
    fi

    local audit_payload
    audit_payload=$(RALPH_AUDIT_TASK_JSON="$TASK_JSON" \
        RALPH_AUDIT_TITLE="$TASK_TITLE" \
        RALPH_AUDIT_STATUS="$audit_status" \
        RALPH_AUDIT_VERIFICATION_JSON="$verification_json_payload" \
        RALPH_AUDIT_CHANGED_FILES_JSON="$changed_files_json" \
        RALPH_AUDIT_REVIEW_JSON="${REVIEW_JSON:-{}}" \
        RALPH_AUDIT_REVIEW_RAW="${REVIEW:-}" \
        RALPH_AUDIT_ATTEMPTS="$CURRENT_ATTEMPT" \
        RALPH_AUDIT_DURATION="$audit_duration" \
        RALPH_AUDIT_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        RALPH_AUDIT_RUNTIME_SUCCESS="$runtime_success" \
        RALPH_AUDIT_VERIFIED_SUCCESS="$verified_success" \
        python3 - <<'PY'
import json
import os

def safe_json_load(raw: str, default):
    try:
        return json.loads(raw or json.dumps(default))
    except Exception:
        return default

task = safe_json_load(os.environ.get("RALPH_AUDIT_TASK_JSON", "{}"), {})
verification = safe_json_load(os.environ.get("RALPH_AUDIT_VERIFICATION_JSON", "{}"), {})
changes = safe_json_load(os.environ.get("RALPH_AUDIT_CHANGED_FILES_JSON", "[]"), [])
parsed_review = safe_json_load(os.environ.get("RALPH_AUDIT_REVIEW_JSON", "{}"), {})

payload = {
    "task_id": task.get("id", ""),
    "title": os.environ.get("RALPH_AUDIT_TITLE", ""),
    "status": os.environ.get("RALPH_AUDIT_STATUS", "failed"),
    "verification": {
        "result": verification.get("result", "needs_human_review"),
        "reason": verification.get("reason", ""),
        "task_class": verification.get("task_class", "unknown"),
        "evidence_files": verification.get("changed_files_non_bookkeeping", []),
    },
    "changes": {
        "all": changes,
        "non_bookkeeping": verification.get("changed_files_non_bookkeeping", []),
    },
    "review": {
        "raw": os.environ.get("RALPH_AUDIT_REVIEW_RAW", ""),
        "parsed": parsed_review,
    },
    "attempts": int(os.environ.get("RALPH_AUDIT_ATTEMPTS", "0") or 0),
    "duration_sec": int(os.environ.get("RALPH_AUDIT_DURATION", "0") or 0),
    "timestamp": os.environ.get("RALPH_AUDIT_TIMESTAMP", ""),
    "runtime_success": os.environ.get("RALPH_AUDIT_RUNTIME_SUCCESS", "false").lower() == "true",
    "verified_success": os.environ.get("RALPH_AUDIT_VERIFIED_SUCCESS", "false").lower() == "true",
}
print(json.dumps(payload, ensure_ascii=False))
PY
)

    if ! printf '%s' "$audit_payload" | python3 "$RALPH_DIR/scripts/audit_artifact.py" write >/dev/null 2>&1; then
        log "⚠️ Failed to persist audit artifact for $TASK_ID"
    fi
}

ensure_metrics_schema

validate_requested_task() {
    python3 - "$TARGET" <<'PY'
import json
import sys
from pathlib import Path

task_id = sys.argv[1]
data = json.loads(Path("tasks.json").read_text(encoding="utf-8"))
tasks = data.get("tasks", [])
completed_statuses = {"done", "verified_done"}

task = next((item for item in tasks if item.get("id") == task_id), None)
if task is None:
    print(f"❌ Requested task not found: {task_id}")
    raise SystemExit(1)

status = str(task.get("status", ""))
if status != "pending":
    print(f"❌ Requested task {task_id} is not runnable: status={status}")
    raise SystemExit(1)

unmet = [dep for dep in task.get("dependencies", []) if next((t for t in tasks if t.get("id") == dep and t.get("status") in completed_statuses), None) is None]
if unmet:
    print(f"❌ Requested task {task_id} is not runnable: unmet dependencies: {', '.join(unmet)}")
    raise SystemExit(1)

print(f"🎯 Requested task {task_id} is runnable and will be executed directly")
PY
}

log_deadlock_reason() {
    local explain_json reason ids details status_ids status_details prefix
    if [ "$MODE" = "phase" ]; then
        explain_json=$(python3 "$RALPH_DIR/scripts/next_task.py" --phase "$TARGET" --explain 2>/dev/null || echo '{}')
        prefix="Phase $TARGET"
    else
        explain_json=$(python3 "$RALPH_DIR/scripts/next_task.py" --explain 2>/dev/null || echo '{}')
        prefix="Auto"
    fi
    reason=$(printf '%s' "$explain_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('reason',''))" 2>/dev/null || echo "")
    if [ "$reason" != "blocked_dependencies" ] && [ "$reason" != "blocked_statuses" ]; then
        return 1
    fi
    ids=$(printf '%s' "$explain_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print(', '.join(item['id'] for item in data.get('blocked_pending', [])))" 2>/dev/null || true)
    details=$(printf '%s' "$explain_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print('; '.join(f\"{item['id']} needs {', '.join(item.get('unmet_dependencies', []))}\" for item in data.get('blocked_pending', [])))" 2>/dev/null || true)
    status_ids=$(printf '%s' "$explain_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print(', '.join(f\"{item['id']}({item.get('status','')})\" for item in data.get('blocked_by_status', [])))" 2>/dev/null || true)
    status_details=$(printf '%s' "$explain_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print('; '.join(f\"{item['id']} status={item.get('status','')}\" for item in data.get('blocked_by_status', [])))" 2>/dev/null || true)
    [ -n "$ids" ] && log "⚠️ $prefix deadlocked: pending tasks remain blocked by dependencies: $ids"
    [ -n "$details" ] && log "⚠️ $prefix blocked details: $details"
    [ -n "$status_ids" ] && log "⚠️ $prefix blocked by status: $status_ids"
    [ -n "$status_details" ] && log "⚠️ $prefix status details: $status_details"
    return 0
}

set_queue_exit_state() {
    local explain_json reason ids status_ids prefix

    FINAL_STATE_STATUS="idle"
    FINAL_STATE_STEP="idle"
    FINAL_NOTIFY_MESSAGE="🎉 Ralph finished! Run /status for details."

    if [ "$MODE" = "phase" ]; then
        explain_json=$(python3 "$RALPH_DIR/scripts/next_task.py" --phase "$TARGET" --explain 2>/dev/null || echo '{}')
        prefix="Phase $TARGET"
        FINAL_STATE_MESSAGE="$prefix complete"
        QUEUE_EXIT_LOG="🎉 $prefix complete!"
    else
        explain_json=$(python3 "$RALPH_DIR/scripts/next_task.py" --explain 2>/dev/null || echo '{}')
        prefix="Auto"
        FINAL_STATE_MESSAGE="All tasks complete"
        QUEUE_EXIT_LOG="🎉 All tasks complete!"
    fi

    reason=$(printf '%s' "$explain_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('reason',''))" 2>/dev/null || echo "")
    if [ "$reason" = "blocked_dependencies" ]; then
        ids=$(printf '%s' "$explain_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print(', '.join(item['id'] for item in data.get('blocked_pending', [])))" 2>/dev/null || true)
        FINAL_STATE_STEP="deadlocked"
        FINAL_STATE_MESSAGE="$prefix deadlocked: pending tasks remain blocked by dependencies"
        [ -n "$ids" ] && FINAL_STATE_MESSAGE="$FINAL_STATE_MESSAGE: $ids"
        FINAL_NOTIFY_MESSAGE="⚠️ Ralph stopped: pending tasks remain blocked. Run /status for details."
        if [ "$MODE" = "phase" ]; then
            QUEUE_EXIT_LOG="⚠️ No runnable tasks remain in $prefix; pending tasks are blocked."
        else
            QUEUE_EXIT_LOG="⚠️ No runnable tasks remain; pending tasks are blocked."
        fi
    elif [ "$reason" = "blocked_statuses" ]; then
        status_ids=$(printf '%s' "$explain_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print(', '.join(f\"{item['id']}({item.get('status','')})\" for item in data.get('blocked_by_status', [])))" 2>/dev/null || true)
        FINAL_STATE_STEP="deadlocked"
        FINAL_STATE_MESSAGE="$prefix blocked: unresolved tasks remain non-runnable by status"
        [ -n "$status_ids" ] && FINAL_STATE_MESSAGE="$FINAL_STATE_MESSAGE: $status_ids"
        FINAL_NOTIFY_MESSAGE="⚠️ Ralph stopped: unresolved tasks remain blocked by status. Run /status for details."
        if [ "$MODE" = "phase" ]; then
            QUEUE_EXIT_LOG="⚠️ No runnable tasks remain in $prefix; unresolved tasks are blocked by status."
        else
            QUEUE_EXIT_LOG="⚠️ No runnable tasks remain; unresolved tasks are blocked by status."
        fi
    fi
}

set_task_success_exit_state() {
    FINAL_STATE_STATUS="idle"
    FINAL_STATE_STEP="completed"
    FINAL_STATE_MESSAGE="Task $TASK_ID complete"
    FINAL_NOTIFY_MESSAGE="✅ Ralph finished requested task $TASK_ID. Run /status for details."
    QUEUE_EXIT_LOG="✅ Requested task $TASK_ID complete!"
}

persist_task_success_state() {
    is_single_task_mode || return 0
    set_task_success_exit_state
    write_state "$FINAL_STATE_STATUS" "" "$FINAL_STATE_STEP" "$FINAL_STATE_MESSAGE"
}

sanitize_fix_instructions() {
    local raw_fix="${1:-}"
    local sanitized_output=""

    sanitized_output=$(RALPH_RAW_FIX="$raw_fix" python3 - <<'PY'
import json
import os
import re

raw = os.environ.get("RALPH_RAW_FIX", "").strip()
if not raw:
    print(json.dumps({
        "mode": "empty",
        "sanitized": "",
        "reason": "Tech Lead returned empty fix instructions.",
    }, ensure_ascii=False))
    raise SystemExit(0)

banned_patterns = [
    r"\btasks\.json\b",
    r"\bprogress\.md\b",
    r"\bcompleted_at\b",
    r"\brevision_notes\b",
    r"\bfinal commit\b",
    r"\bcommit message\b",
    r"\bstatus update\b",
    r"\bupdate task status\b",
    r"\bgit diff\b",
    r"\bnon-?empty diff\b",
    r"\breal diff\b",
]

sentence_split = re.split(r"(?<=[.!?])\s+|\n+", raw)
kept = []
removed = []
for chunk in sentence_split:
    sentence = chunk.strip(" \t-")
    if not sentence:
        continue
    if any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in banned_patterns):
        removed.append(sentence)
    else:
        kept.append(sentence)

sanitized = " ".join(kept).strip()
sanitized = re.sub(r"\s+", " ", sanitized).strip()

if removed and not sanitized:
    print(json.dumps({
        "mode": "contradictory_only",
        "sanitized": "",
        "reason": "Tech Lead requested only runtime-owned bookkeeping or diff-production work and did not specify a coder-owned implementation gap.",
        "removed": removed,
    }, ensure_ascii=False))
elif removed:
    print(json.dumps({
        "mode": "sanitized",
        "sanitized": sanitized,
        "reason": "Removed runtime-owned bookkeeping/diff demands from Tech Lead fix instructions.",
        "removed": removed,
    }, ensure_ascii=False))
else:
    print(json.dumps({
        "mode": "unchanged",
        "sanitized": raw,
        "reason": "",
        "removed": [],
    }, ensure_ascii=False))
PY
)

    FIX_SANITIZE_MODE=$(printf '%s' "$sanitized_output" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('mode', 'unchanged'))
except Exception:
    print('unchanged')
" 2>/dev/null || echo "unchanged")
    FIX_SANITIZED_TEXT=$(printf '%s' "$sanitized_output" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('sanitized', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")
    FIX_SANITIZE_REASON=$(printf '%s' "$sanitized_output" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('reason', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")
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
run_control_helper() {
    local subcommand="$1"
    shift || true

    local helper_output=""
    local helper_stderr=""
    helper_stderr=$(mktemp "${TMPDIR:-/tmp}/ralph_control_stderr.XXXXXX") || {
        log "⚠️ Control helper '${subcommand}' failed: unable to allocate temp file for stderr capture"
        return 1
    }

    if ! helper_output=$(python3 "$RALPH_DIR/scripts/ralph_common.py" "$subcommand" "$@" 2>"$helper_stderr"); then
        if [ -s "$helper_stderr" ]; then
            while IFS= read -r line; do
                [ -n "$line" ] && log "⚠️ Control helper '${subcommand}': $line"
            done < "$helper_stderr"
        fi
        rm -f "$helper_stderr"
        log "⚠️ Control helper '${subcommand}' failed"
        return 1
    fi

    if [ -s "$helper_stderr" ]; then
        while IFS= read -r line; do
            [ -n "$line" ] && log "⚠️ Control helper '${subcommand}': $line"
        done < "$helper_stderr"
    fi
    rm -f "$helper_stderr"

    printf '%s' "$helper_output"
    return 0
}

read_control_file() {
    local helper_output=""
    if ! helper_output=$(run_control_helper control-read); then
        log "⚠️ Failed to read ralph_control.json; defaulting to continue"
        printf "continue\n\n"
        return 0
    fi
    if [ -z "$helper_output" ]; then
        log "⚠️ Control helper returned empty control payload; defaulting to continue"
        printf "continue\n\n"
        return 0
    fi
    printf '%s\n' "$helper_output"
}

parse_control_data() {
    local context="$1"
    local control_data="$2"
    local action target

    action=$(printf '%s\n' "$control_data" | sed -n '1p')
    target=$(printf '%s\n' "$control_data" | sed -n '2p')

    if [ -z "$action" ]; then
        log "⚠️ ${context}: empty control action from ralph_control.json; defaulting to continue"
        CONTROL_ACTION="continue"
        CONTROL_TARGET=""
        return 1
    fi

    CONTROL_ACTION="$action"
    CONTROL_TARGET="$target"
    return 0
}

apply_control_action_snapshot() {
    local context="$1"
    local control_data=""

    control_data=$(read_control_file)
    parse_control_data "$context" "$control_data" || return 1
    return 0
}

clear_control_action() {
    run_control_helper control-clear >/dev/null || {
        log "⚠️ Failed to clear control action in ralph_control.json"
        return 1
    }
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
            apply_control_action_snapshot "check_control" || true
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
                    apply_control_action_snapshot "check_control pause loop" || true
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
            apply_control_action_snapshot "wait_for_high_risk_approval" || true
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

set_control_action() {
    local action="$1"
    local comment="${2:-}"
    run_control_helper control-write "$action" "$comment" >/dev/null || {
        log "⚠️ Failed to write control action '${action}' to ralph_control.json"
        return 1
    }
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

wait_for_required_assets() {
    local poll_interval="${RALPH_ASSET_POLL_INTERVAL:-5}"
    local announced_wait=0
    local sync_output=""
    local sync_status=0
    local waiting_count=0
    local copied_count=0
    local moved_count=0

    if [ ! -f "assets_manifest.json" ]; then
        return 0
    fi

    while true; do
        set +e
        sync_output=$(python3 "$RALPH_DIR/scripts/manage_assets.py" sync 2>/dev/null)
        sync_status=$?
        set -e

        if [ -z "$sync_output" ]; then
            sync_output='{}'
        fi

        if [ $sync_status -eq 1 ]; then
            local manifest_error
            manifest_error=$(printf '%s' "$sync_output" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
print(data.get('error', 'Invalid assets_manifest.json'))
" 2>/dev/null || echo "Invalid assets_manifest.json")
            log "❌ assets_manifest.json invalid: $manifest_error"
            notify "❌ $TASK_ID invalid assets_manifest.json: $manifest_error"
            return 1
        fi

        waiting_count=$(printf '%s' "$sync_output" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
print(data.get('summary', {}).get('waiting', 0))
" 2>/dev/null || echo "0")
        copied_count=$(printf '%s' "$sync_output" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
summary = data.get('summary', {})
print(summary.get('copied', 0))
" 2>/dev/null || echo "0")
        moved_count=$(printf '%s' "$sync_output" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
summary = data.get('summary', {})
print(summary.get('moved', 0))
" 2>/dev/null || echo "0")

        if [ $sync_status -eq 0 ]; then
            if [ $copied_count -gt 0 ] || [ $moved_count -gt 0 ]; then
                log "🖼️ Asset sync applied: copied=$copied_count moved=$moved_count"
            fi
            if [ $announced_wait -eq 1 ]; then
                log "✅ Required assets are ready. Resuming task $TASK_ID."
                notify "✅ Assets ready for $TASK_ID. Resuming."
                write_state "running" "$TASK_ID" "assets_ready" "Required assets available"
            fi
            return 0
        fi

        if [ $announced_wait -eq 0 ]; then
            log "⏸ Waiting for required assets: $waiting_count pending from assets_manifest.json"
            notify "⏸ $TASK_ID waiting for $waiting_count required assets from assets_manifest.json"
            write_state "waiting_human" "$TASK_ID" "asset_wait" "Waiting for required assets from assets_manifest.json"
            announced_wait=1
        fi

        CONTROL_STATUS=0
        check_control || CONTROL_STATUS=$?
        if [ $CONTROL_STATUS -eq 1 ]; then
            return 10
        elif [ $CONTROL_STATUS -eq 2 ] && { [ -z "$CONTROL_TARGET" ] || [ "$CONTROL_TARGET" = "$TASK_ID" ]; }; then
            return 11
        fi

        sleep "$poll_interval"
    done
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

count_prompt_tokens() {
    python3 -c '
import re
import sys
text = sys.stdin.read()
tokens = re.findall(r"\S+", text)
print(len(tokens))
'
}

get_coder_prompt_token_budget() {
    local prompt_profile="${1:-broad}"

    if [ -n "${RALPH_CODER_PROMPT_MAX_TOKENS:-}" ]; then
        printf '%s' "${RALPH_CODER_PROMPT_MAX_TOKENS}"
        return 0
    fi

    if [ "$prompt_profile" = "narrow" ]; then
        printf '%s' "${RALPH_CODER_PROMPT_MAX_TOKENS_NARROW:-15000}"
        return 0
    fi

    printf '%s' "${RALPH_CODER_PROMPT_MAX_TOKENS_BROAD:-25000}"
}

check_prompt_budget() {
    local prompt_text="$1"
    local max_tokens="$2"
    local prompt_label="${3:-Prompt}"
    local prompt_tokens="${4:-}"

    if [ -z "$prompt_tokens" ]; then
        prompt_tokens=$(printf '%s' "$prompt_text" | count_prompt_tokens)
    fi
    if [ "${prompt_tokens:-0}" -gt "$max_tokens" ]; then
        log "❌ Prompt budget exceeded for ${prompt_label}: ${prompt_tokens} tokens > ${max_tokens}"
        return 1
    fi
    return 0
}

log_coder_prompt_tokens() {
    local prompt_profile="${1:-broad}"
    local prompt_tokens="${2:-0}"
    local prompt_budget="${3:-0}"
    log "🧮 Coder prompt tokens: profile=${prompt_profile} tokens=${prompt_tokens} limit=${prompt_budget}"
}


build_required_context_content() {
    local context_files="${1:-}"
    local prompt_profile="${2:-broad}"
    local context_content=""
    local max_chars=""
    local per_file_max_chars=""

    if [ -n "${RALPH_REQUIRED_CONTEXT_MAX_CHARS:-}" ]; then
        max_chars="${RALPH_REQUIRED_CONTEXT_MAX_CHARS}"
    elif [ "$prompt_profile" = "narrow" ]; then
        max_chars="${RALPH_REQUIRED_CONTEXT_MAX_CHARS_NARROW:-4000}"
    else
        max_chars="${RALPH_REQUIRED_CONTEXT_MAX_CHARS_BROAD:-6000}"
    fi

    if [ -n "${RALPH_REQUIRED_CONTEXT_PER_FILE_MAX_CHARS:-}" ]; then
        per_file_max_chars="${RALPH_REQUIRED_CONTEXT_PER_FILE_MAX_CHARS}"
    elif [ "$prompt_profile" = "narrow" ]; then
        per_file_max_chars="${RALPH_REQUIRED_CONTEXT_PER_FILE_MAX_CHARS_NARROW:-2000}"
    else
        per_file_max_chars="${RALPH_REQUIRED_CONTEXT_PER_FILE_MAX_CHARS_BROAD:-3000}"
    fi

    if [ -n "$context_files" ]; then
        local ctx_file
        for ctx_file in $context_files; do
            if [ -f "$ctx_file" ]; then
                context_content="${context_content}
## File: $ctx_file
$(read_file_for_prompt "$ctx_file" "$per_file_max_chars")
"
                if [ "${#context_content}" -ge "$max_chars" ]; then
                    break
                fi
            fi
        done
    fi

    printf '%s' "$context_content" | clip_chars "$max_chars"
}

load_coder_prompt_project_context() {
    local prompt_profile="${1:-broad}"

    CODER_PROMPT_PROJECT_AGENTS=""
    CODER_PROMPT_PROJECT_ARCHITECTURE=""
    CODER_PROMPT_PROJECT_MEMORY_SYSTEM=""
    CODER_PROMPT_MEMORY_CORE=""
    CODER_PROMPT_MEMORY_RECENT=""

    if [ "$prompt_profile" = "narrow" ]; then
        return 0
    fi

    if [ -f "AGENTS.md" ]; then
        CODER_PROMPT_PROJECT_AGENTS=$(read_file_for_prompt "AGENTS.md" "${RALPH_AGENTS_MAX_CHARS:-8000}" || true)
    fi
    if [ -f "ARCHITECTURE.md" ]; then
        CODER_PROMPT_PROJECT_ARCHITECTURE=$(read_file_for_prompt "ARCHITECTURE.md" "${RALPH_ARCHITECTURE_MAX_CHARS:-10000}" || true)
    fi
    if [ -f "MEMORY_SYSTEM.md" ]; then
        CODER_PROMPT_PROJECT_MEMORY_SYSTEM=$(read_file_for_prompt "MEMORY_SYSTEM.md" "${RALPH_MEMORY_SYSTEM_MAX_CHARS:-8000}" || true)
    fi
    if [ -f ".ralph/memory/core.md" ]; then
        CODER_PROMPT_MEMORY_CORE=$(read_file_for_prompt ".ralph/memory/core.md" "${RALPH_MEMORY_CORE_MAX_CHARS:-8000}" || true)
    fi
    if [ -f ".ralph/memory/recent.md" ]; then
        CODER_PROMPT_MEMORY_RECENT=$(read_file_for_prompt ".ralph/memory/recent.md" "${RALPH_MEMORY_RECENT_MAX_CHARS:-8000}" || true)
    fi
}

build_task_prompt_payload() {
    local task_json="$1"
    local prompt_profile="${2:-broad}"

    python3 - "$prompt_profile" "$task_json" <<'PY'
from __future__ import annotations

import json
import sys

prompt_profile = sys.argv[1]
task = json.loads(sys.argv[2])

if prompt_profile == "narrow":
    description_limit = 1200
    criteria_limit = 8
    criteria_chars = 2000
    context_limit = 8
    notes_limit = 800
else:
    description_limit = 2000
    criteria_limit = 16
    criteria_chars = 4000
    context_limit = 12
    notes_limit = 1200


def compact(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ... [truncated]"


lines: list[str] = []
for key, label in (
    ("id", "ID"),
    ("phase", "Phase"),
    ("title", "Title"),
    ("status", "Status"),
    ("complexity", "Complexity"),
    ("category", "Category"),
    ("priority", "Priority"),
):
    value = task.get(key)
    if value not in (None, ""):
        lines.append(f"{label}: {value}")

description = task.get("description")
if description:
    lines.append("")
    lines.append("Description:")
    lines.append(compact(description, description_limit))

required_context = [str(item) for item in (task.get("required_context") or []) if str(item).strip()]
if required_context:
    lines.append("")
    lines.append("Required Context:")
    for item in required_context[:context_limit]:
        lines.append(f"- {item}")
    if len(required_context) > context_limit:
        lines.append(f"- ... [{len(required_context) - context_limit} more entries truncated]")

criteria = [compact(item, 240) for item in (task.get("acceptance_criteria") or []) if str(item).strip()]
if criteria:
    lines.append("")
    lines.append("Acceptance Criteria:")
    used_chars = 0
    emitted = 0
    for item in criteria:
        projected = used_chars + len(item)
        if emitted >= criteria_limit or projected > criteria_chars:
            break
        lines.append(f"- {item}")
        emitted += 1
        used_chars = projected
    remaining = len(criteria) - emitted
    if remaining > 0:
        lines.append(f"- ... [{remaining} more criteria truncated]")

revision_notes = task.get("revision_notes")
if revision_notes not in (None, ""):
    lines.append("")
    lines.append("Revision Notes:")
    lines.append(compact(revision_notes, notes_limit))

completed_at = task.get("completed_at")
if completed_at not in (None, ""):
    lines.append("")
    lines.append(f"Completed At: {completed_at}")

print("\n".join(lines), end="")
PY
}

summarize_retry_test_output() {
    local raw_output="${1:-}"

    RALPH_RETRY_TEST_OUTPUT="$raw_output" python3 - <<'PY'
import os
import re

raw = os.environ.get("RALPH_RETRY_TEST_OUTPUT", "")
if not raw.strip():
    raise SystemExit(0)

lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
markers = ("FAIL", "FAILED", "ERROR", "AssertionError", "Traceback", "not ok", "tests failed")
selected = []
seen = set()

for line in lines:
    if any(marker in line for marker in markers):
        normalized = line.strip()
        if normalized not in seen:
            selected.append(normalized)
            seen.add(normalized)

if not selected:
    raise SystemExit(0)

summary = "\n".join(selected[:12])
if len(summary) > 2000:
    summary = summary[:1997] + "..."
print(summary)
PY
}

build_retry_attempt_context() {
    local previous_attempt_number="$1"
    local previous_review_target_hash="$2"
    local previous_diff_bytes="$3"
    local previous_diff_summary="$4"
    local previous_feedback_source="${5:-}"
    local previous_feedback="${6:-}"
    local previous_test_output="${7:-}"

    PREVIOUS_ATTEMPT_NUMBER="$previous_attempt_number" \
    PREVIOUS_REVIEW_TARGET_HASH="$previous_review_target_hash" \
    PREVIOUS_DIFF_BYTES="$previous_diff_bytes" \
    PREVIOUS_DIFF_SUMMARY="$previous_diff_summary" \
    PREVIOUS_FEEDBACK_SOURCE="$previous_feedback_source" \
    PREVIOUS_FEEDBACK="$previous_feedback" \
    PREVIOUS_TEST_OUTPUT="$previous_test_output" \
    python3 - <<'PY'
import os
import re

attempt = os.environ.get("PREVIOUS_ATTEMPT_NUMBER", "").strip()
review_hash = os.environ.get("PREVIOUS_REVIEW_TARGET_HASH", "").strip()
diff_bytes = os.environ.get("PREVIOUS_DIFF_BYTES", "").strip() or "0"
diff_summary = os.environ.get("PREVIOUS_DIFF_SUMMARY", "").strip()
feedback_source = os.environ.get("PREVIOUS_FEEDBACK_SOURCE", "").strip()
feedback = os.environ.get("PREVIOUS_FEEDBACK", "").strip()
test_output = os.environ.get("PREVIOUS_TEST_OUTPUT", "").strip()

sections = []

if review_hash or diff_summary:
    parts = []
    if review_hash:
        parts.append(f"Review target hash: {review_hash}")
    parts.append(f"Previous diff snapshot: {diff_bytes} bytes")
    if diff_summary:
        parts.append("What changed in prior attempt:")
        parts.append(diff_summary)
    sections.append("\n".join(parts))

if feedback:
    label = {
        "lead": "Lead review feedback from prior attempt:",
        "verification": "Verification feedback from prior attempt:",
    }.get(feedback_source, "Retry guidance from prior attempt:")
    sections.append(f"{label}\n{feedback}")

if test_output:
    sections.append(f"Failed tests from prior attempt:\n{test_output}")

reason_bits = []
if feedback_source == "lead":
    reason_bits.append("Tech Lead rejected the prior attempt")
elif feedback_source == "verification":
    reason_bits.append("closure verification still found an implementation gap")
elif feedback:
    reason_bits.append("the prior attempt still missed the task target")

if test_output:
    reason_bits.append("tests reported failures")

reason_clause = " and ".join(reason_bits) if reason_bits else "the prior attempt did not satisfy the task"
try_clause = re.sub(r"\s+", " ", feedback.replace("\n", " ")).strip()
try_clause = try_clause.rstrip(".")
if not try_clause:
    try_clause = "make a materially different patch that addresses the failure context above"

if attempt:
    sections.append(f"Attempt {attempt} failed because {reason_clause}, try {try_clause} instead.")

print("\n\n".join(section for section in sections if section.strip()))
PY
}

build_coder_prompt() {
    local task_prompt_payload="$1"
    local coder_role_file="$2"
    local coder_role_content="$3"
    local coder_prompt_profile_name="$4"
    local coder_prompt_targets="$5"
    local context_content="$6"
    local relevant_context="$7"
    local project_agents="$8"
    local project_architecture="$9"
    local project_memory_system="${10}"
    local memory_core="${11}"
    local memory_recent="${12}"
    local fix_instructions="${13:-}"
    local human_comment="${14:-}"
    local previous_attempt_context="${15:-}"
    local coder_prompt=""

    if [ "$coder_prompt_profile_name" = "narrow" ]; then
        coder_prompt="Read ${coder_role_file} first. Use AGENTS.md only if repository conventions become ambiguous. Use progress.md only as lightweight narrative context if needed; do not treat it as task truth.
Do NOT run make test or pytest. Ralph runtime owns verification.

## Role Instructions (${coder_role_file})
${coder_role_content:-No role-specific instructions found. Fall back to AGENTS_CODER.md conventions.}

## Exact Task Targets
${coder_prompt_targets:-No explicit concrete target paths detected.}

## Required Context Files
${context_content:-No specific files required.}

## Relevant Source Snippets
${relevant_context:-No keyword-matched source snippets found.}

## Your Task
${task_prompt_payload:-No task payload provided.}"
    else
        coder_prompt="Read AGENTS.md, ARCHITECTURE.md, MEMORY_SYSTEM.md, and ${coder_role_file} first. Use progress.md only as lightweight narrative context if needed; do not treat it as task truth.
Do NOT run make test or pytest. Ralph runtime owns verification.

## Architecture Doc
${project_architecture:-No ARCHITECTURE.md provided. Use AGENTS.md and the repository structure.}

## AGENTS.md Context
${project_agents:-No AGENTS.md provided.}

## Memory System Doc
${project_memory_system:-No MEMORY_SYSTEM.md provided. Use AGENTS.md and .ralph/memory/.}

## Role Instructions (${coder_role_file})
${coder_role_content:-No role-specific instructions found. Fall back to AGENTS_CODER.md conventions.}

## Project Context (from memory)
${memory_core:-No core context yet. Read ARCHITECTURE.md and AGENTS.md for project info.}

## Recent Tasks (what was done before you)
${memory_recent:-No recent tasks yet. This may be the first task.}

## Required Context Files
${context_content:-No specific files required.}

## Relevant Source Snippets
${relevant_context:-No keyword-matched source snippets found.}

## Your Task
${task_prompt_payload:-No task payload provided.}"
    fi

    if [ -n "$fix_instructions" ]; then
        coder_prompt="$coder_prompt

## Fix Instructions from Tech Lead (MUST address)
$fix_instructions"
    fi

    if [ -n "$human_comment" ]; then
        coder_prompt="$coder_prompt

## Human Comment (from project owner via Telegram)
$human_comment"
    fi

    if [ -n "$previous_attempt_context" ]; then
        coder_prompt="$coder_prompt

## Previous Attempt Context
$previous_attempt_context"
    fi

    coder_prompt="$coder_prompt

## Rules
- **Think before coding**: You MUST wrap your plan inside <thinking> tags before writing any code blocks. Briefly analyze the requirements and file structure there.
- Implement ONLY this task
- Follow acceptance_criteria exactly
- Do NOT run make test or pytest. Ralph runtime owns verification.
- Do NOT modify tasks.json or progress.md
- Ralph runtime owns final task bookkeeping: tasks.json, progress.md, final status, audit artifacts, and final task commits
- If fix instructions mention runtime-owned bookkeeping, address only the real implementation gap

Expected response structure:
<thinking>
1. Need to modify app.py to add login route.
2. Will use flask-login library.
3. Need to update requirements.txt first.
</thinking>
\`\`\`python
... code ...
\`\`\`"

    printf '%s' "$coder_prompt"
}

build_coder_prompt_with_budget() {
    local task_json="$1"
    local coder_role_file="$2"
    local coder_role_content="$3"
    local coder_prompt_profile_name="$4"
    local coder_prompt_targets="$5"
    local context_content="$6"
    local relevant_context="$7"
    local project_agents="$8"
    local project_architecture="$9"
    local project_memory_system="${10}"
    local memory_core="${11}"
    local memory_recent="${12}"
    local fix_instructions="${13:-}"
    local human_comment="${14:-}"
    local previous_attempt_context="${15:-}"
    local prompt_budget="${16:-0}"
    local prompt_max_chars="${17:-${RALPH_CODER_PROMPT_MAX_CHARS:-40000}}"
    local coder_prompt=""
    local prompt_tokens=0
    local task_prompt_payload=""
    local trim_plan=""
    local trim_step=""
    local trim_field=""
    local trim_limit=""

    task_prompt_payload=$(build_task_prompt_payload "$task_json" "$coder_prompt_profile_name")
    coder_prompt=$(build_coder_prompt \
        "$task_prompt_payload" \
        "$coder_role_file" \
        "$coder_role_content" \
        "$coder_prompt_profile_name" \
        "$coder_prompt_targets" \
        "$context_content" \
        "$relevant_context" \
        "$project_agents" \
        "$project_architecture" \
        "$project_memory_system" \
        "$memory_core" \
        "$memory_recent" \
        "$fix_instructions" \
        "$human_comment" \
        "$previous_attempt_context")
    prompt_tokens=$(printf '%s' "$coder_prompt" | count_prompt_tokens)

    if [ "$coder_prompt_profile_name" = "narrow" ]; then
        trim_plan="relevant_context:${RALPH_CONTEXT_MAX_CHARS_NARROW_FALLBACK:-2000}
context_content:${RALPH_REQUIRED_CONTEXT_MAX_CHARS_NARROW_FALLBACK:-2000}
coder_role_content:${RALPH_ROLE_MAX_CHARS_NARROW_FALLBACK:-4000}"
    else
        trim_plan="relevant_context:${RALPH_CONTEXT_MAX_CHARS_BROAD_FALLBACK:-6000}
context_content:${RALPH_REQUIRED_CONTEXT_MAX_CHARS_BROAD_FALLBACK:-3000}
task_prompt_payload:${RALPH_TASK_PAYLOAD_MAX_CHARS_BROAD_FALLBACK:-5000}
memory_recent:${RALPH_MEMORY_RECENT_MAX_CHARS_FALLBACK:-3000}
memory_core:${RALPH_MEMORY_CORE_MAX_CHARS_FALLBACK:-4000}
project_architecture:${RALPH_ARCHITECTURE_MAX_CHARS_FALLBACK:-4000}
project_agents:${RALPH_AGENTS_MAX_CHARS_FALLBACK:-3000}
project_memory_system:${RALPH_MEMORY_SYSTEM_MAX_CHARS_FALLBACK:-3000}
coder_role_content:${RALPH_ROLE_MAX_CHARS_BROAD_FALLBACK:-5000}"
    fi

    while IFS= read -r trim_step; do
        [ -n "$trim_step" ] || continue
        [ "$prompt_tokens" -le "$prompt_budget" ] && break
        trim_field="${trim_step%%:*}"
        trim_limit="${trim_step#*:}"

        case "$trim_field" in
            relevant_context)
                [ -n "$relevant_context" ] || continue
                relevant_context=$(printf '%s' "$relevant_context" | clip_chars "$trim_limit")
                ;;
            context_content)
                [ -n "$context_content" ] || continue
                context_content=$(printf '%s' "$context_content" | clip_chars "$trim_limit")
                ;;
            task_prompt_payload)
                [ -n "$task_prompt_payload" ] || continue
                task_prompt_payload=$(printf '%s' "$task_prompt_payload" | clip_chars "$trim_limit")
                ;;
            memory_recent)
                [ -n "$memory_recent" ] || continue
                memory_recent=$(printf '%s' "$memory_recent" | clip_chars "$trim_limit")
                ;;
            memory_core)
                [ -n "$memory_core" ] || continue
                memory_core=$(printf '%s' "$memory_core" | clip_chars "$trim_limit")
                ;;
            project_architecture)
                [ -n "$project_architecture" ] || continue
                project_architecture=$(printf '%s' "$project_architecture" | clip_chars "$trim_limit")
                ;;
            project_agents)
                [ -n "$project_agents" ] || continue
                project_agents=$(printf '%s' "$project_agents" | clip_chars "$trim_limit")
                ;;
            project_memory_system)
                [ -n "$project_memory_system" ] || continue
                project_memory_system=$(printf '%s' "$project_memory_system" | clip_chars "$trim_limit")
                ;;
            coder_role_content)
                [ -n "$coder_role_content" ] || continue
                coder_role_content=$(printf '%s' "$coder_role_content" | clip_chars "$trim_limit")
                ;;
            *)
                continue
                ;;
        esac

        coder_prompt=$(build_coder_prompt \
            "$task_prompt_payload" \
            "$coder_role_file" \
            "$coder_role_content" \
            "$coder_prompt_profile_name" \
            "$coder_prompt_targets" \
            "$context_content" \
            "$relevant_context" \
            "$project_agents" \
            "$project_architecture" \
            "$project_memory_system" \
            "$memory_core" \
            "$memory_recent" \
            "$fix_instructions" \
            "$human_comment" \
            "$previous_attempt_context")
        prompt_tokens=$(printf '%s' "$coder_prompt" | count_prompt_tokens)
    done <<< "$trim_plan"

    coder_prompt=$(printf '%s' "$coder_prompt" | enforce_prompt_budget "$prompt_max_chars")
    prompt_tokens=$(printf '%s' "$coder_prompt" | count_prompt_tokens)

    printf '__TOKENS__:%s\n' "$prompt_tokens"
    printf '%s' "$coder_prompt"
}

build_relevant_context() {
    local task_json="$1"
    local prompt_profile="${2:-broad}"
    local max_files=""
    local max_chars=""

    if [ -n "${RALPH_CONTEXT_MAX_FILES:-}" ]; then
        max_files="${RALPH_CONTEXT_MAX_FILES}"
    elif [ "$prompt_profile" = "narrow" ]; then
        max_files="${RALPH_CONTEXT_MAX_FILES_NARROW:-3}"
    else
        max_files="${RALPH_CONTEXT_MAX_FILES_BROAD:-6}"
    fi

    if [ -n "${RALPH_CONTEXT_MAX_CHARS:-}" ]; then
        max_chars="${RALPH_CONTEXT_MAX_CHARS}"
    elif [ "$prompt_profile" = "narrow" ]; then
        max_chars="${RALPH_CONTEXT_MAX_CHARS_NARROW:-4000}"
    else
        max_chars="${RALPH_CONTEXT_MAX_CHARS_BROAD:-12000}"
    fi

    python3 - "$PROJECT_DIR" "$max_files" "$max_chars" "$prompt_profile" "$task_json" <<'PY'
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

project_dir = pathlib.Path(sys.argv[1]).resolve()
max_files = int(sys.argv[2])
max_chars = int(sys.argv[3])
prompt_profile = sys.argv[4]
task_payload = sys.argv[5]
if prompt_profile == "narrow":
    per_file_limit = max(600, min(1600, max_chars // 2))
    max_hit_lines = 4
    max_hit_ranges = 2
else:
    per_file_limit = max(800, max_chars // 2)
    max_hit_lines = 6
    max_hit_ranges = 3

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
        if len(hit_lines) >= max_hit_lines:
            break

    ranges: list[tuple[int, int]] = []
    for hit_line in hit_lines[:max_hit_ranges]:
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
    if ! run_control_helper control-consume-comment; then
        log "⚠️ Failed to consume operator comment from ralph_control.json"
        return 0
    fi
}

notify() {
    local notify_output=""
    if ! notify_output=$(python3 "$RALPH_DIR/scripts/ralph_notify.py" "$*" 2>&1 >/dev/null); then
        log "⚠️ Notification helper exited with error: ${notify_output:-unknown error}"
        return 0
    fi
    if [ -n "$notify_output" ]; then
        log "⚠️ Notification helper: $notify_output"
    fi
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
    local task_class
    task_class=$(detect_runtime_task_class 2>/dev/null || echo "implementation")
    local allow_timeout_retries=1
    if [ "$task_class" = "docs-only" ]; then
        allow_timeout_retries=0
    fi

    while [ $retry -le $MAX_CODEX_RETRIES ]; do
        : > "$output_file"
        local watchdog_flag
        watchdog_flag="/tmp/ralph_watchdog_${$}_${retry}.flag"
        local stream_fifo="/tmp/ralph_codex_stream_${$}_${retry}.fifo"
        local stream_logger_pid=""
        rm -f "$watchdog_flag"
        rm -f "$stream_fifo"
        mkfifo "$stream_fifo"
        (
            while IFS= read -r stream_line || [ -n "$stream_line" ]; do
                log "[CODEX] $stream_line"
            done < "$stream_fifo"
        ) &
        stream_logger_pid=$!
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
        python3 - "$output_file" "$launcher_meta" "$stream_fifo" "${runner[@]}" <<'PY' &
import os
import subprocess
import sys
import threading
import time

output_file = sys.argv[1]
meta_file = sys.argv[2]
stream_file = sys.argv[3]
cmd = sys.argv[4:]

with open(output_file, "w", encoding="utf-8", errors="replace") as out, open(
    stream_file, "w", encoding="utf-8", errors="replace", buffering=1
) as stream:
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

    def pump_stream() -> None:
        pos = 0
        pending = ""
        idle_loops = 0
        while True:
            with open(output_file, "r", encoding="utf-8", errors="replace") as reader:
                reader.seek(pos)
                chunk = reader.read()
                pos = reader.tell()
            if chunk:
                idle_loops = 0
                pending += chunk
                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    stream.write(line + "\n")
                    stream.flush()
            else:
                idle_loops += 1
            if proc.poll() is not None and idle_loops >= 3:
                break
            time.sleep(0.1)
        if pending:
            stream.write(pending + "\n")
            stream.flush()

    pump_thread = threading.Thread(target=pump_stream, daemon=True)
    pump_thread.start()
    exit_code = proc.wait()
    pump_thread.join(timeout=1)
    sys.exit(exit_code)
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
        local archived_output=""
        if [ -f "$watchdog_flag" ]; then
            watchdog_fired=1
        fi
        rm -f "$watchdog_flag"

        rm -f "$PROJECT_DIR/ralph_codex.pid"
        rm -f "$PROJECT_DIR/ralph_codex.pgid"
        rm -f "$launcher_meta"
        rm -f "$stream_fifo"
        pkill -P "$$" 2>/dev/null || true

        # Watchdog timeout - retry with backoff like other recoverable errors.
        if [ "$watchdog_fired" -eq 1 ]; then
            finalize_codex_stream_logger "$stream_logger_pid" "$stream_fifo"
            archived_output=$(archive_codex_output "$output_file" "$((retry + 1))")
            [ -n "$archived_output" ] && log "📝 Saved codex output: $archived_output"
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            if [ "$allow_timeout_retries" -eq 0 ]; then
                log "❌ Watchdog timeout on docs-only task; timeout retries disabled"
                return 1
            fi
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
            finalize_codex_stream_logger "$stream_logger_pid" "$stream_fifo"
            CONSECUTIVE_FAILURES=0
            return 0
        fi

        # Timeout (124) - clean up aggressively, then retry with backoff.
        if [ $exit_code -eq 124 ]; then
            terminate_codex_run "$codex_pid" "$codex_pgid"
            finalize_codex_stream_logger "$stream_logger_pid" "$stream_fifo"
            archived_output=$(archive_codex_output "$output_file" "$((retry + 1))")
            [ -n "$archived_output" ] && log "📝 Saved codex output: $archived_output"
            log "⏰ TIMEOUT: codex exceeded ${timeout}s"
            notify "⏰ Codex timeout on ${TASK_ID:-unknown}. Cleaning up process tree."
            if [ "$allow_timeout_retries" -eq 0 ]; then
                log "❌ Codex timed out on docs-only task; timeout retries disabled"
                CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
                return 124
            fi
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

        finalize_codex_stream_logger "$stream_logger_pid" "$stream_fifo"
        archived_output=$(archive_codex_output "$output_file" "$((retry + 1))")
        [ -n "$archived_output" ] && log "📝 Saved codex output: $archived_output"

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
task_id = str(d.get('task_id', '')).strip()
summary = str(d.get('summary', '')).strip().lower()
if task_id == 'TASK-ID' or summary == 'one line summary':
    d['decision'] = 'fix'
    d['fix_instructions'] = d.get('fix_instructions') or 'Tech Lead returned placeholder/template JSON instead of a final review. Return one authoritative final JSON review only.'
    d.pop('alert_reason', None)
elif decision == 'done':
    d['decision'] = 'approve'
elif decision not in ('approve', 'fix', 'alert'):
    d['decision'] = 'fix'
    d['fix_instructions'] = d.get('fix_instructions') or 'Tech Lead returned invalid JSON. Retry: implement the task correctly and ensure tests pass.'
    d.pop('alert_reason', None)
print(json.dumps(d, ensure_ascii=False))
")
}

parse_lead_review_json() {
    local review_file_json=""
    local lead_output_json=""
    local review_file_decision=""
    local lead_output_decision=""
    REVIEW_JSON='{}'
    REVIEW_JSON_SOURCE="none"

    review_file_json=$(python3 "$RALPH_DIR/scripts/extract_json.py" < "$REVIEW_FILE" 2>/dev/null || true)
    lead_output_json=$(python3 "$RALPH_DIR/scripts/extract_json.py" < "$LEAD_OUTPUT" 2>/dev/null || true)

    if [ -n "$review_file_json" ] && [ "$review_file_json" != "{}" ]; then
        REVIEW_JSON="$review_file_json"
        REVIEW_JSON_SOURCE="review_file"
    fi

    if [ -n "$lead_output_json" ] && [ "$lead_output_json" != "{}" ]; then
        if [ "$REVIEW_JSON_SOURCE" = "review_file" ]; then
            review_file_decision=$(echo "$review_file_json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(str(d.get('decision', '')).strip())
except Exception:
    print('')
" 2>/dev/null || echo "")
            lead_output_decision=$(echo "$lead_output_json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(str(d.get('decision', '')).strip())
except Exception:
    print('')
" 2>/dev/null || echo "")
            if [ -n "$review_file_decision" ] && [ -n "$lead_output_decision" ] && [ "$review_file_decision" != "$lead_output_decision" ]; then
                REVIEW_JSON='{"decision":"fix","fix_instructions":"Tech Lead output was ambiguous: authoritative review file and stdout disagreed. Return one final JSON review only.","progress_note":"Trust layer fail-closed on review mismatch"}'
                REVIEW_JSON_SOURCE="mismatch_fail_closed"
                return
            fi
        elif [ "$REVIEW_JSON" = "{}" ]; then
            REVIEW_JSON="$lead_output_json"
            REVIEW_JSON_SOURCE="lead_output"
        fi
    fi

    if [ -z "$REVIEW_JSON" ] || [ "$REVIEW_JSON" = "{}" ]; then
        REVIEW_JSON='{"decision":"fix","fix_instructions":"Tech Lead output could not be parsed safely. Return one final JSON review only.","progress_note":"Trust layer fail-closed: unparseable review"}'
        REVIEW_JSON_SOURCE="unparsed_fail_closed"
    fi
}

collect_preclosure_changed_files_json() {
    python3 - "${REVIEW_BASE_HASH:-$PRE_HASH}" "${REVIEW_TARGET_HASH:-HEAD}" <<'PY'
import json
import subprocess
import sys

base_hash = sys.argv[1]
target_hash = sys.argv[2]
commands = [
    ["git", "diff", "--name-only", base_hash, target_hash],
    ["git", "diff", "--name-only", "--cached"],
    ["git", "diff", "--name-only"],
    ["git", "ls-files", "--others", "--exclude-standard"],
]
seen = set()
result = []
for cmd in commands:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        continue
    for line in proc.stdout.splitlines():
        path = line.strip()
        if not path or path in seen:
            continue
        seen.add(path)
        result.append(path)
print(json.dumps(result, ensure_ascii=False))
PY
}

collect_changed_paths() {
    python3 - <<'PY'
import subprocess

commands = [
    ["git", "diff", "--name-only", "--cached"],
    ["git", "diff", "--name-only"],
    ["git", "ls-files", "--others", "--exclude-standard"],
]
seen = set()
for cmd in commands:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        continue
    for line in proc.stdout.splitlines():
        path = line.strip()
        if not path or path in seen:
            continue
        seen.add(path)
        print(path)
PY
}

stage_changed_paths() {
    local changed_paths=""
    local path=""

    changed_paths=$(collect_changed_paths)
    [ -n "$changed_paths" ] || return 0

    while IFS= read -r path; do
        [ -n "$path" ] || continue
        if handoff_is_runtime_owned_path "$path"; then
            continue
        fi
        if [ -e "$path" ] && [ ! -r "$path" ]; then
            continue
        fi
        git add -A -- "$path"
    done <<< "$changed_paths"
}

task_scoped_diff_between_refs() {
    local base_hash="$1"
    local target_hash="$2"
    git diff "$base_hash" "$target_hash" -- \
        ':!ralph.sh' ':!ralph_state.json' ':!ralph_control.json' ':!ralph_alerts.log' \
        ':!ralph_main.pid' ':!ralph_codex.pid' ':!ralph_codex.pgid' \
        ':!tasks.json' ':!progress.md' ':!logs/**' ':!.ralph/audit/**' ':!.ralph/memory/recent.md' \
        2>/dev/null || true
}

task_scoped_cached_name_only_from_ref() {
    local base_hash="$1"
    git diff --cached --name-only "$base_hash" -- \
        ':!ralph.sh' ':!ralph_state.json' ':!ralph_control.json' ':!ralph_alerts.log' \
        ':!ralph_main.pid' ':!ralph_codex.pid' ':!ralph_codex.pgid' \
        ':!tasks.json' ':!progress.md' ':!logs/**' ':!.ralph/audit/**' ':!.ralph/memory/recent.md' \
        2>/dev/null || true
}

task_scoped_cached_diff_from_ref() {
    local base_hash="$1"
    git diff --cached "$base_hash" -- \
        ':!ralph.sh' ':!ralph_state.json' ':!ralph_control.json' ':!ralph_alerts.log' \
        ':!ralph_main.pid' ':!ralph_codex.pid' ':!ralph_codex.pgid' \
        ':!tasks.json' ':!progress.md' ':!logs/**' ':!.ralph/audit/**' ':!.ralph/memory/recent.md' \
        2>/dev/null || true
}

task_scoped_worktree_diff_from_ref() {
    local base_hash="$1"
    git diff "$base_hash" -- \
        ':!ralph.sh' ':!ralph_state.json' ':!ralph_control.json' ':!ralph_alerts.log' \
        ':!ralph_main.pid' ':!ralph_codex.pid' ':!ralph_codex.pgid' \
        ':!tasks.json' ':!progress.md' ':!logs/**' ':!.ralph/audit/**' ':!.ralph/memory/recent.md' \
        2>/dev/null || true
}

format_diff_summary() {
    python3 -c '
from __future__ import annotations

import re
import sys

text = sys.stdin.read()
if not text.strip():
    print("0 file(s)")
    raise SystemExit(0)

results = []
current_path = None
current_ranges = []

for line in text.splitlines():
    if line.startswith("+++ b/"):
        if current_path is not None:
            results.append((current_path, current_ranges))
        current_path = line[6:]
        current_ranges = []
        continue
    if current_path is None:
        continue
    match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
    if not match:
        continue
    start = int(match.group(1))
    length = int(match.group(2) or "1")
    end = start if length <= 1 else start + length - 1
    current_ranges.append(f"{start}" if start == end else f"{start}-{end}")

if current_path is not None:
    results.append((current_path, current_ranges))

if not results:
    print("0 file(s)")
    raise SystemExit(0)

print(f"{len(results)} file(s)")
for path, ranges in results[:8]:
    if ranges:
        joined = ", ".join(ranges[:6])
        print(f"- {path} (lines {joined})")
    else:
        print(f"- {path}")
remaining = len(results) - 8
if remaining > 0:
    print(f"- +{remaining} more file(s)")
'
}

summarize_diff_between_refs() {
    local base_hash="$1"
    local target_hash="$2"
    task_scoped_diff_between_refs "$base_hash" "$target_hash" | format_diff_summary
}

summarize_cached_diff_from_ref() {
    local base_hash="$1"
    task_scoped_cached_diff_from_ref "$base_hash" | format_diff_summary
}

resolve_git_ref() {
    local git_ref="$1"
    git rev-parse "$git_ref" 2>/dev/null || printf '%s\n' "$git_ref"
}

run_task_closure_verification() {
    PRE_CLOSURE_CHANGED_FILES_JSON=$(collect_preclosure_changed_files_json)
    VERIFICATION_JSON=$(printf '%s' "$TASK_JSON" | \
        RALPH_PROJECT_DIR="$PROJECT_DIR" \
        RALPH_CHANGED_FILES_JSON="$PRE_CLOSURE_CHANGED_FILES_JSON" \
        python3 "$RALPH_DIR/scripts/verify_task_closure.py" 2>/dev/null || echo '{"result":"needs_human_review","task_class":"implementation","reason":"Verification script failed unexpectedly.","changed_files":[],"changed_files_non_bookkeeping":[],"bookkeeping_only":false}')

    VERIFICATION_RESULT=$(echo "$VERIFICATION_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('result', 'needs_human_review'))
except Exception:
    print('needs_human_review')
" 2>/dev/null || echo "needs_human_review")
    VERIFICATION_CLASS=$(echo "$VERIFICATION_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('task_class', 'implementation'))
except Exception:
    print('implementation')
" 2>/dev/null || echo "implementation")
    VERIFICATION_REASON=$(echo "$VERIFICATION_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('reason', 'Verification failed'))
except Exception:
    print('Verification failed')
" 2>/dev/null || echo "Verification failed")
    VERIFICATION_NON_BOOKKEEPING=$(echo "$VERIFICATION_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(', '.join(d.get('changed_files_non_bookkeeping', [])))
except Exception:
    print('')
" 2>/dev/null || echo "")
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
    local prompt_profile_json=""
    local coder_prompt_profile_name="broad"
    local coder_prompt_targets=""
    local human_comment=""
    local coder_output=""
    local pre_hash=""
    local codex_exit=0
    local coder_prompt_tokens=0
    local coder_prompt_budget=0

    CODER_ROLE_FILE=$(resolve_agent_prompt_file "${TASK_ROLE:-coder}" "AGENTS_CODER.md")
    CODER_ROLE_CONTENT=$(read_file_for_prompt "$CODER_ROLE_FILE" "${RALPH_ROLE_MAX_CHARS:-8000}" || true)
    prompt_profile_json=$(coder_prompt_profile "$TASK_JSON" || echo '{"profile":"broad","targets":[]}')
    coder_prompt_profile_name=$(printf '%s' "$prompt_profile_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('profile', 'broad'))" 2>/dev/null || echo "broad")
    coder_prompt_targets=$(printf '%s' "$prompt_profile_json" | python3 -c "import json,sys; print('\n'.join(json.load(sys.stdin).get('targets', [])))" 2>/dev/null || echo "")
    coder_prompt_budget=$(get_coder_prompt_token_budget "$coder_prompt_profile_name")
    load_coder_prompt_project_context "$coder_prompt_profile_name"
    project_agents="$CODER_PROMPT_PROJECT_AGENTS"
    project_architecture="$CODER_PROMPT_PROJECT_ARCHITECTURE"
    project_memory_system="$CODER_PROMPT_PROJECT_MEMORY_SYSTEM"
    memory_core="$CODER_PROMPT_MEMORY_CORE"
    memory_recent="$CODER_PROMPT_MEMORY_RECENT"

    relevant_context=$(build_relevant_context "$TASK_JSON" "$coder_prompt_profile_name" || true)
    human_comment=$(get_human_comment)
    context_content=$(build_required_context_content "${TASK_CONTEXT_FILES:-}" "$coder_prompt_profile_name")
    local prompt_payload=""
    prompt_payload=$(build_coder_prompt_with_budget \
        "$TASK_JSON" \
        "$CODER_ROLE_FILE" \
        "$CODER_ROLE_CONTENT" \
        "$coder_prompt_profile_name" \
        "$coder_prompt_targets" \
        "$context_content" \
        "$relevant_context" \
        "$project_agents" \
        "$project_architecture" \
        "$project_memory_system" \
        "$memory_core" \
        "$memory_recent" \
        "" \
        "$human_comment" \
        "" \
        "$coder_prompt_budget" \
        "${RALPH_CODER_PROMPT_MAX_CHARS:-40000}")
    coder_prompt_tokens=$(printf '%s\n' "$prompt_payload" | sed -n '1s/^__TOKENS__://p')
    coder_prompt=$(printf '%s\n' "$prompt_payload" | sed '1d')
    log_coder_prompt_tokens "$coder_prompt_profile_name" "$coder_prompt_tokens" "$coder_prompt_budget"
    if ! check_prompt_budget "$coder_prompt" "$coder_prompt_budget" "Coder prompt" "$coder_prompt_tokens"; then
        write_state "blocked" "" "prompt_budget" "Coder prompt exceeded token budget"
        return 1
    fi
    coder_output="/tmp/ralph_coder_$$.txt"
    pre_hash=$(git rev-parse HEAD)

    set +e
    run_codex "$coder_prompt" "$coder_output" "" "${TASK_TIMEOUT:-180}" "${CODEX_MODEL:-}"
    codex_exit=$?
    set -e

    CODER_TOKENS=$(extract_tokens "$coder_output")
    TASK_TOKENS=$(( ${TASK_TOKENS:-0} + ${CODER_TOKENS:-0} ))
    SESSION_TOKENS=$(( ${SESSION_TOKENS:-0} + ${CODER_TOKENS:-0} ))

    if [ -n "$(git diff --name-only 2>/dev/null)" ] || [ -n "$(git diff --cached --name-only 2>/dev/null)" ]; then
        stage_changed_paths
        git commit -m "wip(${TASK_ID}): coder changes" 2>/dev/null || true
    fi

    PRE_HASH="$pre_hash"
    return $codex_exit
}

self_heal_environment() {
    local check_scope="${PRETASK_CHECK_SCOPE:-pre-task validation}"
    local heal_description="${PRETASK_HEAL_DESCRIPTION:-Before starting the task queue, pre-task validation is failing. Find the root cause and fix it without changing tasks.json or progress.md. Do NOT add new features.}"

    log "🩹 $check_scope broken before start. Attempting self-heal..."
    notify "🩹 $check_scope broken before start. Ralph will try to fix automatically."

    local HEAL_TASK_JSON
    HEAL_TASK_JSON=$(python3 - <<PY
import json

payload = {
  "id": "ENV-FIX",
  "phase": "R0",
  "title": "Fix broken pre-task validation",
  "description": """$heal_description""",
  "status": "pending",
  "priority": "critical",
  "complexity": "moderate",
  "timeout": 900,
  "required_context": [],
}
print(json.dumps(payload))
PY
)

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
    TASK_TITLE="Fix broken pre-task validation"
    TASK_TIMEOUT=900
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

    if run_pre_task_check /tmp/ralph_heal_verify.log; then
        log "✅ Self-heal succeeded! $check_scope is green. Continuing queue."
        notify '✅ Self-heal succeeded! Continuing task queue.'
        return 0
    else
        log "❌ Self-heal failed. $check_scope is still broken."
        notify "🚨 Self-heal failed. $check_scope is still broken. Manual fix needed."
        write_state "blocked" "" "self_heal_failed" "Self-heal failed: ${check_scope} still broken after ENV-FIX attempt"
        return 1
    fi
}

should_run_full_pre_task_suite() {
    [ "$MODE" = "auto" ] || [ "${RALPH_PRETASK_FULL_TEST:-0}" = "1" ]
}

run_fast_python_validation() {
    local log_file="$1"
    python3 - "$PROJECT_DIR" >"$log_file" 2>&1 <<'PY'
from __future__ import annotations

import ast
import importlib.util
import py_compile
import sys
from pathlib import Path

project_dir = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(project_dir / "scripts"))
sys.path.insert(0, str(project_dir / "src" / "ralph" / "resources" / "scripts"))
ignored_names = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".idea",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "logs",
    "node_modules",
    "site-packages",
    "venv",
}


def is_ignored(path: Path) -> bool:
    return any(part in ignored_names for part in path.relative_to(project_dir).parts)


def discover_python_files() -> list[Path]:
    return sorted(
        path for path in project_dir.rglob("*.py")
        if path.is_file() and not is_ignored(path)
    )


def package_parts_for(path: Path) -> list[str]:
    rel = path.relative_to(project_dir)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    package_parts = parts[:-1] if path.name != "__init__.py" else parts
    while package_parts:
        init_path = project_dir.joinpath(*package_parts, "__init__.py")
        if init_path.exists():
            return package_parts
        package_parts.pop(0)
    return []


def module_exists(module_name: str) -> bool:
    if not module_name:
        return False
    parts = module_name.split(".")
    module_path = project_dir.joinpath(*parts)
    return module_path.with_suffix(".py").exists() or (module_path / "__init__.py").exists()


def module_resolves(module_name: str) -> bool:
    if module_exists(module_name):
        return True
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def resolve_from_module(path: Path, node: ast.ImportFrom) -> str:
    current_package = package_parts_for(path)
    if node.level:
        if node.level > len(current_package) + 1:
            raise ValueError("relative import escapes package root")
        base_parts = current_package[: len(current_package) - node.level + 1]
    else:
        base_parts = []
    if node.module:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts)


errors: list[str] = []
python_files = discover_python_files()
for file_path in python_files:
    try:
        py_compile.compile(str(file_path), doraise=True)
    except py_compile.PyCompileError as exc:
        errors.append(f"syntax error in {file_path.relative_to(project_dir)}: {exc.msg}")
        continue

    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not module_resolves(alias.name):
                    errors.append(f"missing import '{alias.name}' in {file_path.relative_to(project_dir)}")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            try:
                module_name = resolve_from_module(file_path, node)
            except ValueError as exc:
                errors.append(f"invalid relative import in {file_path.relative_to(project_dir)}: {exc}")
                continue
            if module_name and not module_resolves(module_name):
                errors.append(f"missing import '{module_name}' in {file_path.relative_to(project_dir)}")

if errors:
    for entry in errors:
        print(entry)
    raise SystemExit(1)

print(f"validated {len(python_files)} Python files")
PY
}

run_pre_task_check() {
    local log_file="${1:-/tmp/ralph_test.log}"

    if should_run_full_pre_task_suite; then
        PRETASK_CHECK_SCOPE="make test"
        PRETASK_HEAL_DESCRIPTION="Before starting the task queue, make test is failing. Find the root cause and fix it so all tests pass. Do NOT change tasks.json or progress.md. Do NOT add new features."
        make test >"$log_file" 2>&1
    else
        PRETASK_CHECK_SCOPE="fast Python validation"
        PRETASK_HEAL_DESCRIPTION="Before starting the task queue, fast Python validation is failing. Fix Python syntax errors and unresolved imports without changing tasks.json or progress.md. Do NOT add new features."
        run_fast_python_validation "$log_file"
    fi
}

benchmark_select_simple_tasks() {
    python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path("tasks.json").read_text(encoding="utf-8"))
selected = [
    task["id"]
    for task in data.get("tasks", [])
    if task.get("status") == "pending" and task.get("complexity") == "simple"
][:3]
for task_id in selected:
    print(task_id)
PY
}

copy_repo_for_benchmark() {
    local destination="$1"
    mkdir -p "$destination"
    tar -cf - . | (cd "$destination" && tar -xf -)
}

run_manual_benchmark_for_task() {
    local task_id="$1"
    local output_file="$2"
    local task_json=""
    local task_context_files=""
    local task_complexity=""
    local model=""
    local coder_output=""
    local manual_start=""
    local manual_end=""
    local manual_duration=""
    local codex_status=0

    task_json=$(python3 "$RALPH_DIR/scripts/next_task.py" --task "$task_id" 2>/dev/null || echo "null")
    [ "$task_json" != "null" ] && [ -n "$task_json" ] || return 1

    TASK_JSON="$task_json"
    TASK_ID="$task_id"
    TASK_TITLE=$(extract_task_field "$task_json" "print(task.get('title', ''))" || echo "")
    task_context_files=$(extract_task_field "$task_json" "print(' '.join(task.get('required_context', []) or []))" || echo "")
    task_complexity=$(extract_task_field "$task_json" "print(task.get('complexity', 'moderate'))" || echo "moderate")
    model=""
    if [ "$task_complexity" = "simple" ]; then
        model="$MINI_MODEL"
    fi

    FIX_RETRY=0
    FIX_INSTRUCTIONS=""
    CODER_ROLE_FILE=$(resolve_agent_prompt_file "coder" "AGENTS_CODER.md")
    CODER_ROLE_CONTENT=$(read_file_for_prompt "$CODER_ROLE_FILE" "${RALPH_ROLE_MAX_CHARS:-8000}" || true)
    prepare_coder_prompt_for_task_json "$task_json" "$task_context_files"

    coder_output="/tmp/ralph_benchmark_manual_${task_id}_$$.txt"
    manual_start=$(python3 -c 'import time; print(f"{time.time():.6f}")')
    set +e
    if [ -n "$model" ]; then
        codex exec -s danger-full-access -m "$model" "$CODER_PROMPT" >"$coder_output" 2>&1
    else
        codex exec -s danger-full-access "$CODER_PROMPT" >"$coder_output" 2>&1
    fi
    codex_status=$?
    set -e
    manual_end=$(python3 -c 'import time; print(f"{time.time():.6f}")')
    manual_duration=$(python3 - "$manual_start" "$manual_end" <<'PY'
import sys
start = float(sys.argv[1])
end = float(sys.argv[2])
print(f"{end - start:.6f}")
PY
)
    log_phase_timing "$task_id" "1" "benchmark_manual" "coder" "$manual_duration"
    python3 - "$output_file" "$task_id" "$TASK_TITLE" "$manual_duration" "$CODER_PROMPT_TOKENS" "$codex_status" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
entry = {
    "task_id": sys.argv[2],
    "title": sys.argv[3],
    "coder_duration_s": float(sys.argv[4]),
    "prompt_tokens": int(sys.argv[5] or 0),
    "exit_code": int(sys.argv[6]),
}
with path.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
PY
    if [ "$codex_status" -eq 0 ]; then
        python3 - "$task_id" <<'PY'
import json
import sys
from pathlib import Path

task_id = sys.argv[1]
path = Path("tasks.json")
data = json.loads(path.read_text(encoding="utf-8"))
for task in data.get("tasks", []):
    if task.get("id") == task_id:
        task["status"] = "verified_done"
        break
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
    fi
    rm -f "$coder_output"
    return "$codex_status"
}

write_benchmark_report() {
    local auto_dir="$1"
    local manual_results_file="$2"
    local report_file="$3"
    local task_ids_csv="$4"
    local auto_total_wall="$5"
    local manual_total_wall="$6"

    python3 - "$auto_dir" "$manual_results_file" "$report_file" "$task_ids_csv" "$auto_total_wall" "$manual_total_wall" <<'PY'
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

auto_dir = Path(sys.argv[1])
manual_results_file = Path(sys.argv[2])
report_file = Path(sys.argv[3])
task_ids = [item for item in sys.argv[4].split(",") if item]
auto_total_wall = float(sys.argv[5])
manual_total_wall = float(sys.argv[6])


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


metrics_rows = [row for row in read_csv(auto_dir / "logs" / "metrics.csv") if row.get("task_id") in task_ids]
timing_rows = [
    row for row in read_csv(auto_dir / "logs" / "task_phase_timings.csv")
    if row.get("task_id") in task_ids and row.get("mode") == "auto"
]

phase_totals: dict[str, float] = defaultdict(float)
task_phase_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
for row in timing_rows:
    duration = float(row.get("duration_s") or 0.0)
    phase = row.get("phase") or "unknown"
    phase_totals[phase] += duration
    task_phase_totals[row.get("task_id") or ""][phase] += duration

auto_tasks = []
auto_total = 0.0
for row in metrics_rows:
    task_id = row["task_id"]
    task_total = float(row.get("duration_s") or 0.0)
    phases = task_phase_totals.get(task_id, {})
    known = sum(phases.values())
    auto_total += task_total
    auto_tasks.append(
        {
            "task_id": task_id,
            "status": row.get("status", ""),
            "duration_s": task_total,
            "attempts": int(row.get("attempts") or 0),
            "coder_duration_s": round(phases.get("coder", 0.0), 3),
            "test_duration_s": round(phases.get("test", 0.0), 3),
            "lead_duration_s": round(phases.get("lead", 0.0), 3),
            "other_duration_s": round(max(task_total - known, 0.0), 3),
        }
    )

manual_tasks = []
manual_total = 0.0
if manual_results_file.exists():
    for line in manual_results_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        manual_total += float(entry.get("coder_duration_s") or 0.0)
        manual_tasks.append(entry)

ratio = auto_total_wall / manual_total_wall if manual_total_wall > 0 else float("inf")
report = {
    "sample_size": len(task_ids),
    "task_ids": task_ids,
    "threshold_ratio": 5.0,
    "auto": {
        "total_duration_s": round(auto_total_wall, 3),
        "task_total_duration_s": round(auto_total, 3),
        "phase_totals_s": {
            "coder": round(phase_totals.get("coder", 0.0), 3),
            "test": round(phase_totals.get("test", 0.0), 3),
            "lead": round(phase_totals.get("lead", 0.0), 3),
            "other": round(max(auto_total_wall - sum(phase_totals.values()), 0.0), 3),
        },
        "tasks": auto_tasks,
    },
    "manual": {
        "total_duration_s": round(manual_total_wall, 3),
        "task_total_duration_s": round(manual_total, 3),
        "tasks": manual_tasks,
    },
    "comparison": {
        "auto_to_manual_ratio": round(ratio, 3),
        "assertion": "pass" if ratio < 5.0 else "fail",
    },
}

report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
if report["sample_size"] != 3:
    raise SystemExit("benchmark requires exactly 3 simple tasks")
if len(auto_tasks) != 3:
    raise SystemExit("auto benchmark did not complete 3 tasks")
if len(manual_tasks) != 3:
    raise SystemExit("manual benchmark did not execute 3 tasks")
if report["comparison"]["assertion"] != "pass":
    raise SystemExit(f"auto/manual ratio too high: {ratio:.3f}")
PY
}

run_auto_manual_benchmark() {
    local task_ids=""
    local task_ids_csv=""
    local benchmark_root=""
    local auto_dir=""
    local manual_dir=""
    local manual_results_file=""
    local report_file="$LOG_DIR/benchmark_auto_vs_manual.json"
    local auto_start=""
    local auto_end=""
    local auto_total_wall=""
    local manual_start=""
    local manual_end=""
    local manual_total_wall=""

    task_ids=$(benchmark_select_simple_tasks)
    if [ "$(printf '%s\n' "$task_ids" | sed '/^$/d' | wc -l | tr -d ' ')" != "3" ]; then
        echo "❌ Benchmark requires exactly 3 pending simple tasks in tasks.json"
        exit 1
    fi
    task_ids_csv=$(printf '%s\n' "$task_ids" | paste -sd ',' -)

    benchmark_root=$(mktemp -d "/tmp/ralph_benchmark_XXXXXX")
    auto_dir="$benchmark_root/auto"
    manual_dir="$benchmark_root/manual"
    manual_results_file="$manual_dir/logs/manual_benchmark.jsonl"
    mkdir -p "$auto_dir" "$manual_dir" "$manual_dir/logs"
    copy_repo_for_benchmark "$auto_dir"
    copy_repo_for_benchmark "$manual_dir"

    log "⏱️ Benchmark: running auto mode for tasks [$task_ids_csv]"
    auto_start=$(python3 -c 'import time; print(f"{time.time():.6f}")')
    (
        cd "$auto_dir"
        export RALPH_PROJECT_DIR="$auto_dir"
        "$RALPH_DIR/ralph.sh" auto
    )
    auto_end=$(python3 -c 'import time; print(f"{time.time():.6f}")')
    auto_total_wall=$(python3 - "$auto_start" "$auto_end" <<'PY'
import sys
start = float(sys.argv[1])
end = float(sys.argv[2])
print(f"{end - start:.6f}")
PY
)

    log "⏱️ Benchmark: running manual codex baseline for tasks [$task_ids_csv]"
    manual_start=$(python3 -c 'import time; print(f"{time.time():.6f}")')
    (
        cd "$manual_dir"
        export RALPH_PROJECT_DIR="$manual_dir"
        while IFS= read -r task_id; do
            [ -n "$task_id" ] || continue
            run_manual_benchmark_for_task "$task_id" "$manual_results_file"
        done <<EOF
$task_ids
EOF
    )
    manual_end=$(python3 -c 'import time; print(f"{time.time():.6f}")')
    manual_total_wall=$(python3 - "$manual_start" "$manual_end" <<'PY'
import sys
start = float(sys.argv[1])
end = float(sys.argv[2])
print(f"{end - start:.6f}")
PY
)

    write_benchmark_report "$auto_dir" "$manual_results_file" "$report_file" "$task_ids_csv" "$auto_total_wall" "$manual_total_wall"
    log "📊 Benchmark report written to $report_file"
    cat "$report_file"
}

# ─── Status ───
print_task_progress_report() {
    echo "=== Task Progress ==="
    python3 - <<'PY' 2>/dev/null || echo "task progress unavailable"
import json
from pathlib import Path

data = json.loads(Path("tasks.json").read_text(encoding="utf-8"))
tasks = data["tasks"]
done = sum(1 for task in tasks if task["status"] in {"done", "verified_done"})
total = len(tasks)
print(f"  Total: {done}/{total} tasks done")
for phase in sorted({str(task["phase"]) for task in tasks}):
    phase_tasks = [task for task in tasks if str(task["phase"]) == phase]
    phase_done = sum(1 for task in phase_tasks if task["status"] in {"done", "verified_done"})
    print(f"  Phase {phase}: {phase_done}/{len(phase_tasks)}")
print()
pending = [task for task in tasks if task["status"] == "pending"]
if pending:
    print("Next pending:")
    for task in pending[:5]:
        print(f"  {task['id']} [{task['priority']}] {task['title']}")
PY
}

print_status_report() {
    echo "=== Test Status ==="
    python3 -m pytest --tb=no -q 2>/dev/null | tail -1 || echo "tests not run"
    echo ""
    print_task_progress_report
}

print_final_report() {
    echo "=== Final State ==="
    echo "Status: $FINAL_STATE_STATUS"
    echo "Step: $FINAL_STATE_STEP"
    echo "Message: $FINAL_STATE_MESSAGE"
    echo ""
    print_task_progress_report
}

if [ "$MODE" = "status" ]; then
    print_status_report
    exit 0
fi

if [ "$MODE" = "audit" ]; then
    if [ -z "$TARGET" ]; then
        echo "Usage: ralph.sh audit <task_id>"
        exit 1
    fi
    python3 "$RALPH_DIR/scripts/audit_artifact.py" show "$TARGET"
    exit $?
fi

if [ "$MODE" = "audit-last" ]; then
    python3 "$RALPH_DIR/scripts/audit_artifact.py" list "${TARGET:-10}"
    exit $?
fi

if [ "$MODE" = "trust-report" ]; then
    python3 "$RALPH_DIR/scripts/audit_artifact.py" report
    exit $?
fi

if [ "$MODE" = "re-audit-last" ]; then
    python3 "$RALPH_DIR/scripts/re_audit_tasks.py" --last "${TARGET:-10}" ${EXTRA:+--apply}
    exit $?
fi

if [ "$MODE" = "benchmark" ]; then
    run_auto_manual_benchmark
    exit $?
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

if should_run_full_pre_task_suite; then
    log "🔍 Pre-task check: make test"
else
    log "🔍 Pre-task check: fast Python validation"
fi
if ! run_pre_task_check /tmp/ralph_test.log; then
    log "❌ Pre-task check failed!"
    tail -20 /tmp/ralph_test.log
    self_heal_environment || exit 1
fi
log "✅ Pre-task check passed"
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
        validate_requested_task
        ;;
    handoff)
        [ -z "$TARGET" ] && { echo "Usage: ralph.sh handoff <id>"; exit 1; }
        NEXT_ARGS="--task $TARGET"
        validate_requested_task
        ;;
    phase)
        [ -z "$TARGET" ] && { echo "Usage: ralph.sh phase <num>"; exit 1; }
        NEXT_ARGS="--phase $TARGET"
        ;;
    auto)
        NEXT_ARGS=""
        ;;
    *)
        echo "Usage: ralph.sh {task|handoff|phase|auto|benchmark|redo|status|audit|audit-last|trust-report|re-audit-last} [target]"
        exit 1
        ;;
esac

# ─── Main loop ───
while true; do
    CONTROL_STATUS=0
    REASON=""
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
    export TASK_JSON

    if [ "$TASK_JSON" = "null" ] || [ -z "$TASK_JSON" ]; then
        if [ "$MODE" = "phase" ] || [ "$MODE" = "auto" ]; then
            set_queue_exit_state
            log_deadlock_reason || true
            log "$QUEUE_EXIT_LOG"
        else
            log "🎉 No more pending tasks!"
        fi
        break
    fi

    TASK_ID=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    TASK_TITLE=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['title'])")
    # Extract coder timeout from task (complexity-aware defaults)
    TASK_TIMEOUT=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
complexity = task.get('complexity', 'moderate')
defaults = {'simple': 900, 'moderate': 900, 'complex': 900, 'critical': 900}
default_timeout = defaults.get(complexity, 900)
print(task.get('timeout', default_timeout))
" 2>/dev/null || echo "900")

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
    LEAD_ROLE_FILE=$(resolve_agent_prompt_file "lead" "AGENTS_LEAD.md")
    CODER_ROLE_CONTENT=$(read_file_for_prompt "$CODER_ROLE_FILE" "${RALPH_ROLE_MAX_CHARS:-8000}" || true)
    LEAD_ROLE_CONTENT=$(read_file_for_prompt "$LEAD_ROLE_FILE" "${RALPH_ROLE_MAX_CHARS:-8000}" || true)

    # Select model based on complexity
    CODEX_MODEL=""
    if [ "$TASK_COMPLEXITY" = "simple" ]; then
        CODEX_MODEL="$MINI_MODEL"
        log "🧠 Model: default (simple task)"
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
    TASK_START_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "HEAD")

    FIX_RETRY=0
    TASK_DONE=false
    TASK_SKIPPED=false
    TASK_BLOCKED=false
    TASK_ALERTED=false
    AUDIT_WRITTEN=false
    FIX_INSTRUCTIONS=""
    TASK_TOKENS=0
    DIFF_SNAPSHOT_FILE="/tmp/ralph_diff_${TASK_ID}.txt"
    DIFF_SUMMARY_FILE="/tmp/ralph_diff_summary_${TASK_ID}.txt"
    REVIEW_TARGET_FILE="/tmp/ralph_review_target_${TASK_ID}.txt"
    RETRY_FEEDBACK_FILE="/tmp/ralph_retry_feedback_${TASK_ID}.txt"
    RETRY_FEEDBACK_SOURCE_FILE="/tmp/ralph_retry_feedback_source_${TASK_ID}.txt"
    RETRY_TEST_OUTPUT_FILE="/tmp/ralph_retry_tests_${TASK_ID}.txt"
    rm -f "$DIFF_SNAPSHOT_FILE"
    rm -f "$DIFF_SUMMARY_FILE"
    rm -f "$REVIEW_TARGET_FILE"
    rm -f "$RETRY_FEEDBACK_FILE"
    rm -f "$RETRY_FEEDBACK_SOURCE_FILE"
    rm -f "$RETRY_TEST_OUTPUT_FILE"

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

        PRE_HASH=$(git rev-parse HEAD)
        REVIEW_BASE_HASH="${TASK_START_COMMIT:-$PRE_HASH}"
        REVIEW_TARGET_HASH="HEAD"
        CODER_OUTPUT="/tmp/ralph_coder_$$.txt"
        CODER_TOKENS=0
        CODER_DURATION=0
        CODEX_EXIT=0
        SKIP_CODER_STAGE=0

        if [ "$MODE" = "handoff" ] && [ "$FIX_RETRY" -eq 0 ]; then
            HANDOFF_WORKTREE_EVIDENCE=""
            HANDOFF_REPO_EVIDENCE=""
            HANDOFF_REPO_COMMIT=""
            HANDOFF_UNRELATED_CHANGES=""
            CURRENT_ATTEMPT=1
            log "═══════════════════════════════════════════"
            log "🪄 HANDOFF — Evaluating existing task-scoped candidate state"
            log "Task: ${TASK_ID} — ${TASK_TITLE}"
            log "═══════════════════════════════════════════"
            write_state "running" "$TASK_ID" "handoff" "Preparing validated worktree handoff..."
            notify "🪄 [HANDOFF] Starting: $TASK_ID — $TASK_TITLE"
            CODER_START=$(date +%s)

            HANDOFF_WORKTREE_EVIDENCE=$(handoff_worktree_evidence_paths "$TASK_JSON")
            if [ -n "$HANDOFF_WORKTREE_EVIDENCE" ]; then
                HANDOFF_UNRELATED_CHANGES=$(handoff_unrelated_worktree_tracked_changes "$TASK_JSON")
                if [ -n "$HANDOFF_UNRELATED_CHANGES" ]; then
                    REASON="Handoff requested with unrelated tracked changes outside the exact task scope: $(printf '%s' "$HANDOFF_UNRELATED_CHANGES" | paste -sd ', ' -)"
                    QUALITY="n/a"
                    TASK_DURATION=$(( $(date +%s) - TASK_START ))
                    log "$REASON"
                    log_metrics "failed" "false" "false"
                    RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "false" "false" "$TASK_DURATION"
                    AUDIT_WRITTEN=true
                    defer_blocked_task "$REASON"
                    break
                fi
                log "🪄 HANDOFF — Using existing task-scoped worktree evidence"
                handoff_stage_paths "$HANDOFF_WORKTREE_EVIDENCE"
                if [ -z "$(git diff --cached --name-only 2>/dev/null)" ]; then
                    REASON="Handoff requested but task-scoped worktree evidence could not be staged."
                    TASK_DURATION=$(( $(date +%s) - TASK_START ))
                    log "$REASON"
                    log_metrics "failed" "false" "false"
                    RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "false" "false" "$TASK_DURATION"
                    AUDIT_WRITTEN=true
                    defer_blocked_task "$REASON"
                    break
                fi
                git commit -m "wip($TASK_ID): handoff candidate" 2>/dev/null || true
                SKIP_CODER_STAGE=1
                REVIEW_TARGET_HASH=$(git rev-parse HEAD 2>/dev/null || echo "HEAD")
            else
                HANDOFF_REPO_COMMIT=$(handoff_latest_repo_candidate_commit "$TASK_JSON")
                if [ -n "$HANDOFF_REPO_COMMIT" ]; then
                    HANDOFF_UNRELATED_CHANGES=$(handoff_unrelated_worktree_tracked_changes "$TASK_JSON")
                    if [ -n "$HANDOFF_UNRELATED_CHANGES" ]; then
                        REASON="Handoff requested with unrelated tracked changes outside the exact task scope: $(printf '%s' "$HANDOFF_UNRELATED_CHANGES" | paste -sd ', ' -)"
                        QUALITY="n/a"
                        TASK_DURATION=$(( $(date +%s) - TASK_START ))
                        log "$REASON"
                        log_metrics "failed" "false" "false"
                        RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "false" "false" "$TASK_DURATION"
                        AUDIT_WRITTEN=true
                        defer_blocked_task "$REASON"
                        break
                    fi
                    PRE_HASH=$(handoff_commit_parent_hash "$HANDOFF_REPO_COMMIT")
                    REVIEW_BASE_HASH="$PRE_HASH"
                    REVIEW_TARGET_HASH="$HANDOFF_REPO_COMMIT"
                    log "🪄 HANDOFF — Using repo-backed candidate state from commit ${HANDOFF_REPO_COMMIT}"
                    SKIP_CODER_STAGE=1
                fi
            fi

            if [ "$SKIP_CODER_STAGE" -eq 0 ]; then
                REASON="Handoff requested but no task-scoped worktree evidence or exact-task repo-backed candidate evidence was found. Runtime-owned artifacts do not count."
                QUALITY="n/a"
                TASK_DURATION=$(( $(date +%s) - TASK_START ))
                log "$REASON"
                log_metrics "failed" "false" "false"
                RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "false" "false" "$TASK_DURATION"
                AUDIT_WRITTEN=true
                defer_blocked_task "$REASON"
                break
            fi
        fi

        if [ "$SKIP_CODER_STAGE" -eq 0 ]; then
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
            CODER_PROMPT_PROFILE_NAME="broad"
            CODER_PROMPT_TARGETS=""
            CODER_PROMPT_TOKENS=0
            CODER_PROMPT_BUDGET=0
            prepare_coder_prompt_for_task_json "$TASK_JSON" "$TASK_CONTEXT_FILES"
            log_coder_prompt_tokens "$CODER_PROMPT_PROFILE_NAME" "$CODER_PROMPT_TOKENS" "$CODER_PROMPT_BUDGET"
            if ! check_prompt_budget "$CODER_PROMPT" "$CODER_PROMPT_BUDGET" "Coder prompt" "$CODER_PROMPT_TOKENS"; then
                REASON="Coder prompt exceeded token budget"
                TASK_DURATION=$(( $(date +%s) - TASK_START ))
                write_state "blocked" "" "prompt_budget" "$REASON"
                log_metrics "failed" "false" "false"
                log "📋 TASK_FAIL task_id=$TASK_ID status=prompt_budget runtime_success=false verified_success=false reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "false" "false" "$TASK_DURATION"
                AUDIT_WRITTEN=true
                defer_blocked_task "$REASON"
                TASK_BLOCKED=true
                break
            fi

            set +e
            # run_codex handles retries/backoff for codex execution
            run_codex "$CODER_PROMPT" "$CODER_OUTPUT" "" "$TASK_TIMEOUT" "$CODEX_MODEL"
            CODEX_EXIT=$?
            set -e
            CONTROL_STATUS=0
            SESSION_TOKENS=$((SESSION_TOKENS + ${CODER_TOKENS:-0}))
            log "💰 [CODER] Tokens: $(format_tokens "$CODER_TOKENS") | Task total: $(format_tokens "$TASK_TOKENS") | Session total: $(format_tokens "$SESSION_TOKENS")"

            # Commit any unstaged changes the coder left behind
            if [ -n "$(git diff --name-only 2>/dev/null)" ] || [ -n "$(git diff --cached --name-only 2>/dev/null)" ]; then
                stage_changed_paths
                if [ -n "$(task_scoped_cached_name_only_from_ref "HEAD")" ]; then
                    git commit -m "wip($TASK_ID): coder changes" 2>/dev/null || true
                    REVIEW_TARGET_HASH=$(git rev-parse HEAD 2>/dev/null || echo "HEAD")
                else
                    git reset >/dev/null 2>&1 || true
                fi
            fi
        fi

        ASSET_STATUS=0
        wait_for_required_assets || ASSET_STATUS=$?
        if [ $ASSET_STATUS -eq 10 ]; then
            log "⏹ Stop signal received"
            write_state "stopped" "" "" "Stopped by user"
            notify "⏹ Ralph stopped by user"
            cleanup
            exit 0
        elif [ $ASSET_STATUS -eq 11 ]; then
            skip_current_task
            TASK_DONE=true
            TASK_SKIPPED=true
            break
        elif [ $ASSET_STATUS -ne 0 ]; then
            TASK_DURATION=$(( $(date +%s) - TASK_START ))
            REASON="Invalid assets_manifest.json"
            log_metrics "failed" "false" "false"
            RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "false" "false" "$TASK_DURATION"
            AUDIT_WRITTEN=true
            defer_blocked_task "$REASON"
            break
        fi

        CODER_DURATION=$(( $(date +%s) - CODER_START ))
        log "⏱️ Coder took ${CODER_DURATION}s"
        log_phase_timing "$TASK_ID" "$CURRENT_ATTEMPT" "$MODE" "coder" "$CODER_DURATION"

        POST_HASH=$(git rev-parse HEAD)
        EFFECTIVE_REVIEW_BASE_HASH=$(resolve_git_ref "${REVIEW_BASE_HASH:-$PRE_HASH}")
        EFFECTIVE_REVIEW_TARGET_HASH=$(resolve_git_ref "${REVIEW_TARGET_HASH:-$POST_HASH}")
        PRIOR_ATTEMPT_DIFF=""
        if [ "$FIX_RETRY" -gt 0 ] && [ -f "$DIFF_SNAPSHOT_FILE" ]; then
            PRIOR_ATTEMPT_DIFF=$(cat "$DIFF_SNAPSHOT_FILE" 2>/dev/null || true)
        fi
        if [ "$EFFECTIVE_REVIEW_BASE_HASH" = "$EFFECTIVE_REVIEW_TARGET_HASH" ] && [ -n "$(task_scoped_cached_name_only_from_ref "$EFFECTIVE_REVIEW_BASE_HASH")" ]; then
            CURRENT_DIFF=$(task_scoped_cached_diff_from_ref "$EFFECTIVE_REVIEW_BASE_HASH")
            CURRENT_DIFF_SUMMARY=$(summarize_cached_diff_from_ref "$EFFECTIVE_REVIEW_BASE_HASH")
        else
            CURRENT_DIFF=$(task_scoped_diff_between_refs "$EFFECTIVE_REVIEW_BASE_HASH" "$EFFECTIVE_REVIEW_TARGET_HASH")
            CURRENT_DIFF_SUMMARY=$(summarize_diff_between_refs "$EFFECTIVE_REVIEW_BASE_HASH" "$EFFECTIVE_REVIEW_TARGET_HASH")
        fi
        if [ "$FIX_RETRY" -gt 0 ] && [ -f "$DIFF_SNAPSHOT_FILE" ] && { [ -z "$CURRENT_DIFF" ] || [ "$PRIOR_ATTEMPT_DIFF" = "$CURRENT_DIFF" ]; }; then
            REASON="Retry produced identical diff to prior attempt"
            TASK_DURATION=$(( $(date +%s) - TASK_START ))
            log "⚠️ Retry diff matched the prior attempt; blocking before attempt $((CURRENT_ATTEMPT + 1))"
            write_state "blocked" "" "idempotent_retry" "$REASON"
            log_metrics "failed" "true" "false"
            log "📋 TASK_FAIL task_id=$TASK_ID status=idempotent_retry runtime_success=true verified_success=false reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
            RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "true" "false" "$TASK_DURATION"
            AUDIT_WRITTEN=true
            defer_blocked_task "$REASON"
            TASK_BLOCKED=true
            break
        fi
        printf '%s' "$CURRENT_DIFF" > "$DIFF_SNAPSHOT_FILE"
        printf '%s' "$CURRENT_DIFF_SUMMARY" > "$DIFF_SUMMARY_FILE"
        if [ -n "${REVIEW_TARGET_HASH:-}" ] && [ "$EFFECTIVE_REVIEW_BASE_HASH" != "$EFFECTIVE_REVIEW_TARGET_HASH" ]; then
            printf '%s' "$EFFECTIVE_REVIEW_TARGET_HASH" > "$REVIEW_TARGET_FILE"
        else
            rm -f "$REVIEW_TARGET_FILE"
        fi
        DIFF_SNAPSHOT_BYTES=$(wc -c < "$DIFF_SNAPSHOT_FILE" 2>/dev/null | tr -d ' ' || echo "0")
        DIFF_SNAPSHOT_BYTES="${DIFF_SNAPSHOT_BYTES:-0}"
        if [ "${REVIEW_BASE_HASH:-$PRE_HASH}" = "${REVIEW_TARGET_HASH:-$POST_HASH}" ]; then
            GIT_DIFF="(no changes committed)"
        else
            GIT_DIFF=$(git diff "${REVIEW_BASE_HASH:-$PRE_HASH}" "${REVIEW_TARGET_HASH:-HEAD}" -- ':!ralph.sh' ':!ralph_state.json' ':!ralph_control.json' ':!ralph_alerts.log' 2>/dev/null | head -500 || echo "diff error")
        fi
        TEST_START=$(date +%s)
        TEST_OUTPUT=$(make test 2>&1 | tail -40 || echo "tests failed")
        TEST_DURATION=$(( $(date +%s) - TEST_START ))
        log "⏱️ Test gate took ${TEST_DURATION}s"
        log_phase_timing "$TASK_ID" "$CURRENT_ATTEMPT" "$MODE" "test" "$TEST_DURATION"
        RETRY_TEST_OUTPUT=$(summarize_retry_test_output "$TEST_OUTPUT")
        if [ -n "$RETRY_TEST_OUTPUT" ]; then
            printf '%s' "$RETRY_TEST_OUTPUT" > "$RETRY_TEST_OUTPUT_FILE"
        else
            rm -f "$RETRY_TEST_OUTPUT_FILE"
        fi

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

Previous diff snapshot: ${DIFF_SNAPSHOT_BYTES:-0} bytes

## Tests
\`\`\`
$TEST_OUTPUT
\`\`\`

Return exactly one final review block in this format:
BEGIN_RALPH_REVIEW_JSON
{...valid final review JSON...}
END_RALPH_REVIEW_JSON

Do not output example JSON.
Do not output multiple JSON objects.
If the task is not fully complete, return decision=fix.
Do not ask the coder to update tasks.json, progress.md, final commits, final status, audit artifacts, or to produce a non-empty diff as a goal by itself."

            set +e
            # run_codex handles retries/backoff for codex execution
            run_codex "$LEAD_PROMPT" "$LEAD_OUTPUT" "$REVIEW_FILE" "$TASK_LEAD_TIMEOUT" "$CODEX_MODEL"
            CODEX_EXIT=$?
            set -e
            mkdir -p .ralph/audit
            printf '%s' "$LEAD_PROMPT" > ".ralph/audit/lead_prompt_${TASK_ID}.txt"
            cp "$LEAD_OUTPUT" ".ralph/audit/lead_reasoning_${TASK_ID}.txt"
            log "📋 Lead review artifacts saved to .ralph/audit/"
            LEAD_TOKENS=$(extract_tokens "$LEAD_OUTPUT")
            TASK_TOKENS=$((TASK_TOKENS + ${LEAD_TOKENS:-0}))
            SESSION_TOKENS=$((SESSION_TOKENS + ${LEAD_TOKENS:-0}))
            log "💰 [LEAD]  Tokens: $(format_tokens "$LEAD_TOKENS") | Task total: $(format_tokens "$TASK_TOKENS") | Session total: $(format_tokens "$SESSION_TOKENS")"
            LEAD_DURATION=$(( $(date +%s) - LEAD_START ))
            log "⏱️ Tech Lead took ${LEAD_DURATION}s"
            log_phase_timing "$TASK_ID" "$CURRENT_ATTEMPT" "$MODE" "lead" "$LEAD_DURATION"
            REVIEW=$(cat "$REVIEW_FILE" 2>/dev/null || echo '{"decision":"alert","alert_reason":"No output"}')
            parse_lead_review_json
            validate_lead_review_json
            log "🔍 DEBUG: Review first 200 chars: $(echo "$REVIEW" | head -c 200)"
            log "🔍 DEBUG: Parsed review JSON: $(echo "$REVIEW_JSON" | head -c 200)"
            log "🔍 DEBUG: Parsed review source: ${REVIEW_JSON_SOURCE:-unknown}"
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
                run_task_closure_verification
                log "🧪 Verification: ${VERIFICATION_RESULT:-unknown} (${VERIFICATION_CLASS:-implementation})"
                log "🧪 Verification reason: ${VERIFICATION_REASON:-none}"
                if [ -n "${VERIFICATION_NON_BOOKKEEPING:-}" ]; then
                    log "🧪 Evidence files: ${VERIFICATION_NON_BOOKKEEPING}"
                fi

                if [ "${VERIFICATION_RESULT:-needs_human_review}" = "fail_fix" ]; then
                    FIX_INSTRUCTIONS="$VERIFICATION_REASON"
                    printf '%s' "$FIX_INSTRUCTIONS" > "$RETRY_FEEDBACK_FILE"
                    printf '%s' "verification" > "$RETRY_FEEDBACK_SOURCE_FILE"
                    FIX_RETRY=$((FIX_RETRY+1))
                    notify "🔧 $TASK_ID verification blocked closure ($FIX_RETRY/$MAX_FIX_RETRIES)"
                    log "🔧 Fix $FIX_RETRY/$MAX_FIX_RETRIES: $FIX_INSTRUCTIONS"
                elif [ "${VERIFICATION_RESULT:-needs_human_review}" = "needs_human_review" ]; then
                    REASON="$VERIFICATION_REASON"
                    TASK_DURATION=$(( $(date +%s) - TASK_START ))
                    log_metrics "failed" "true" "false"
                    log "📋 TASK_FAIL task_id=$TASK_ID status=verification runtime_success=true verified_success=false reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                    RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "true" "false" "$TASK_DURATION"
                    AUDIT_WRITTEN=true
                    if [ "${TASK_RISK:-medium}" = "high" ]; then
                        alert_human "$REASON"
                        TASK_ALERTED=true
                        TASK_DONE=true
                    else
                        defer_blocked_task "$REASON"
                    fi
                else
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

                    python3 "$RALPH_DIR/scripts/update_task.py" "$TASK_ID" verified_done
                    python3 "$RALPH_DIR/scripts/update_progress.py" "$TASK_ID" "$PROGRESS_NOTE"
                    # Update memory with task summary
                    CHANGED_FILES=$(git diff --name-only "${REVIEW_BASE_HASH:-$PRE_HASH}" "${REVIEW_TARGET_HASH:-HEAD}" 2>/dev/null | tr '\n' ', ' | sed 's/,$//')
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
                    persist_task_success_state
                    stage_changed_paths
                    git commit -m "feat($TASK_ID): $TASK_TITLE [ralph]" 2>/dev/null || true
                    log_metrics "success" "true" "true"
                    log "✅ $TASK_ID done"
                    TASK_DURATION=$(( $(date +%s) - TASK_START ))
                    TOTAL="$TASK_DURATION"
                    write_task_audit_artifact "done" "true" "true" "$TASK_DURATION"
                    AUDIT_WRITTEN=true
                    log "📋 TASK_DONE task_id=$TASK_ID status=approved runtime_success=true verified_success=true quality=$QUALITY duration=${TOTAL}s attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
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
                fi
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

                sanitize_fix_instructions "$FIX_INSTRUCTIONS"
                if [ "${FIX_SANITIZE_MODE:-unchanged}" = "contradictory_only" ]; then
                    REASON="${FIX_SANITIZE_REASON:-Contradictory Tech Lead fix: runtime-owned demands only.}"
                    TASK_DURATION=$(( $(date +%s) - TASK_START ))
                    log "🛑 Contradictory Tech Lead fix blocked retry: $REASON"
                    log_metrics "failed" "true" "false"
                    log "📋 TASK_FAIL task_id=$TASK_ID status=contradictory_fix runtime_success=true verified_success=false reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                    RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "true" "false" "$TASK_DURATION"
                    AUDIT_WRITTEN=true
                    if [ "${TASK_RISK:-medium}" = "high" ]; then
                        alert_human "$REASON"
                        TASK_ALERTED=true
                        TASK_DONE=true
                    else
                        defer_blocked_task "$REASON"
                    fi
                    break
                fi
                if [ "${FIX_SANITIZE_MODE:-unchanged}" = "sanitized" ]; then
                    FIX_INSTRUCTIONS="$FIX_SANITIZED_TEXT"
                    log "🧹 Sanitized Tech Lead fix instructions: removed runtime-owned bookkeeping/diff demands"
                fi

                printf '%s' "$FIX_INSTRUCTIONS" > "$RETRY_FEEDBACK_FILE"
                printf '%s' "lead" > "$RETRY_FEEDBACK_SOURCE_FILE"
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

                TASK_DURATION=$(( $(date +%s) - TASK_START ))
                log_metrics "failed" "true" "false"
                log "📋 TASK_FAIL task_id=$TASK_ID status=alert runtime_success=true verified_success=false reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "blocked" "true" "false" "$TASK_DURATION"
                AUDIT_WRITTEN=true
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
        is_single_task_mode && break
        continue
    fi

    if [ "$TASK_BLOCKED" = true ]; then
        if [ "$AUDIT_WRITTEN" = false ]; then
            TASK_DURATION=$(( $(date +%s) - TASK_START ))
            RALPH_AUDIT_REASON="${REASON:-Task blocked}" write_task_audit_artifact "blocked" "false" "false" "$TASK_DURATION"
            AUDIT_WRITTEN=true
        fi
        is_single_task_mode && break
        continue
    fi

    if [ "$TASK_ALERTED" = true ]; then
        break
    fi

    if [ "$TASK_DONE" = false ]; then
        REASON="$TASK_ID failed after $MAX_FIX_RETRIES retries"
        TASK_DURATION=$(( $(date +%s) - TASK_START ))
        FINAL_RUNTIME_SUCCESS="false"
        FINAL_AUDIT_STATUS="failed"
        if [ -n "${VERIFICATION_JSON:-}" ] && [ "${VERIFICATION_JSON:-}" != "{}" ]; then
            FINAL_RUNTIME_SUCCESS="true"
            FINAL_AUDIT_STATUS="blocked"
        fi
        log_metrics "failed" "$FINAL_RUNTIME_SUCCESS" "false"
        log "📋 TASK_FAIL task_id=$TASK_ID status=alert runtime_success=$FINAL_RUNTIME_SUCCESS verified_success=false reason=\"$REASON\" attempts=$FIX_RETRY timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        RALPH_AUDIT_REASON="$REASON" write_task_audit_artifact "$FINAL_AUDIT_STATUS" "$FINAL_RUNTIME_SUCCESS" "false" "$TASK_DURATION"
        AUDIT_WRITTEN=true
        if [ "${TASK_RISK:-medium}" = "high" ]; then
            alert_human "$REASON"
            break
        else
            defer_blocked_task "$REASON"
            is_single_task_mode && break
            continue
        fi
    fi

    is_single_task_mode && break

    if [ "$MODE" = "phase" ]; then
        REMAINING=$(python3 "$RALPH_DIR/scripts/next_task.py" --phase "$TARGET" 2>/dev/null || echo "null")
        if [ "$REMAINING" = "null" ]; then
            set_queue_exit_state
            log_deadlock_reason || true
            log "$QUEUE_EXIT_LOG"
            break
        fi
    fi
    log "DEBUG: Finished task $TASK_ID, continuing to next..."
    # Circuit breaker check
    if [ $CONSECUTIVE_FAILURES -ge $MAX_CONSECUTIVE_FAILURES ]; then
        log "🔴 CIRCUIT BREAKER: $CONSECUTIVE_FAILURES consecutive failures!"
        notify "🔴 CIRCUIT BREAKER: $CONSECUTIVE_FAILURES consecutive failures. Ralph stopped."
        alert_human "$CONSECUTIVE_FAILURES consecutive failures triggered the circuit breaker"
        write_state "circuit_breaker" "" "" "$CONSECUTIVE_FAILURES consecutive failures"
        break
    fi
    continue
done

write_state "$FINAL_STATE_STATUS" "" "$FINAL_STATE_STEP" "$FINAL_STATE_MESSAGE"
notify "$FINAL_NOTIFY_MESSAGE"
log "════════════════════════════════════════════════════"
log "💰 SESSION TOTAL: ${SESSION_TASKS} tasks, ~$(format_tokens "$SESSION_TOKENS") tokens (~\$$(estimate_cost "$SESSION_TOKENS"))"
log "════════════════════════════════════════════════════"
log "📊 Final:"
print_final_report
exit "$FINAL_EXIT_CODE"
