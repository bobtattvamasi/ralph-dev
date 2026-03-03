#!/usr/bin/env bash
set -euo pipefail

# Ralph Init — setup ralph in a new project
# Usage: .ralph/ralph-init.sh [project-name]

RALPH_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(pwd)"
PROJECT_NAME="${1:-$(basename "$PROJECT_DIR")}"

echo "🤖 Ralph Init"
echo "   Project: $PROJECT_NAME"
echo "   Dir:     $PROJECT_DIR"
echo "   Ralph:   $RALPH_DIR"
echo ""

# Copy templates if not exist
copy_if_missing() {
    local src="$1" dst="$2"
    if [ -f "$dst" ]; then
        echo "   ⏭  $dst already exists, skipping"
    else
        cp "$src" "$dst"
        echo "   ✅ Created $dst"
    fi
}

copy_if_missing "$RALPH_DIR/templates/AGENTS.md.template" "$PROJECT_DIR/AGENTS.md"
copy_if_missing "$RALPH_DIR/templates/AGENTS_CODER.md" "$PROJECT_DIR/AGENTS_CODER.md"
copy_if_missing "$RALPH_DIR/templates/AGENTS_LEAD.md" "$PROJECT_DIR/AGENTS_LEAD.md"
copy_if_missing "$RALPH_DIR/templates/progress.md.template" "$PROJECT_DIR/progress.md"

# Memory templates (.ralph/memory)
mkdir -p "$PROJECT_DIR/.ralph/memory"
for tpl in "$RALPH_DIR"/templates/memory/*.template; do
    [ -f "$tpl" ] || continue
    base="$(basename "$tpl" .template)"
    copy_if_missing "$tpl" "$PROJECT_DIR/.ralph/memory/$base"
done

# tasks.json with project name
if [ -f "$PROJECT_DIR/tasks.json" ]; then
    echo "   ⏭  tasks.json already exists, skipping"
else
    sed "s/PROJECT_NAME/$PROJECT_NAME/g" "$RALPH_DIR/templates/tasks.json.template" > "$PROJECT_DIR/tasks.json"
    echo "   ✅ Created tasks.json (project: $PROJECT_NAME)"
fi

# .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
    if [ -f "$RALPH_DIR/.env.example" ]; then
        cp "$RALPH_DIR/.env.example" "$PROJECT_DIR/.env"
        echo "   ✅ Created .env (edit with your tokens)"
    else
        echo "   ⚠️  .env.example not found in ralph-dev, skipping .env"
    fi
fi

# Add to .gitignore
GITIGNORE="$PROJECT_DIR/.gitignore"
touch "$GITIGNORE"
for entry in ".ralph/" "ralph_state.json" "ralph_control.json" "ralph_alerts.log" "logs/"; do
    grep -qxF "$entry" "$GITIGNORE" 2>/dev/null || echo "$entry" >> "$GITIGNORE"
done
echo "   ✅ Updated .gitignore"

echo ""
echo "🎉 Done! Next steps:"
echo "   1. Edit AGENTS.md — describe YOUR project"
echo "   2. Edit .env — add Telegram tokens"
echo "   3. Add tasks to tasks.json"
echo "   4. Run: $RALPH_DIR/ralph.sh task YOUR-TASK-01"
echo "   5. Or:  python3 $RALPH_DIR/scripts/ralph_bot.py"
