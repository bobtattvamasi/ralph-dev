from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

from scripts.next_task import pick_next


REPO_ROOT = Path(__file__).resolve().parents[1]
REAUDIT = REPO_ROOT / "scripts" / "re_audit_tasks.py"


def test_reaudit_module_imports_from_repo_root() -> None:
    module = importlib.import_module("scripts.re_audit_tasks")
    assert module.__name__ == "scripts.re_audit_tasks"


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


def write_bot(project_dir: Path, content: str) -> None:
    scripts_dir = project_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "ralph_bot.py").write_text(content, encoding="utf-8")


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
    assert "=== Re-audit Summary ===" in result.stdout
    assert result.stdout.index("=== Re-audit Summary ===") < result.stdout.index("Results:")
    assert "R8-01 | done -> false_positive | script | Expected script is missing: scripts/fetch_channel.py" in result.stdout
    assert "Total checked: 1" in result.stdout
    assert "false_positive: 1" in result.stdout
    assert "applyable: 1" in result.stdout
    assert "Human-readable report saved to audit_report.md" in result.stdout

    report = (project_dir / "audit_report.md").read_text(encoding="utf-8")
    assert "# Re-audit Report" in report
    assert "- Scope: task R8-01" in report
    assert "### R8-01" in report
    assert "- Classification: false positive" in report
    assert "Expected script is missing: scripts/fetch_channel.py" in report


def test_reaudit_command_alias_handler_counts_as_verified_done(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_bot(
        project_dir,
        """
async def cmd_start_auto() -> None:
    return None

async def cmd_help() -> None:
    text = "/auto — run all"
    return None

async def handle_update(update: dict) -> None:
    cmd = "/auto"
    if cmd == "/auto":
        await cmd_start_auto()
""".strip()
        + "\n",
    )
    tests_dir = project_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_bot_auto.py").write_text(
        "def test_auto_route():\n    assert '/auto'\n    assert 'cmd_start_auto'\n",
        encoding="utf-8",
    )
    write_tasks(
        project_dir,
        [
            {
                "id": "R9-01",
                "phase": "R9",
                "title": "Bot: защита от двойного /auto",
                "description": "Add /auto guard in Telegram bot.",
                "status": "done",
            }
        ],
    )

    result = run_reaudit(project_dir, "--task", "R9-01")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "R9-01 | done -> verified_done | command | Command routing, handler alias, help text, and test evidence exist." in result.stdout


