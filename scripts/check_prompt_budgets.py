from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RALPH_SH = REPO_ROOT / "ralph.sh"


def copy_repo_text_file(relative_path: str, project_dir: Path) -> None:
    source = REPO_ROOT / relative_path
    target = project_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o644)


def create_test_project(root: Path) -> Path:
    project_dir = root / "project"
    (project_dir / "logs").mkdir(parents=True)
    (project_dir / ".ralph" / "memory").mkdir(parents=True)
    (project_dir / "src").mkdir()
    (project_dir / "scripts").mkdir()

    tasks = {
        "version": 1,
        "project": "prompt-budget-validation",
        "phases": {"OPS": {"name": "Ops", "description": "Prompt budget validation"}},
        "tasks": [],
    }
    (project_dir / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    (project_dir / "progress.md").write_text("# Progress\n", encoding="utf-8")
    (project_dir / "src" / "prompt_builder.ts").write_text(
        "export function buildKeywordPrompt() {\n"
        "  return 'context injection keyword matching prompt builder " + ("alpha " * 120) + "';\n"
        "}\n",
        encoding="utf-8",
    )
    (project_dir / "scripts" / "narrow_target.py").write_text("TARGET = False\n", encoding="utf-8")

    for relative_path in (
        "AGENTS.md",
        "ARCHITECTURE.md",
        "MEMORY_SYSTEM.md",
        "AGENTS_CODER.md",
        "AGENTS_LEAD.md",
        ".ralph/memory/core.md",
        ".ralph/memory/recent.md",
    ):
        copy_repo_text_file(relative_path, project_dir)

    return project_dir


def write_task(project_dir: Path, task: dict) -> None:
    payload = {
        "version": 1,
        "project": "prompt-budget-validation",
        "phases": {"OPS": {"name": "Ops", "description": "Prompt budget validation"}},
        "tasks": [task],
    }
    (project_dir / "tasks.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_prompt_runner_script() -> Path:
    shell_lines = RALPH_SH.read_text(encoding="utf-8").splitlines()
    try:
        cutoff = next(index for index, line in enumerate(shell_lines) if line.startswith('case "$MODE" in'))
    except StopIteration as exc:
        raise RuntimeError("cannot find main entrypoint in ralph.sh") from exc

    runner_body = "\n".join(shell_lines[:cutoff]) + "\n" + """
TASK_ID="${1:-T01}"
TASK_ROLE="coder"
TASK_JSON=$(python3 - "$TASK_ID" <<'PY'
import json
import sys
task_id = sys.argv[1]
data = json.load(open("tasks.json", encoding="utf-8"))
for task in data["tasks"]:
    if task["id"] == task_id:
        print(json.dumps(task))
        break
else:
    raise SystemExit(f"task not found: {task_id}")
PY
)
TASK_CONTEXT_FILES=$(echo "$TASK_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
files = task.get('required_context', [])
print(' '.join(files) if files else '')
" 2>/dev/null || echo "")
CODER_ROLE_FILE=$(resolve_agent_prompt_file "${TASK_ROLE:-coder}" "AGENTS_CODER.md")
CODER_ROLE_CONTENT=$(read_file_for_prompt "$CODER_ROLE_FILE" "${RALPH_ROLE_MAX_CHARS:-8000}" || true)
PROMPT_PROFILE_JSON=$(coder_prompt_profile "$TASK_JSON" || echo '{"profile":"broad","targets":[]}')
CODER_PROMPT_PROFILE_NAME=$(printf '%s' "$PROMPT_PROFILE_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('profile', 'broad'))" 2>/dev/null || echo "broad")
CODER_PROMPT_TARGETS=$(printf '%s' "$PROMPT_PROFILE_JSON" | python3 -c "import json,sys; print('\\n'.join(json.load(sys.stdin).get('targets', [])))" 2>/dev/null || echo "")
CODER_PROMPT_BUDGET=$(get_coder_prompt_token_budget "$CODER_PROMPT_PROFILE_NAME")
load_coder_prompt_project_context "$CODER_PROMPT_PROFILE_NAME"
RELEVANT_CONTEXT=$(build_relevant_context "$TASK_JSON" "$CODER_PROMPT_PROFILE_NAME" || true)
CONTEXT_CONTENT=$(build_required_context_content "${TASK_CONTEXT_FILES:-}" "$CODER_PROMPT_PROFILE_NAME")
PROMPT_PAYLOAD=$(build_coder_prompt_with_budget \
    "$TASK_JSON" \
    "$CODER_ROLE_FILE" \
    "$CODER_ROLE_CONTENT" \
    "$CODER_PROMPT_PROFILE_NAME" \
    "$CODER_PROMPT_TARGETS" \
    "$CONTEXT_CONTENT" \
    "$RELEVANT_CONTEXT" \
    "$CODER_PROMPT_PROJECT_AGENTS" \
    "$CODER_PROMPT_PROJECT_ARCHITECTURE" \
    "$CODER_PROMPT_PROJECT_MEMORY_SYSTEM" \
    "$CODER_PROMPT_MEMORY_CORE" \
    "$CODER_PROMPT_MEMORY_RECENT" \
    "" \
    "" \
    "" \
    "0" \
    "" \
    "$CODER_PROMPT_BUDGET" \
    "${RALPH_CODER_PROMPT_MAX_CHARS:-40000}")
printf '%s' "$PROMPT_PAYLOAD"
"""

    runner_path = REPO_ROOT / ".tmp_prompt_budget_runner.sh"
    runner_path.write_text(runner_body, encoding="utf-8")
    runner_path.chmod(0o755)
    return runner_path


def run_case(runner_path: Path, tmp_root: Path, profile: str) -> tuple[int, int]:
    project_dir = create_test_project(tmp_root / profile)

    if profile == "narrow":
        task = {
            "id": "T01",
            "phase": "OPS",
            "title": "Simple exact-task script update",
            "description": "Update scripts/narrow_target.py with the smallest exact-task change.",
            "status": "pending",
            "complexity": "simple",
            "category": "optimization",
            "priority": "high",
            "acceptance_criteria": [
                "scripts/narrow_target.py is updated",
                "Simple exact-task path stays narrow by default",
            ],
        }
        expected_limit = 15000
    else:
        task = {
            "id": "T01",
            "phase": "OPS",
            "title": "Simple exact-task script update requiring architecture context",
            "description": "Update scripts/narrow_target.py but read ARCHITECTURE.md first.",
            "status": "pending",
            "complexity": "simple",
            "category": "optimization",
            "priority": "high",
            "required_context": ["ARCHITECTURE.md"],
            "acceptance_criteria": [
                "scripts/narrow_target.py is updated",
                "ARCHITECTURE.md is included because the task explicitly requires project-wide docs",
            ],
        }
        expected_limit = 25000

    write_task(project_dir, task)

    result = subprocess.run(
        [str(runner_path), "T01"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{profile} prompt validation failed:\n{result.stdout}\n{result.stderr}")

    lines = result.stdout.splitlines()
    token_index = next((index for index, line in enumerate(lines) if line.startswith("__TOKENS__:")), -1)
    if token_index < 0:
        raise RuntimeError(f"{profile} prompt payload is missing token header")

    measured_tokens = int(lines[token_index].split(":", 1)[1])
    prompt_text = "\n".join(lines[token_index + 1 :])
    prompt_tokens = len(prompt_text.split())
    if prompt_tokens != measured_tokens:
        raise RuntimeError(
            f"{profile} prompt token mismatch: header={measured_tokens} measured={prompt_tokens}"
        )
    if prompt_tokens >= expected_limit:
        raise RuntimeError(f"{profile} prompt is too large: {prompt_tokens} tokens >= {expected_limit}")

    return prompt_tokens, expected_limit


def main() -> int:
    runner_path = build_prompt_runner_script()
    try:
        with tempfile.TemporaryDirectory(prefix="ralph-prompt-budget-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            narrow_tokens, narrow_limit = run_case(runner_path, tmp_root, "narrow")
            broad_tokens, broad_limit = run_case(runner_path, tmp_root, "broad")
    finally:
        runner_path.unlink(missing_ok=True)

    print(f"narrow: {narrow_tokens} tokens (<{narrow_limit})")
    print(f"broad: {broad_tokens} tokens (<{broad_limit})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
