#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SESSION_NOTES_FILE="$PROJECT_DIR/SESSION_NOTES.md"

cd "$PROJECT_DIR"

PROMPT_FILE=""
RESPONSE_FILE=""
OUTPUT_FILE=""
TASK_SCOPE_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE" "$RESPONSE_FILE" "$OUTPUT_FILE" "$TASK_SCOPE_FILE"' EXIT

python3 - "$PROJECT_DIR" > "$TASK_SCOPE_FILE" <<'PY' || {
import json
import sys
from pathlib import Path

project_dir = Path(sys.argv[1])
state_path = project_dir / "ralph_state.json"
tasks_path = project_dir / "tasks.json"

try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"Cannot read current task from {state_path.name}: {exc}", file=sys.stderr)
    raise SystemExit(1)

current_task = str(state.get("current_task") or "").strip()
if not current_task:
    print("Cannot determine current task for scoped auto-commit.", file=sys.stderr)
    raise SystemExit(1)

try:
    tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"Cannot read task scope from {tasks_path.name}: {exc}", file=sys.stderr)
    raise SystemExit(1)

task = next((item for item in tasks_data.get("tasks", []) if str(item.get("id", "")).strip() == current_task), None)
if not isinstance(task, dict):
    print(f"Current task not found in tasks.json: {current_task}", file=sys.stderr)
    raise SystemExit(1)

target_files = task.get("target_files") or []
if not isinstance(target_files, list) or not any(str(path).strip() for path in target_files):
    print(f"No target_files defined for current task: {current_task}", file=sys.stderr)
    raise SystemExit(1)

for path in target_files:
    value = str(path).strip()
    if value:
        print(value)

for extra in (f".ralph/audit/{current_task}.json", "audit_report.md"):
    print(extra)
PY
    exit 1
}

is_path_in_scope() {
    local candidate="${1:-}"
    [ -n "$candidate" ] || return 1

    while IFS= read -r scope_path; do
        [ -n "$scope_path" ] || continue
        if [ "$candidate" = "$scope_path" ]; then
            return 0
        fi
    done < "$TASK_SCOPE_FILE"

    return 1
}

ensure_only_scoped_paths() {
    local label="${1:-changes}"
    local path=""

    while IFS= read -r path; do
        [ -n "$path" ] || continue
        if ! is_path_in_scope "$path"; then
            echo "Refusing auto-commit: unrelated $label detected: $path" >&2
            echo "Only current task files may be committed." >&2
            exit 1
        fi
    done
}

ensure_only_scoped_paths "staged change" < <(git diff --cached --name-only)
ensure_only_scoped_paths "tracked change" < <(git diff --name-only)
while IFS= read -r untracked_path; do
    [ -n "$untracked_path" ] || continue
    if ! is_path_in_scope "$untracked_path"; then
        echo "Refusing auto-commit: unrelated untracked file detected: $untracked_path" >&2
        echo "Only current task files may be committed." >&2
        exit 1
    fi
done < <(git ls-files --others --exclude-standard)

while IFS= read -r scope_path; do
    [ -n "$scope_path" ] || continue
    if [ -e "$scope_path" ] || git ls-files --error-unmatch -- "$scope_path" >/dev/null 2>&1; then
        git add -- "$scope_path"
    fi
done < "$TASK_SCOPE_FILE"

echo "Staging files:"
git diff --cached --name-only | sed 's/^/ - /'

if git diff --cached --quiet; then
    echo "No staged changes to document."
    exit 1
fi

DIFF_CONTENT="$(git diff --cached)"
PROMPT_FILE="$(mktemp)"
RESPONSE_FILE="$(mktemp)"
OUTPUT_FILE="$(mktemp)"

cat > "$PROMPT_FILE" <<EOF
Проанализируй этот diff. Напиши короткое summary изменений для человека. Затем сгенерируй commit message в формате Conventional Commits.

Верни ТОЛЬКО JSON-объект такого вида:
{"decision":"approve","summary":"...","commit_message":"type(scope): short message"}

Требования:
- decision: всегда "approve"
- summary: 2-4 коротких пункта или 1 короткий абзац, понятный человеку
- commit_message: одна строка в формате Conventional Commits
- без markdown
- без пояснений вне JSON

Diff:
$DIFF_CONTENT
EOF

set +e
codex exec -s danger-full-access -o "$RESPONSE_FILE" "$(cat "$PROMPT_FILE")" > "$OUTPUT_FILE" 2>&1
CODEX_EXIT=$?
set -e

if [ $CODEX_EXIT -ne 0 ]; then
    echo "codex exec failed"
    cat "$OUTPUT_FILE"
    exit $CODEX_EXIT
fi

PARSED_JSON="$(python3 "$PROJECT_DIR/scripts/extract_json.py" < "$RESPONSE_FILE" 2>/dev/null)" || {
    echo "Failed to parse codex response"
    cat "$RESPONSE_FILE"
    exit 1
}

SUMMARY="$(python3 -c "import json,sys; value=json.loads(sys.argv[1]).get('summary', ''); text=str(value).strip(); sys.exit(1) if not text else None; print(text)" "$PARSED_JSON" 2>/dev/null)" || {
    echo "Parsed response is missing summary"
    cat "$RESPONSE_FILE"
    exit 1
}

COMMIT_MESSAGE="$(python3 -c "import json,sys; value=json.loads(sys.argv[1]).get('commit_message', ''); text=str(value).strip(); sys.exit(1) if not text else None; print(text)" "$PARSED_JSON" 2>/dev/null)" || {
    echo "Parsed response is missing commit_message"
    cat "$RESPONSE_FILE"
    exit 1
}

TIMESTAMP="$(date -u '+%Y-%m-%d %H:%M UTC')"
{
    echo ""
    echo "### $TIMESTAMP"
    echo "$SUMMARY"
} >> "$SESSION_NOTES_FILE"

git add "$SESSION_NOTES_FILE"
GIT_EDITOR=true git commit -m "$COMMIT_MESSAGE"

echo "Summary appended to SESSION_NOTES.md"
echo "Committed: $COMMIT_MESSAGE"