def test_reaudit_missing_command_still_becomes_false_positive(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_bot(project_dir, "async def cmd_help():\n    return None\n")
    write_tasks(
        project_dir,
        [
            {
                "id": "R6-01",
                "phase": "R6",
                "title": "Bot: /ask command",
                "description": "Add /ask command to Telegram bot.",
                "status": "done",
            }
        ],
    )

    result = run_reaudit(project_dir, "--task", "R6-01")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "R6-01 | done -> false_positive | command | Command implementation missing: /ask." in result.stdout


def test_reaudit_apply_updates_tasks_for_strong_case(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".ralph" / "audit").mkdir(parents=True)
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
    (project_dir / ".ralph" / "audit" / "R8-01.json").write_text(
        json.dumps(
            {
                "task_id": "R8-01",
                "status": "done",
                "verification": {"result": "pass", "reason": "stale success", "task_class": "script", "evidence_files": []},
                "changes": {"all": ["scripts/fetch_channel.py"], "non_bookkeeping": ["scripts/fetch_channel.py"]},
                "runtime_success": True,
                "verified_success": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_reaudit(project_dir, "--task", "R8-01", "--apply")
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Applied:" in result.stdout
    assert "- R8-01 -> false_positive -> Expected script is missing: scripts/fetch_channel.py" in result.stdout
    assert "Skipped: none" in result.stdout
    assert data["tasks"][0]["status"] == "false_positive"
    assert "false_positive" in data["tasks"][0]["revision_notes"]
    assert "Expected script is missing: scripts/fetch_channel.py" in data["tasks"][0]["revision_notes"]
    assert data["tasks"][0]["completed_at"] is None
    assert not (project_dir / ".ralph" / "audit" / "R8-01.json").exists()


def test_reaudit_apply_false_positive_keeps_reason_and_clears_stale_latest_run_truth(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".ralph" / "audit").mkdir(parents=True)
    write_tasks(
        project_dir,
        [
            {
                "id": "R5-01",
                "phase": "R5",
                "title": "Create run_eval helper",
                "description": "Add scripts/run_eval.py for evaluation flow.",
                "status": "done",
                "revision_notes": "old note",
            }
        ],
    )
    (project_dir / ".ralph" / "audit" / "R5-01.json").write_text(
        json.dumps(
            {
                "task_id": "R5-01",
                "status": "done",
                "verification": {"result": "pass", "reason": "stale success", "task_class": "script", "evidence_files": []},
                "changes": {"all": ["scripts/run_eval.py"], "non_bookkeeping": ["scripts/run_eval.py"]},
                "runtime_success": True,
                "verified_success": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_reaudit(project_dir, "--task", "R5-01", "--apply")
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    task = data["tasks"][0]

    assert result.returncode == 0, result.stdout + result.stderr
    assert "R5-01 | done -> false_positive | script | Expected script is missing: scripts/run_eval.py" in result.stdout
    assert task["status"] == "false_positive"
    assert "Re-audit " in task["revision_notes"]
    assert "false_positive" in task["revision_notes"]
    assert "Expected script is missing: scripts/run_eval.py" in task["revision_notes"]
    assert task["completed_at"] is None
    assert not (project_dir / ".ralph" / "audit" / "R5-01.json").exists()


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
    report = (project_dir / "audit_report.md").read_text(encoding="utf-8")
    assert "- Classification: unclear" in report


def test_reaudit_report_stays_task_scoped(tmp_path: Path) -> None:
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
            },
            {
                "id": "R5-99",
                "phase": "R5",
                "title": "Improve generic orchestrator behavior",
                "description": "Refine orchestration reliability.",
                "status": "done",
            },
        ],
    )

    result = run_reaudit(project_dir, "--task", "R8-01")

    assert result.returncode == 0, result.stdout + result.stderr
    report = (project_dir / "audit_report.md").read_text(encoding="utf-8")
    assert "### R8-01" in report
    assert "### R5-99" not in report


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


def test_reaudit_apply_skips_partial_and_needs_human_review(tmp_path: Path) -> None:
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
                "revision_notes": "",
            },
            {
                "id": "R5-99",
                "phase": "R5",
                "title": "Improve generic orchestrator behavior",
                "description": "Refine orchestration reliability.",
                "status": "done",
                "revision_notes": "",
            },
        ],
    )

    result = run_reaudit(project_dir, "--last", "2", "--apply")
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "partial: 1" in result.stdout
    assert "needs_human_review: 1" in result.stdout
    assert "applyable: 0" in result.stdout
    assert "Applied: none" in result.stdout
    assert "- R8-09 -> partial -> report-only in apply mode" in result.stdout
    assert "- R5-99 -> needs_human_review -> report-only in apply mode" in result.stdout
    assert data["tasks"][0]["status"] == "done"
    assert data["tasks"][1]["status"] == "done"
    assert data["tasks"][0]["revision_notes"] == ""
    assert data["tasks"][1]["revision_notes"] == ""


def test_reaudit_apply_skips_tasks_already_aligned_to_verified_done(tmp_path: Path) -> None:
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
                "status": "verified_done",
                "revision_notes": "trusted note",
                "completed_at": "2026-03-18T00:00:00+00:00",
                "acceptance_criteria": ["templates/AGENTS_COORDINATOR.md exists"],
            }
        ],
    )

    result = run_reaudit(project_dir, "--task", "R8-05", "--apply")
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    task = data["tasks"][0]

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Applied: none" in result.stdout
    assert "- R8-05 -> verified_done -> already aligned" in result.stdout
    assert task["status"] == "verified_done"
    assert task["revision_notes"] == "trusted note"
    assert task["completed_at"] == "2026-03-18T00:00:00+00:00"


def test_next_task_still_only_picks_pending() -> None:
    tasks = [
        {"id": "A", "status": "verified_done", "priority": "high", "phase": "R1"},
        {"id": "B", "status": "false_positive", "priority": "high", "phase": "R1"},
        {"id": "C", "status": "partial", "priority": "high", "phase": "R1"},
        {"id": "D", "status": "needs_human_review", "priority": "high", "phase": "R1"},
        {"id": "E", "status": "pending", "priority": "medium", "phase": "R1", "target_files": ["test_file.py"]},
    ]
    picked = pick_next(tasks)
    assert picked is not None
    assert picked["id"] == "E"
