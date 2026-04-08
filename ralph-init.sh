#!/usr/bin/env bash
set -euo pipefail

# Ralph Init — setup ralph in a new project
# Usage: .ralph/ralph-init.sh [project-name]

RALPH_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(pwd)"
PROJECT_NAME="${1:-$(basename "$PROJECT_DIR")}"
REGISTRY_DIR="${HOME}/.ralph"
REGISTRY_FILE="$REGISTRY_DIR/projects.json"
DEFAULT_PROJECT_NAME="ralph-dev"
DEFAULT_TEST_CMD="make test"
PROJECT_REGISTRY_NAME="$(basename "$PROJECT_DIR")"

auto_register_project() {
    mkdir -p "$REGISTRY_DIR"
    python3 - "$REGISTRY_FILE" "$PROJECT_DIR" "$RALPH_DIR" "$PROJECT_REGISTRY_NAME" "$DEFAULT_TEST_CMD" "$PROJECT_DIR/.ralph/project.json" <<'PY'
from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
from pathlib import Path

registry_path = Path(sys.argv[1]).expanduser()
lock_path = registry_path.with_suffix(".lock")
project_dir = Path(sys.argv[2]).expanduser().resolve()
ralph_dir = Path(sys.argv[3]).expanduser().resolve()
project_name = sys.argv[4]
default_test_cmd = sys.argv[5]
project_config_path = Path(sys.argv[6]).expanduser().resolve()
default_project_name = "ralph-dev"


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def load_project_test_cmd() -> str:
    if not project_config_path.exists():
        return default_test_cmd
    try:
        payload = json.loads(project_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_test_cmd
    if not isinstance(payload, dict):
        return default_test_cmd
    value = payload.get("test_cmd", default_test_cmd)
    if not isinstance(value, str) or not value.strip():
        return default_test_cmd
    return value.strip()


def default_project_entry() -> dict[str, str]:
    return {"path": str(ralph_dir), "test_cmd": default_test_cmd}


def load_registry() -> dict[str, object]:
    if not registry_path.exists():
        return {
            "version": 1,
            "active_project": default_project_name,
            "projects": {default_project_name: default_project_entry()},
        }

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registry must contain a JSON object.")

    projects = data.get("projects")
    if not isinstance(projects, dict):
        raise ValueError("Registry must contain a top-level 'projects' object.")

    data.setdefault("version", 1)
    data.setdefault("active_project", default_project_name)
    if default_project_name not in projects:
        projects[default_project_name] = default_project_entry()
    if data.get("active_project") not in projects:
        data["active_project"] = default_project_name
    return data


def next_available_name(projects: dict[str, object], base_name: str) -> str:
    if base_name not in projects:
        return base_name
    suffix = 2
    while f"{base_name}-{suffix}" in projects:
        suffix += 1
    return f"{base_name}-{suffix}"


lock_path.parent.mkdir(parents=True, exist_ok=True)
with lock_path.open("a+", encoding="utf-8") as lock_handle:
    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

    registry_exists = registry_path.exists()
    registry = load_registry()
    projects = registry["projects"]
    project_path = str(project_dir)
    project_test_cmd = load_project_test_cmd()

    for existing_name, payload in projects.items():
        if not isinstance(existing_name, str) or not isinstance(payload, dict):
            continue
        raw_path = payload.get("path")
        if not isinstance(raw_path, str):
            continue
        try:
            if Path(raw_path).expanduser().resolve() == project_dir:
                payload["path"] = project_path
                payload["test_cmd"] = project_test_cmd
                atomic_write_json(registry_path, registry)
                raise SystemExit(0)
        except OSError:
            continue

    resolved_name = next_available_name(projects, project_name)
    projects[resolved_name] = {"path": project_path, "test_cmd": project_test_cmd}
    if not registry_exists:
        registry["active_project"] = resolved_name
    atomic_write_json(registry_path, registry)
PY
}

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

render_template_if_missing() {
    local src="$1" dst="$2"
    if [ -f "$dst" ]; then
        echo "   ⏭  $dst already exists, skipping"
    else
        sed "s/{{PROJECT_NAME}}/$PROJECT_NAME/g; s/PROJECT_NAME/$PROJECT_NAME/g" "$src" > "$dst"
        echo "   ✅ Created $dst"
    fi
}

render_template_if_missing "$RALPH_DIR/templates/AGENTS.md.template" "$PROJECT_DIR/AGENTS.md"
render_template_if_missing "$RALPH_DIR/templates/ARCHITECTURE.md.template" "$PROJECT_DIR/ARCHITECTURE.md"
render_template_if_missing "$RALPH_DIR/templates/MEMORY_SYSTEM.md.template" "$PROJECT_DIR/MEMORY_SYSTEM.md"
copy_if_missing "$RALPH_DIR/templates/AGENTS_CODER.md" "$PROJECT_DIR/AGENTS_CODER.md"
copy_if_missing "$RALPH_DIR/templates/AGENTS_DESIGNER.md" "$PROJECT_DIR/AGENTS_DESIGNER.md"
copy_if_missing "$RALPH_DIR/templates/AGENTS_JOURNALIST.md" "$PROJECT_DIR/AGENTS_JOURNALIST.md"
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

auto_register_project

echo ""
echo "🎉 Done! Next steps:"
echo "   1. Edit AGENTS.md, ARCHITECTURE.md, and MEMORY_SYSTEM.md"
echo "   2. Edit .env — add Telegram tokens"
echo "   3. Add tasks to tasks.json"
echo "   4. Run: $RALPH_DIR/ralph.sh task YOUR-TASK-01"
echo "   5. Or:  python3 $RALPH_DIR/scripts/ralph_bot.py"
