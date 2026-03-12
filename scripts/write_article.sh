#!/usr/bin/env bash
set -euo pipefail

RALPH_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_DIR="$(pwd)"

if [ ! -f "$PROJECT_DIR/BLOG_DRAFTS.md" ]; then
    touch "$PROJECT_DIR/BLOG_DRAFTS.md"
fi

SESSION_TAIL=""
PROGRESS_TAIL=""
if [ -f "$PROJECT_DIR/SESSION_NOTES.md" ]; then
    SESSION_TAIL="$(tail -n 50 "$PROJECT_DIR/SESSION_NOTES.md" 2>/dev/null || true)"
fi
if [ -f "$PROJECT_DIR/progress.md" ]; then
    PROGRESS_TAIL="$(tail -n 50 "$PROJECT_DIR/progress.md" 2>/dev/null || true)"
fi

JOURNALIST_INSTRUCTIONS="$(cat "$RALPH_DIR/templates/AGENTS_JOURNALIST.md")"
RECENT_COMMITS="$(git log -n 5 --stat --oneline 2>/dev/null || git log -n 5 --oneline 2>/dev/null || true)"

PROMPT="$(cat <<EOF
Read and follow these instructions:

$JOURNALIST_INSTRUCTIONS

Context to analyze:

## Latest Commits
$RECENT_COMMITS

## SESSION_NOTES.md (last 50 lines)
${SESSION_TAIL:-No SESSION_NOTES.md found.}

## progress.md (last 50 lines)
${PROGRESS_TAIL:-No progress.md found.}

Output the final article pack in markdown with these sections:
## Telegram
## LinkedIn
## Cover Prompts
EOF
)"

ARTICLE_TEXT="$(codex exec "$PROMPT")"

{
    printf "\n## %s\n\n" "$(date -u +%Y-%m-%d %H:%M UTC)"
    printf "%s\n" "$ARTICLE_TEXT"
} >> "$PROJECT_DIR/BLOG_DRAFTS.md"

echo "✅ Article generated in BLOG_DRAFTS.md"
