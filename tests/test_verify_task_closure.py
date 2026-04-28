from __future__ import annotations

from pathlib import Path

from scripts.ralph_common import is_bookkeeping_file
from scripts.verify_task_closure import verify_task_completion


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    write(project / "scripts" / "ralph_bot.py", 'async def cmd_status():\n    pass\n')
    write(project / "docs" / "GUIDE.md", "# Guide\n")
    write(project / "tests" / "test_sample.py", "def test_existing():\n    assert True\n")
    return project


def test_bookkeeping_only_diff_blocks_implementation_task(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    task = {
        "id": "R10-X1",
        "title": "Bot: /ask команда",
        "description": "Add /ask command to the bot",
        "acceptance_criteria": ["make test passes"],
    }

    result = verify_task_completion(task, project, ["tasks.json", "progress.md"])

    assert result["result"] == "fail_fix"
    assert result["bookkeeping_only"] is True


def test_missing_script_file_blocks_closure(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    task = {
        "id": "R10-X2",
        "title": "scripts/ralph_reflect.py — анализ metrics.csv → proposals.json",
        "description": "Create scripts/ralph_reflect.py and wire it into ralph_bot.py",
        "acceptance_criteria": ["scripts/ralph_reflect.py существует и запускается"],
    }

    result = verify_task_completion(task, project, ["scripts/ralph_bot.py"])

    assert result["result"] == "fail_fix"
    assert "expected script missing" in result["reason"]


def test_missing_command_handler_blocks_closure(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    task = {
        "id": "R10-X3",
        "title": "Bot: /ask команда — быстрый вопрос Ralph",
        "description": "Команда /ask <вопрос> отправляет вопрос в codex",
        "acceptance_criteria": ["test_ask_command_basic — /ask возвращает ответ от codex"],
    }

    result = verify_task_completion(task, project, ["scripts/ralph_bot.py", "tests/test_bot_commands.py"])

    assert result["result"] == "fail_fix"
    assert "missing handlers: /ask" in result["reason"]


def test_command_alias_handler_counts_as_valid_runtime_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    write(
        project / "scripts" / "ralph_bot.py",
        """
async def cmd_start_auto():
    return None

async def cmd_help():
    text = "/auto — run all"
    return None

async def handle_update(update):
    cmd = "/auto"
    if cmd == "/auto":
        await cmd_start_auto()
""".strip()
        + "\n",
    )
    write(
        project / "tests" / "test_bot_auto.py",
        "def test_auto_route():\n    assert '/auto'\n    assert 'cmd_start_auto'\n",
    )
    task = {
        "id": "R10-X3B",
        "title": "Bot: защита от двойного /auto",
        "description": "Add /auto guard in Telegram bot.",
        "acceptance_criteria": ["test_auto_route — /auto is wired"],
    }

    result = verify_task_completion(task, project, ["scripts/ralph_bot.py", "tests/test_bot_auto.py"])

    assert result["result"] == "pass"
    assert result["task_class"] == "command"


def test_missing_template_file_blocks_closure(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    task = {
        "id": "R10-X4",
        "title": "templates/AGENTS_COORDINATOR.md — роль координатора для проектов",
        "description": "Создать templates/AGENTS_COORDINATOR.md",
        "acceptance_criteria": ["templates/AGENTS_COORDINATOR.md существует"],
    }

    result = verify_task_completion(task, project, ["templates/AGENTS_CODER.md"])

    assert result["result"] == "fail_fix"
    assert "template" in result["reason"].lower()


def test_docs_only_task_can_pass_with_docs_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    write(project / "docs" / "TRUST_LAYER.md", "# Trust Layer\n")
    task = {
        "id": "R10-X5",
        "title": "Docs: trust layer memo",
        "description": "Update docs/TRUST_LAYER.md with trust notes",
        "acceptance_criteria": [],
    }

    result = verify_task_completion(task, project, ["docs/TRUST_LAYER.md"])

    assert result["result"] == "pass"
    assert result["task_class"] == "docs-only"


def test_tests_only_task_requires_actual_test_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    task = {
        "id": "R10-X6",
        "title": "Tests: покрытие /ask и /chat команд",
        "description": "Добавить тесты для /ask и /chat",
        "acceptance_criteria": [
            "test_ask_command_basic — /ask возвращает ответ от codex",
            "test_chat_command_start — /chat начинает сессию",
        ],
    }

    result = verify_task_completion(task, project, ["tasks.json", "progress.md"])

    assert result["result"] == "fail_fix"
    assert "no changed test files" in result["reason"] or "only bookkeeping" in result["reason"]


def test_reaudit_reporting_task_passes_with_saved_report_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    write(
        project / "scripts" / "re_audit_tasks.py",
        """
REPORT_FILE = PROJECT_DIR / "audit_report.md"

def human_verdict(verdict: str) -> str:
    mapping = {"verified_done": "verified", "false_positive": "false positive", "needs_human_review": "unclear"}
    return mapping.get(verdict, verdict)

print("Human-readable report saved to audit_report.md")
""".strip()
        + "\n",
    )
    write(
        project / "tests" / "test_re_audit_tasks.py",
        """
def test_report_written():
    assert "audit_report.md"
    assert "Classification: unclear"
""".strip()
        + "\n",
    )
    write(
        project / "audit_report.md",
        """
# Re-audit Report

## Results
### R10-09
- Classification: unclear
""".strip()
        + "\n",
    )
    task = {
        "id": "R10-09",
        "title": "Re-audit suspicious recent done tasks",
        "description": "Run the repaired trust checks over suspicious recent tasks and produce a compact truth report for human review.",
        "acceptance_criteria": [
            "Suspicious recent tasks are re-checked with the new audit flow",
            "Report classifies tasks as verified, partial, false positive, or unclear",
            "Results are saved in a human-readable report",
            "No hidden feature work is mixed into the re-audit step",
        ],
    }

    result = verify_task_completion(task, project, ["tasks.json", "audit_report.md", ".ralph/audit/R10-09.json"])

    assert result["result"] == "pass"
    assert result["task_class"] == "reaudit-report"


def test_generic_implementation_task_still_fails_on_report_and_state_files_only(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    write(project / "audit_report.md", "# Re-audit Report\n")
    task = {
        "id": "R10-X7",
        "title": "Improve orchestration reliability",
        "description": "Tighten generic runtime behavior.",
        "acceptance_criteria": ["make test passes"],
    }

    result = verify_task_completion(task, project, ["tasks.json", "audit_report.md", ".ralph/audit/R10-X7.json"])

    assert result["result"] == "fail_fix"
    assert result["task_class"] == "implementation"
    assert "only bookkeeping/state/report files changed" in result["reason"]


def test_runtime_memory_and_asset_manifest_paths_are_bookkeeping_after_normalization() -> None:
    assert is_bookkeeping_file(".ralph/memory/recent.md")
    assert is_bookkeeping_file("ralph/memory/recent.md")
    assert is_bookkeeping_file(".ralph/assets/inbox/hero-image.txt")
    assert is_bookkeeping_file("ralph/assets/inbox/hero-image.txt")
    assert is_bookkeeping_file("assets_manifest.json")


def test_target_files_mismatch_returns_detailed_debug_context(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    write(project / "src" / "generated_by_codex.ts", "export const generatedByCodex = true;\n")
    task = {
        "id": "R10-X8",
        "title": "Integration test task",
        "description": "Create or update src/generated_by_codex.ts with the required implementation.",
        "acceptance_criteria": ["src/generated_by_codex.ts exists"],
        "target_files": ["src/generated_by_codex.ts"],
    }

    result = verify_task_completion(task, project, ["src/other_file.ts"])

    assert result["result"] == "fail_fix"
    assert "target_files do not exactly match implementation evidence" in result["reason"]
    assert result["target_file_debug"]["expected_files"] == ["src/generated_by_codex.ts"]
    assert result["target_file_debug"]["unexpected_files"] == ["src/other_file.ts"]
    assert "DEBUG: Expected files: ['src/generated_by_codex.ts']" in result["debug_lines"]
