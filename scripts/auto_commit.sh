#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SESSION_NOTES_FILE="$PROJECT_DIR/SESSION_NOTES.md"

cd "$PROJECT_DIR"

git add -A

if git diff --cached --quiet; then
    echo "No staged changes to document."
    exit 1
fi

DIFF_CONTENT="$(git diff --cached)"
PROMPT_FILE="$(mktemp)"
RESPONSE_FILE="$(mktemp)"
OUTPUT_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE" "$RESPONSE_FILE" "$OUTPUT_FILE"' EXIT

cat > "$PROMPT_FILE" <<EOF
Проанализируй этот diff. Напиши короткое summary изменений для человека. Затем сгенерируй commit message в формате Conventional Commits.

Верни ТОЛЬКО JSON-объект такого вида:
{"summary":"...","commit_message":"type(scope): short message"}

Требования:
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

PARSED_JSON="$(python3 -c "
import json, re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace').strip()
try:
    data = json.loads(text)
except Exception:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise SystemExit(1)
    data = json.loads(match.group(0))
summary = str(data.get('summary', '')).strip()
commit_message = str(data.get('commit_message', '')).strip()
if not summary or not commit_message:
    raise SystemExit(1)
print(json.dumps({'summary': summary, 'commit_message': commit_message}, ensure_ascii=False))
" "$RESPONSE_FILE" 2>/dev/null)" || {
    echo "Failed to parse codex response"
    cat "$RESPONSE_FILE"
    exit 1
}

SUMMARY="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['summary'])" "$PARSED_JSON")"
COMMIT_MESSAGE="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['commit_message'])" "$PARSED_JSON")"

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
