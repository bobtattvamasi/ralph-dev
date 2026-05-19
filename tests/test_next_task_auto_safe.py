from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.test_integration import REPO_ROOT
from tests.test_ralph_shell_helpers import build_shell_fixture, run_helper


NEXT_TASK = REPO_ROOT / "scripts" / "next_task.py"


def write_task_file(project_dir: Path, tasks: list[dict]) -> None:
    (project_dir / "tasks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project": "next-task-auto-safe-tests",
                "tasks": tasks,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_next_task(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(NEXT_TASK), *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_next_task_auto_safe_skips_unsafe_and_selects_safe(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_task_file(
        project_dir,
        [
            {
                "id": "R17-01",
                "phase": "R17",
                "status": "pending",
                "title": "ralph kickoff CLI command",
                "description": "Add new ralph.sh mode kickoff and pass description into generation steps.",
                "target_files": ["ralph.sh", "src/ralph/resources/ralph.sh"],
                "acceptance_criteria": ["Add focused test coverage for kickoff path"],
                "priority": "high",
                "complexity": "moderate",
            },
            {
                "id": "T02",
                "phase": "R20",
                "status": "pending",
                "title": "Safe runtime fix",
                "description": "Tighten one shell helper",
                "target_files": ["ralph.sh", "tests/test_ralph_shell_helpers.py"],
                "acceptance_criteria": ["Tighten one shell helper with a narrow scoped change."],
                "priority": "high",
                "complexity": "simple",
            },
        ],
    )

    result = run_next_task(project_dir, "--auto-safe")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["id"] == "T02"
    assert result.stderr.splitlines() == [
        "TASK_SKIPPED_UNSAFE R17-01 BOOTSTRAP_FEATURE",
    ]


def test_next_task_auto_safe_returns_null_when_only_unsafe_pending_and_explicit_task_still_works(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    unsafe_task = {
        "id": "R17-01",
        "phase": "R17",
        "status": "pending",
        "title": "ralph kickoff CLI command",
        "description": "Bootstrap kickoff flow for generation",
        "target_files": ["ralph.sh"],
        "acceptance_criteria": ["Add focused test coverage for kickoff path"],
        "priority": "high",
        "complexity": "moderate",
    }
    write_task_file(project_dir, [unsafe_task])

    auto_safe = run_next_task(project_dir, "--auto-safe")
    explicit = run_next_task(project_dir, "--auto-safe", "--task", "R17-01")

    assert auto_safe.returncode == 0, auto_safe.stdout + auto_safe.stderr
    assert auto_safe.stdout.strip() == "null"
    assert auto_safe.stderr.splitlines() == [
        "TASK_SKIPPED_UNSAFE R17-01 BOOTSTRAP_FEATURE",
    ]
    assert explicit.returncode == 0, explicit.stdout + explicit.stderr
    assert json.loads(explicit.stdout)["id"] == "R17-01"


def test_next_task_auto_safe_respects_depends_on_blocked_dependency(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_task_file(
        project_dir,
        [
            {
                "id": "R22-01",
                "phase": "R22",
                "status": "blocked",
                "title": "state_service.py",
                "description": "Blocked prerequisite",
                "target_files": ["scripts/state_service.py"],
                "acceptance_criteria": ["State service works"],
                "priority": "high",
                "complexity": "moderate",
            },
            {
                "id": "R22-04",
                "phase": "R22",
                "status": "pending",
                "title": "Qdrant memory",
                "description": "Semantic retrieval task that depends on state service",
                "target_files": ["scripts/memory_service.py", "ralph.sh", "tests/test_memory_service.py"],
                "acceptance_criteria": ["Memory service behavior is covered"],
                "priority": "medium",
                "complexity": "moderate",
                "depends_on": ["R22-01"],
            },
        ],
    )

    auto_safe = run_next_task(project_dir, "--auto-safe")
    explain = run_next_task(project_dir, "--auto-safe", "--explain")

    assert auto_safe.returncode == 0, auto_safe.stdout + auto_safe.stderr
    assert auto_safe.stdout.strip() == "null"
    explained = json.loads(explain.stdout)
    assert explained["reason"] == "blocked_dependencies"
    assert explained["blocked_pending"] == [
        {
            "id": "R22-04",
            "title": "Qdrant memory",
            "unmet_dependencies": ["R22-01"],
        }
    ]


def test_run_next_task_helper_supports_auto_safe_selection_and_skip_logging(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "scripts" / "next_task.py").write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "if '--auto-safe' in sys.argv:\n"
        "    print('TASK_SKIPPED_UNSAFE T01 BOOTSTRAP_FEATURE', file=sys.stderr)\n"
        "    print(json.dumps({'id': 'T02', 'title': 'Safe task', 'status': 'pending'}))\n"
        "else:\n"
        "    print(json.dumps({'id': 'T01', 'title': 'Unsafe task', 'status': 'pending'}))\n",
        encoding="utf-8",
    )

    result = run_helper(
        project_dir,
        "TASK_JSON=$(run_next_task_helper --auto-safe)\n"
        "printf 'TASK_JSON=%s\\n' \"$TASK_JSON\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "TASK_SKIPPED_UNSAFE T01 BOOTSTRAP_FEATURE" in combined
    payload_line = next(line for line in result.stdout.splitlines() if line.startswith("TASK_JSON="))
    payload = json.loads(payload_line[len("TASK_JSON="):])
    assert payload["id"] == "T02"
