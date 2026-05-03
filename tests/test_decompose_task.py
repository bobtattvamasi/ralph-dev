from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLANNER = ROOT / "scripts" / "decompose_task.py"


def make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    return project_dir


def write_tasks(project_dir: Path, tasks: list[dict]) -> None:
    (project_dir / "tasks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project": "decompose-task-tests",
                "tasks": tasks,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_planner(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PLANNER), *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def test_planner_proposes_kickoff_split_without_modifying_tasks(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    original_tasks = [
        {
            "id": "R17-01",
            "phase": "R17",
            "status": "pending",
            "title": "ralph kickoff CLI command",
            "description": "Add new ralph.sh mode 'kickoff <path> <description>' that creates the target directory, runs ralph-init.sh there, and passes the description into AI generation steps.",
            "target_files": ["ralph.sh", "src/ralph/resources/ralph.sh"],
            "acceptance_criteria": [
                "ralph.sh kickoff path creates a directory with .ralph scaffold",
                "focused tests cover kickoff path",
            ],
            "priority": "high",
            "complexity": "moderate",
            "role": "coder",
        }
    ]
    write_tasks(project_dir, original_tasks)

    result = run_planner(project_dir, "R17-01")

    assert result.returncode == 0, result.stdout + result.stderr
    proposal = json.loads(result.stdout)
    assert proposal["parent_id"] == "R17-01"
    assert proposal["rationale"] == ["bootstrap_risk", "target_scope_too_narrow", "missing_test_target"]
    children = proposal["children"]
    assert [child["id"] for child in children] == ["R17-01A", "R17-01B", "R17-01C"]
    assert "CLI argument and mode parsing" in children[0]["title"]
    assert children[0]["target_files"] == ["ralph.sh", "src/ralph/resources/ralph.sh"]
    assert "ralph-init.sh" in children[1]["target_files"]
    assert children[2]["target_files"] == ["tests/test_ralph_shell_helpers.py"]
    after = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    assert after == original_tasks


def test_planner_apply_appends_children_once_and_keeps_parent_unchanged(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    parent = {
        "id": "R17-01",
        "phase": "R17",
        "status": "pending",
        "title": "ralph kickoff CLI command",
        "description": "Kickoff bootstrap and generation flow",
        "target_files": ["ralph.sh", "src/ralph/resources/ralph.sh"],
        "acceptance_criteria": ["focused tests cover kickoff path"],
        "priority": "high",
        "complexity": "moderate",
        "role": "coder",
    }
    write_tasks(project_dir, [parent])

    first = run_planner(project_dir, "R17-01", "--apply")
    second = run_planner(project_dir, "R17-01", "--apply")

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    tasks = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    assert tasks[0] == parent
    assert [task["id"] for task in tasks] == ["R17-01", "R17-01A", "R17-01B", "R17-01C"]
