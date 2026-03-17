from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.next_task import pick_next


REPO_ROOT = Path(__file__).resolve().parents[1]
REAUDIT = REPO_ROOT / "scripts" / "re_audit_tasks.py"


def write_tasks(project_dir: Path, tasks: list[dict]) -> None:
    (project_dir / "tasks.json").write_text(
        json.dumps({"version": 1, "project": "re-audit-test", "tasks": tasks}, indent=2) + "\n",
        encoding="utf-8",
    )


def run_reaudit(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {"RALPH_PROJECT_DIR": str(project_dir)}
    return subprocess.run(
        ["python3", str(REAUDIT), *args],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_reaudit_dry_run_classifies_obvious_false_positive(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_tasks(
        project_dir,
        [
            {
                "id": "R8-01",
                "phase": "R8",
                "title": "Create fetch channel script",
                "description": "Add scripts/fetch_channel.py for Telegram channel context.",
                "status": "done",
            }
        ],
    )

    result = run_reaudit(project_dir, "--task", "R8-01")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "R8-01 | done -> false_positive | script | Expected script is missing: scripts/fetch_channel.py" in result.stdout


def test_reaudit_apply_updates_tasks_for_strong_case(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_tasks(
        project_dir,
        [
            {
                "id": "R8-01",
                "phase": "R8",
                "title": "Create fetch channel script",
                "description": "Add scripts/fetch_channel.py for Telegram channel context.",
                "status": "done",
                "revision_notes": "",
            }
        ],
    )

    result = run_reaudit(project_dir, "--task", "R8-01", "--apply")
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Applied changes: 1" in result.stdout
    assert data["tasks"][0]["status"] == "false_positive"
    assert "Re-audit" in data["tasks"][0]["revision_notes"]
    assert data["tasks"][0]["completed_at"] is None


def test_reaudit_ambiguous_case_becomes_needs_human_review(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_tasks(
        project_dir,
        [
            {
                "id": "R5-99",
                "phase": "R5",
                "title": "Improve generic orchestrator behavior",
                "description": "Refine orchestration reliability.",
                "status": "done",
            }
        ],
    )

    result = run_reaudit(project_dir, "--task", "R5-99")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "R5-99 | done -> needs_human_review | implementation | Generic implementation task needs human review: repo truth is not strong enough." in result.stdout


def test_reaudit_verified_case_becomes_verified_done(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "templates").mkdir()
    (project_dir / "templates" / "AGENTS_COORDINATOR.md").write_text(
        "Ask clarifying questions.\nOutput PROJECT_BRIEF.md.\n",
        encoding="utf-8",
    )
    write_tasks(
        project_dir,
        [
            {
                "id": "R8-05",
                "phase": "R8",
                "title": "Add coordinator template",
                "description": "Create templates/AGENTS_COORDINATOR.md for project intake.",
                "status": "done",
                "acceptance_criteria": [
                    "templates/AGENTS_COORDINATOR.md exists"
                ],
            }
        ],
    )

    result = run_reaudit(project_dir, "--task", "R8-05")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "R8-05 | done -> verified_done | template | Expected template paths exist and match required content checks." in result.stdout


def test_reaudit_partial_case_is_reported(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "templates").mkdir()
    (project_dir / "templates" / "AGENTS_COORDINATOR.md").write_text("stub\n", encoding="utf-8")
    write_tasks(
        project_dir,
        [
            {
                "id": "R8-09",
                "phase": "R8",
                "title": "Add templates bundle",
                "description": "Create templates/AGENTS_COORDINATOR.md and templates/AGENTS_ARCHITECT.md.",
                "status": "done",
            }
        ],
    )

    result = run_reaudit(project_dir, "--task", "R8-09")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "R8-09 | done -> partial | template | Some expected templates are missing: templates/AGENTS_ARCHITECT.md" in result.stdout


def test_next_task_still_only_picks_pending() -> None:
    tasks = [
        {"id": "A", "status": "verified_done", "priority": "high", "phase": "R1"},
        {"id": "B", "status": "false_positive", "priority": "high", "phase": "R1"},
        {"id": "C", "status": "partial", "priority": "high", "phase": "R1"},
        {"id": "D", "status": "needs_human_review", "priority": "high", "phase": "R1"},
        {"id": "E", "status": "pending", "priority": "medium", "phase": "R1"},
    ]
    picked = pick_next(tasks)
    assert picked is not None
    assert picked["id"] == "E"
