from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RALPH_SH = REPO_ROOT / "ralph.sh"


def wait_until(predicate, timeout: float = 10.0, interval: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def make_fake_binaries(bin_dir: Path) -> None:
    write_executable(
        bin_dir / "codex",
        """#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
review_file = None
i = 0
while i < len(args):
    if args[i] in {"-s", "-m"}:
        i += 2
    elif args[i] == "-o":
        review_file = args[i + 1]
        i += 2
    else:
        i += 1

sleep_s = float(os.environ.get("MOCK_CODEX_SLEEP", "0"))
if review_file:
    payload = {
        "decision": "approve",
        "quality_score": 8,
        "progress_note": "Integration test approve",
    }
    Path(review_file).write_text(json.dumps(payload), encoding="utf-8")
else:
    if sleep_s > 0:
        time.sleep(sleep_s)

print("tokens used")
print("123")
""",
    )
    write_executable(
        bin_dir / "gtimeout",
        """#!/usr/bin/env bash
set -euo pipefail
while [ $# -gt 0 ]; do
    case "$1" in
        --foreground)
            shift
            ;;
        --kill-after=*)
            shift
            ;;
        ''|*[!0-9]*)
            break
            ;;
        *)
            shift
            break
            ;;
    esac
done
exec "$@"
""",
    )


def init_git_repo(project_dir: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test User",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test User",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True, text=True, env=env)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "chore: init test project"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def create_test_project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "logs").mkdir()
    (project_dir / ".ralph" / "memory").mkdir(parents=True)

    tasks = {
        "version": 1,
        "project": "integration-test",
        "phases": {"R1": {"name": "Reliability", "description": "Integration tests"}},
        "tasks": [
            {
                "id": "T01",
                "phase": "R1",
                "title": "Integration test task",
                "description": "Exercise ralph.sh integration flow",
                "status": "pending",
                "priority": "high",
                "dependencies": [],
                "timeout": 5,
            }
        ],
    }
    (project_dir / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    (project_dir / "progress.md").write_text("# Progress\n", encoding="utf-8")
    (project_dir / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (project_dir / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
    (project_dir / "MEMORY_SYSTEM.md").write_text("# Memory\n", encoding="utf-8")
    (project_dir / "AGENTS_CODER.md").write_text("# Coder\n", encoding="utf-8")
    (project_dir / "AGENTS_LEAD.md").write_text("# Lead\n", encoding="utf-8")
    (project_dir / ".ralph" / "memory" / "core.md").write_text("# Core\n", encoding="utf-8")
    (project_dir / ".ralph" / "memory" / "recent.md").write_text("# Recent\n", encoding="utf-8")
    (project_dir / "Makefile").write_text(".PHONY: test\n\ntest:\n\t@true\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make_fake_binaries(bin_dir)

    init_git_repo(project_dir)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PYTHONUNBUFFERED"] = "1"
    env["RALPH_PROJECT_DIR"] = str(project_dir)
    return project_dir, env


def load_task_status(project_dir: Path, task_id: str = "T01") -> str:
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    for task in data["tasks"]:
        if task["id"] == task_id:
            return task["status"]
    raise AssertionError(f"Task {task_id} not found")


def load_state(project_dir: Path) -> dict:
    return json.loads((project_dir / "ralph_state.json").read_text(encoding="utf-8"))


def test_ralph_marks_task_done_on_success(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)

    result = subprocess.run(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert load_task_status(project_dir) == "done"


def test_ralph_marks_task_skipped_on_skip_control(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    env["MOCK_CODEX_SLEEP"] = "1.5"

    process = subprocess.Popen(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    state_file = project_dir / "ralph_state.json"
    assert wait_until(
        lambda: state_file.exists() and load_state(project_dir).get("current_phase_step") == "coder",
        timeout=10,
    )

    (project_dir / "ralph_control.json").write_text(
        json.dumps({"action": "skip", "comment": "T01"}, indent=2),
        encoding="utf-8",
    )

    stdout, _ = process.communicate(timeout=20)
    assert process.returncode == 0, stdout
    assert load_task_status(project_dir) == "skipped"


def test_ralph_stops_when_stop_control_is_present(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    (project_dir / "ralph_control.json").write_text(
        json.dumps({"action": "stop", "comment": ""}, indent=2),
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(RALPH_SH), "auto"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    state = load_state(project_dir)
    assert state["status"] == "stopped"
    assert load_task_status(project_dir) == "pending"
