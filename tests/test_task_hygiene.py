from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check_task_hygiene.py"


def make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    return project_dir


def write_tasks(project_dir: Path, tasks: list[dict]) -> None:
    (project_dir / "tasks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project": "task-hygiene-tests",
                "tasks": tasks,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_checker(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def test_checker_reports_r17_01_like_unsafe_task(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    write_tasks(
        project_dir,
        [
            {
                "id": "R17-01",
                "phase": "R17",
                "status": "pending",
                "title": "ralph kickoff CLI command",
                "description": "Add new ralph.sh mode 'kickoff <path> <description>' that creates the target directory, runs ralph-init.sh there, and passes the description into AI generation steps.",
                "target_files": ["ralph.sh", "src/ralph/resources/ralph.sh"],
                "acceptance_criteria": [
                    "ralph.sh kickoff path creates a directory with .ralph scaffold",
                    "Add focused test coverage for kickoff path",
                ],
                "priority": "high",
                "complexity": "moderate",
            }
        ],
    )

    result = run_checker(project_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines == [
        "TASK_HYGIENE_WARN R17-01 BOOTSTRAP_FEATURE bootstrap/kickoff/init/generation style task is risky for unattended auto",
        "TASK_HYGIENE_WARN R17-01 MISSING_TEST_TARGET acceptance implies test coverage but target_files has no tests/ path",
    ]


def test_checker_fail_on_warn_and_stable_warning_order(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    write_tasks(
        project_dir,
        [
            {
                "id": "T01",
                "status": "pending",
                "title": "New command generator",
                "description": "Bootstrap a new CLI mode with scaffold generation",
                "target_files": ["scripts/thing.py"],
                "acceptance_criteria": ["Tests cover the new command path"],
                "revision_notes": "T01 failed after 2 retries",
                "complexity": "complex",
                "scope_too_wide": True,
                "selection_warnings": ["scope-too-wide"],
            }
        ],
    )

    result = run_checker(project_dir, "--fail-on-warn")

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "TASK_HYGIENE_WARN T01 BOOTSTRAP_FEATURE bootstrap/kickoff/init/generation style task is risky for unattended auto",
        "TASK_HYGIENE_WARN T01 MISSING_TEST_TARGET acceptance implies test coverage but target_files has no tests/ path",
        "TASK_HYGIENE_WARN T01 PREVIOUS_RETRY_FAILURE revision_notes mention previous retry failure",
        "TASK_HYGIENE_WARN T01 COMPLEX_TASK complex task is risky for unattended auto",
        "TASK_HYGIENE_WARN T01 BROAD_SCOPE task is already marked scope_too_wide",
    ]


def test_checker_supports_task_id_and_include_non_pending(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    write_tasks(
        project_dir,
        [
            {
                "id": "T01",
                "status": "done",
                "title": "kickoff command",
                "description": "new command",
                "target_files": ["ralph.sh"],
                "acceptance_criteria": ["Tests cover kickoff"],
            },
            {
                "id": "T02",
                "status": "pending",
                "title": "Safe narrow fix",
                "description": "Adjust one helper",
                "target_files": ["scripts/helper.py", "tests/test_helper.py"],
                "acceptance_criteria": ["Adjust one helper with narrow task scope."],
            },
        ],
    )

    default_result = run_checker(project_dir, "--task-id", "T01")
    include_result = run_checker(project_dir, "--task-id", "T01", "--include-non-pending")

    assert default_result.returncode == 0
    assert default_result.stdout == ""
    assert include_result.returncode == 0
    assert include_result.stdout.splitlines() == [
        "TASK_HYGIENE_WARN T01 BOOTSTRAP_FEATURE bootstrap/kickoff/init/generation style task is risky for unattended auto",
        "TASK_HYGIENE_WARN T01 MISSING_TEST_TARGET acceptance implies test coverage but target_files has no tests/ path",
    ]


def test_checker_reports_missing_test_target_for_implicit_behavioral_verification(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    write_tasks(
        project_dir,
        [
            {
                "id": "R20-05",
                "status": "pending",
                "title": "Safe auto-commit — scope to task files only",
                "description": "Replace git add -A with scoped staging.",
                "target_files": ["scripts/auto_commit.sh"],
                "acceptance_criteria": [
                    "Create dirty worktree with unrelated files. Run auto-commit. Must refuse to commit unrelated changes."
                ],
                "priority": "high",
                "complexity": "moderate",
            }
        ],
    )

    result = run_checker(project_dir, "--task-id", "R20-05")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "TASK_HYGIENE_WARN R20-05 MISSING_TEST_TARGET acceptance implies test coverage but target_files has no tests/ path",
    ]


def test_checker_reports_external_service_and_memory_system_change_for_r22_04_like_task(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    write_tasks(
        project_dir,
        [
            {
                "id": "R22-04",
                "status": "pending",
                "title": "Qdrant memory — semantic retrieval instead of recent.md",
                "description": "Replace .ralph/memory/recent.md with Qdrant local instance through a memory service.",
                "target_files": ["scripts/memory_service.py", "ralph.sh", "tests/test_memory_service.py"],
                "acceptance_criteria": [
                    "Qdrant starts locally through Docker or embedded mode.",
                    "Semantic retrieval returns top-5 similar tasks.",
                    "Fallback to recent.md if the external service is unavailable.",
                ],
                "priority": "medium",
                "complexity": "moderate",
            }
        ],
    )

    result = run_checker(project_dir, "--task-id", "R22-04")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "TASK_HYGIENE_WARN R22-04 EXTERNAL_SERVICE task depends on external or containerized service runtime",
        "TASK_HYGIENE_WARN R22-04 MEMORY_SYSTEM_CHANGE task changes memory retrieval or .ralph/memory behavior",
    ]
