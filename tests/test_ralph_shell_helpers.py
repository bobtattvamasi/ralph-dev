from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
RALPH_SH = REPO_ROOT / "ralph.sh"


def build_shell_fixture(tmp_path: Path, *, broken_verifier: bool = False) -> Path:
    project_dir = tmp_path / "project"
    (project_dir / "scripts").mkdir(parents=True)
    (project_dir / "logs").mkdir()
    (project_dir / "tests").mkdir()
    (project_dir / ".ralph" / "memory").mkdir(parents=True)
    (project_dir / ".ralph" / "audit").mkdir(parents=True)
    (project_dir / "src" / "ralph" / "resources" / "scripts").mkdir(parents=True)
    (project_dir / "tasks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project": "shell-helper-tests",
                "tasks": [
                    {
                        "id": "T01",
                        "phase": "OPS",
                        "title": "Bot: /auto command",
                        "description": "Wire /auto in the bot",
                        "status": "pending",
                        "acceptance_criteria": ["Wire /auto through the bot route cleanly."],
                        "target_files": ["scripts/ralph_bot.py"],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / "progress.md").write_text("# Progress\n", encoding="utf-8")
    for name, content in (
        ("AGENTS.md", "# AGENTS\n"),
        ("ARCHITECTURE.md", "# Architecture\n"),
        ("MEMORY_SYSTEM.md", "# Memory\n"),
        ("AGENTS_CODER.md", "# Coder\n"),
        ("AGENTS_LEAD.md", "# Lead\n"),
        (".ralph/memory/core.md", "# Core\n"),
        (".ralph/memory/recent.md", "# Recent\n"),
    ):
        (project_dir / name).write_text(content, encoding="utf-8")

    for script_name in ("extract_json.py", "ralph_common.py", "review_service.py"):
        shutil.copy2(REPO_ROOT / "scripts" / script_name, project_dir / "scripts" / script_name)
    verify_target = project_dir / "scripts" / "verify_task_closure.py"
    if broken_verifier:
        verify_target.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    else:
        shutil.copy2(REPO_ROOT / "scripts" / "verify_task_closure.py", verify_target)

    shell_lines = RALPH_SH.read_text(encoding="utf-8").splitlines()
    cutoff = next(index for index, line in enumerate(shell_lines) if line.startswith('case "$MODE" in'))
    (project_dir / "ralph_helpers.sh").write_text("\n".join(shell_lines[:cutoff]) + "\n", encoding="utf-8")
    return project_dir


def init_git_repo(project_dir: Path) -> None:
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_dir, check=True, capture_output=True, text=True)


def run_helper(project_dir: Path, body: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    runner = project_dir / "run_helper.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "source ./ralph_helpers.sh\n"
        f"{body}\n",
        encoding="utf-8",
    )
    runner.chmod(0o755)
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        [str(runner)],
        cwd=project_dir,
        env=run_env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def write_tool_shim(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def write_project_test_commands(project_dir: Path, test_cmd: str, test_cmd_fast: str | None = None) -> None:
    payload: dict[str, str] = {"test_cmd": test_cmd}
    if test_cmd_fast is not None:
        payload["test_cmd_fast"] = test_cmd_fast
    (project_dir / ".ralph" / "project.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def test_handoff_candidate_paths_include_packaged_and_test_evidence(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "scripts" / "ralph_bot.py").write_text(
        "async def cmd_start_auto():\n    return None\n\n"
        "async def handle_update(cmd):\n"
        "    if cmd == '/auto':\n"
        "        await cmd_start_auto()\n",
        encoding="utf-8",
    )
    (project_dir / "src" / "ralph" / "resources" / "scripts" / "ralph_bot.py").write_text(
        "async def cmd_start_auto():\n    return None\n",
        encoding="utf-8",
    )
    (project_dir / "tests" / "test_bot_auto.py").write_text(
        "def test_auto_route():\n    assert '/auto'\n    assert 'cmd_start_auto'\n",
        encoding="utf-8",
    )
    import json as _json
    tasks_data = _json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    task_obj = tasks_data["tasks"][0]
    task_json = _json.dumps(task_obj)

    result = run_helper(
        project_dir,
        f"handoff_candidate_paths '{task_json}'",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    lines = set(result.stdout.splitlines())
    assert "scripts/ralph_bot.py" in lines
    assert "src/ralph/resources/scripts/ralph_bot.py" in lines
    assert "tests/test_bot_auto.py" in lines


def test_handoff_worktree_evidence_paths_only_returns_dirty_candidate_paths(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    init_git_repo(project_dir)
    (project_dir / "scripts" / "run_eval.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (project_dir / "src" / "ralph" / "resources" / "scripts" / "run_eval.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (project_dir / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)
    (project_dir / "scripts" / "run_eval.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (project_dir / "ARCHITECTURE.md").write_text("# Architecture\nchanged\n", encoding="utf-8")
    task = {
        "id": "T02",
        "phase": "OPS",
        "title": "scripts/run_eval.py",
        "description": "Add scripts/run_eval.py and keep it importable.",
        "status": "pending",
        "acceptance_criteria": ["scripts/run_eval.py exists and is safely executable or importable"],
        "target_files": ["scripts/run_eval.py"],
    }

    result = run_helper(
        project_dir,
        f"handoff_worktree_evidence_paths '{json.dumps(task)}'",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert "scripts/run_eval.py" in lines
    assert "ARCHITECTURE.md" not in lines


def test_handoff_commit_parent_hash_uses_empty_tree_for_root_commit(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    init_git_repo(project_dir)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "root"], cwd=project_dir, check=True, capture_output=True, text=True)
    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = run_helper(project_dir, f"handoff_commit_parent_hash '{commit_hash}'")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def test_validate_lead_review_json_normalizes_placeholder_and_done_decisions(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)

    placeholder = run_helper(
        project_dir,
        "REVIEW_JSON='{\"decision\":\"approve\",\"task_id\":\"TASK-ID\",\"summary\":\"one line summary\"}'\n"
        "validate_lead_review_json\n"
        "printf '%s' \"$REVIEW_JSON\"\n",
    )
    done_review = run_helper(
        project_dir,
        "REVIEW_JSON='{\"decision\":\"done\",\"task_id\":\"T01\",\"summary\":\"ship it\"}'\n"
        "validate_lead_review_json\n"
        "printf '%s' \"$REVIEW_JSON\"\n",
    )

    assert json.loads(placeholder.stdout)["decision"] == "fix"
    assert "placeholder/template JSON" in json.loads(placeholder.stdout)["fix_instructions"]
    assert json.loads(done_review.stdout)["decision"] == "approve"


def test_parse_lead_review_json_fail_closes_on_unparseable_sources(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "review.json").write_text("not json\n", encoding="utf-8")
    (project_dir / "lead_output.txt").write_text("also not json\n", encoding="utf-8")

    result = run_helper(
        project_dir,
        "REVIEW_FILE=review.json\n"
        "LEAD_OUTPUT=lead_output.txt\n"
        "parse_lead_review_json\n"
        "printf '%s\\n%s' \"$REVIEW_JSON_SOURCE\" \"$REVIEW_JSON\"\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "unparsed_fail_closed"
    parsed = json.loads(lines[1])
    assert parsed["decision"] == "fix"
    assert "could not be parsed safely" in parsed["fix_instructions"]


def test_run_task_closure_verification_falls_back_when_verifier_crashes(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path, broken_verifier=True)

    result = run_helper(
        project_dir,
        "TASK_JSON='{\"id\":\"T01\",\"title\":\"Task\",\"description\":\"desc\"}'\n"
        "PRE_HASH=$(git hash-object -t tree /dev/null)\n"
        "REVIEW_BASE_HASH=\"$PRE_HASH\"\n"
        "REVIEW_TARGET_HASH=\"$PRE_HASH\"\n"
        "run_task_closure_verification\n"
        "printf '%s\\n%s\\n%s\\n%s' \"$VERIFICATION_RESULT\" \"$VERIFICATION_CLASS\" \"$VERIFICATION_REASON\" \"$VERIFICATION_NON_BOOKKEEPING\"\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "needs_human_review"
    assert lines[1] == "implementation"
    assert lines[2] == "Verification script failed unexpectedly."


def test_startup_dependency_preflight_fails_fast_for_missing_tools_and_skips_status(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)

    for tool in ("codex", "gtimeout", "git", "python3"):
        missing = run_helper(
            project_dir,
            f"command() {{ if [ \"$1\" = \"-v\" ] && [ \"$2\" = \"{tool}\" ]; then return 1; fi; builtin command \"$@\"; }}\n"
            "MODE=task\nensure_startup_runtime_dependencies\n",
        )
        combined = missing.stdout + missing.stderr
        assert missing.returncode != 0, combined
        assert f"Missing runtime dependency: {tool}" in combined

    ok = run_helper(
        project_dir,
        "MODE=task\nensure_startup_runtime_dependencies\nprintf 'ok\\n'\n",
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert ok.stdout.strip() == "ok"

    status_ok = run_helper(
        project_dir,
        "MODE=status\nensure_startup_runtime_dependencies\nprintf 'status-ok\\n'\n",
    )
    assert status_ok.returncode == 0, status_ok.stdout + status_ok.stderr


@pytest.mark.overnight_smoke
def test_auto_and_phase_modes_prefer_project_fast_test_command_but_task_mode_uses_full_command(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    write_project_test_commands(
        project_dir,
        "python3 -c \"from pathlib import Path; Path('full.log').write_text('full\\n', encoding='utf-8')\"",
        "python3 -c \"from pathlib import Path; Path('fast.log').write_text('fast\\n', encoding='utf-8')\"",
    )

    auto_result = run_helper(
        project_dir,
        "MODE=auto\n"
        "PROJECT_TEST_CMD=\"$(load_project_test_command)\"\n"
        "PROJECT_TEST_CMD_FAST=\"$(load_project_fast_test_command || true)\"\n"
        "run_project_test_command\n",
    )
    assert auto_result.returncode == 0, auto_result.stdout + auto_result.stderr
    assert (project_dir / "fast.log").read_text(encoding="utf-8").splitlines() == ["fast"]
    assert not (project_dir / "full.log").exists()

    (project_dir / "fast.log").unlink(missing_ok=True)
    phase_result = run_helper(
        project_dir,
        "MODE=phase\n"
        "PROJECT_TEST_CMD=\"$(load_project_test_command)\"\n"
        "PROJECT_TEST_CMD_FAST=\"$(load_project_fast_test_command || true)\"\n"
        "run_project_test_command\n",
    )
    assert phase_result.returncode == 0, phase_result.stdout + phase_result.stderr
    assert (project_dir / "fast.log").read_text(encoding="utf-8").splitlines() == ["fast"]
    assert not (project_dir / "full.log").exists()

    (project_dir / "fast.log").unlink(missing_ok=True)
    task_result = run_helper(
        project_dir,
        "MODE=task\n"
        "PROJECT_TEST_CMD=\"$(load_project_test_command)\"\n"
        "PROJECT_TEST_CMD_FAST=\"$(load_project_fast_test_command || true)\"\n"
        "run_project_test_command\n",
    )
    assert task_result.returncode == 0, task_result.stdout + task_result.stderr
    assert (project_dir / "full.log").read_text(encoding="utf-8").splitlines() == ["full"]
    assert not (project_dir / "fast.log").exists()


def test_tester_phase_logs_start_done_and_structured_report(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    write_project_test_commands(
        project_dir,
        "python3 -c \"print('full-ok')\"",
        "python3 -c \"print('fast-ok')\"",
    )

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "PROJECT_TEST_CMD=\"$(load_project_test_command)\"\n"
        "PROJECT_TEST_CMD_FAST=\"$(load_project_fast_test_command || true)\"\n"
        "TESTER_STATUS=0\n"
        "run_tester_phase T01 HEAD HEAD || TESTER_STATUS=$?\n"
        "printf 'STATUS=%s\\nREPORT=%s\\n' \"$TESTER_STATUS\" \"$TESTER_REPORT\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "TESTER_START T01 command=python3 -c \"print('fast-ok')\"" in combined
    assert "TESTER_DONE T01 exit_code=0 duration=" in combined
    assert "STATUS=0" in result.stdout
    report_line = next(line for line in result.stdout.splitlines() if line.startswith("REPORT="))
    report = json.loads(report_line[len("REPORT="):])
    assert report["task_id"] == "T01"
    assert report["command"] == "python3 -c \"print('fast-ok')\""
    assert report["exit_code"] == 0
    assert report["timed_out"] is False
    assert "fast-ok" in report["combined_output_tail"]


def test_tester_timeout_logs_reason_and_structured_report(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    write_project_test_commands(
        project_dir,
        "python3 -c \"import time; time.sleep(2)\"",
        "python3 -c \"import time; time.sleep(2)\"",
    )

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "PROJECT_TEST_CMD=\"$(load_project_test_command)\"\n"
        "PROJECT_TEST_CMD_FAST=\"$(load_project_fast_test_command || true)\"\n"
        "TESTER_STATUS=0\n"
        "run_tester_phase T01 HEAD HEAD || TESTER_STATUS=$?\n"
        "printf 'STATUS=%s\\nREASON=%s\\nTIMED_OUT=%s\\nREPORT=%s\\n' \"$TESTER_STATUS\" \"$TESTER_REASON\" \"$TESTER_TIMED_OUT\" \"$TESTER_REPORT\"\n",
        env={"RALPH_TESTER_FAST_TIMEOUT_SEC": "1"},
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "TESTER_TIMEOUT T01 timeout=1s command=python3 -c \"import time; time.sleep(2)\"" in combined
    assert "TESTER_DONE T01 exit_code=124 duration=" in combined
    assert "STATUS=124" in result.stdout
    assert "REASON=tester_timeout" in result.stdout
    assert "TIMED_OUT=true" in result.stdout
    report_line = next(line for line in result.stdout.splitlines() if line.startswith("REPORT="))
    report = json.loads(report_line[len("REPORT="):])
    assert report["exit_code"] == 124
    assert report["timed_out"] is True


def test_phase_mode_tester_uses_fast_command_and_timeout(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    write_project_test_commands(
        project_dir,
        "python3 -c \"print('full-ok')\"",
        "python3 -c \"print('phase-fast-ok')\"",
    )

    result = run_helper(
        project_dir,
        "MODE=phase\n"
        "PROJECT_TEST_CMD=\"$(load_project_test_command)\"\n"
        "PROJECT_TEST_CMD_FAST=\"$(load_project_fast_test_command || true)\"\n"
        "printf 'CMD=%s\\nTIMEOUT=%s\\n' \"$(current_project_test_command)\" \"$(current_project_test_timeout_sec)\"\n"
        "TESTER_STATUS=0\n"
        "run_tester_phase T01 HEAD HEAD || TESTER_STATUS=$?\n"
        "printf 'STATUS=%s\\nREPORT=%s\\n' \"$TESTER_STATUS\" \"$TESTER_REPORT\"\n",
        env={"RALPH_TESTER_FAST_TIMEOUT_SEC": "7", "RALPH_TESTER_FULL_TIMEOUT_SEC": "33"},
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "CMD=python3 -c \"print('phase-fast-ok')\"" in result.stdout
    assert "TIMEOUT=7" in result.stdout
    assert "TESTER_START T01 command=python3 -c \"print('phase-fast-ok')\"" in combined
    report_line = next(line for line in result.stdout.splitlines() if line.startswith("REPORT="))
    report = json.loads(report_line[len("REPORT="):])
    assert report["command"] == "python3 -c \"print('phase-fast-ok')\""


def test_run_next_task_helper_blocks_on_helper_failure(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "scripts" / "next_task.py").write_text(
        "import sys\nprint('selection boom', file=sys.stderr)\nsys.exit(2)\n",
        encoding="utf-8",
    )

    result = run_helper(
        project_dir,
        "write_state() { printf '%s|%s|%s|%s\\n' \"$1\" \"$2\" \"$3\" \"$4\" > state_capture.txt; }\n"
        "run_next_task_helper --task T01\n",
    )

    assert result.returncode == 1
    assert "next_task.py failed while selecting the next task" in (result.stdout + result.stderr)
    assert "selection boom" in (result.stdout + result.stderr)
    assert (project_dir / "state_capture.txt").read_text(encoding="utf-8").strip() == (
        "blocked||task_selection|next_task.py failed during task selection"
    )


def test_run_update_task_strict_blocks_on_persist_failure(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "scripts" / "update_task.py").write_text(
        "import sys\nprint('persist boom', file=sys.stderr)\nsys.exit(3)\n",
        encoding="utf-8",
    )

    result = run_helper(
        project_dir,
        "write_state() { printf '%s|%s|%s|%s\\n' \"$1\" \"$2\" \"$3\" \"$4\" > state_capture.txt; }\n"
        "run_update_task_strict T01 blocked 'broken' task_status 'update_task.py failed'\n",
    )

    assert result.returncode == 1
    assert "update_task.py failed for T01 -> blocked" in (result.stdout + result.stderr)
    assert "persist boom" in (result.stdout + result.stderr)
    assert (project_dir / "state_capture.txt").read_text(encoding="utf-8").strip() == (
        "blocked|T01|task_status|update_task.py failed"
    )


def test_enforce_task_wall_clock_cap_blocks_long_running_task(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "init_auto_run_summary\n"
        "write_state() { printf '%s|%s|%s|%s\\n' \"$1\" \"$2\" \"$3\" \"$4\" > state_capture.txt; }\n"
        "TASK_ID='T01'\n"
        "TASK_START=$(( $(date +%s) - 5 ))\n"
        "TASK_WALL_CAP=1\n"
        "enforce_task_wall_clock_cap \"$TASK_ID\" \"$TASK_WALL_CAP\"\n",
    )

    assert result.returncode == 1
    assert "Task T01 exceeded wall-clock cap (1s), marking blocked" in (result.stdout + result.stderr)
    assert "AUTO_RUN_SUMMARY done=0 failed=0 blocked=1 skipped=0" in result.stdout
    assert "AUTO_TASK_RESULT T01 status=blocked reason=Task T01 exceeded wall-clock cap (1s)" in result.stdout
    assert (project_dir / "state_capture.txt").read_text(encoding="utf-8").strip() == (
        "blocked|T01|task_wall_cap|Task T01 exceeded wall-clock cap (1s)"
    )


def test_auto_run_summary_tracks_done_failed_blocked_and_skipped_tasks(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "init_auto_run_summary\n"
        "AUTO_SUMMARY_START_TS=$(( $(date +%s) - 3 ))\n"
        "auto_record_task_result 'T01' done 'approved'\n"
        "auto_record_task_result 'T02' failed 'Final git commit failed after approval'\n"
        "auto_record_task_result 'T03' blocked 'Missing required asset from handoff queue'\n"
        "auto_record_task_result 'T04' skipped 'Skipped by user via Telegram'\n"
        "print_auto_run_summary\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith("AUTO_RUN_SUMMARY done=1 failed=1 blocked=1 skipped=1 duration=")
    duration = int(lines[0].rsplit("duration=", 1)[1])
    assert 3 <= duration <= 5
    assert "AUTO_TASK_RESULT T02 status=failed reason=Final git commit failed after approval" in lines
    assert "AUTO_TASK_RESULT T03 status=blocked reason=Missing required asset from handoff queue" in lines
    assert "AUTO_TASK_RESULT T04 status=skipped reason=Skipped by user via Telegram" in lines


def test_auto_run_summary_preserves_tester_timeout_reason(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "init_auto_run_summary\n"
        "auto_record_task_result 'T01' blocked 'tester_timeout'\n"
        "print_auto_run_summary\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith("AUTO_RUN_SUMMARY done=0 failed=0 blocked=1 skipped=0 duration=")
    assert "AUTO_TASK_RESULT T01 status=blocked reason=tester_timeout" in lines


def test_auto_run_summary_records_skipped_unsafe_tasks_from_next_task_helper(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "scripts" / "next_task.py").write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('TASK_SKIPPED_UNSAFE T01 BOOTSTRAP_FEATURE', file=sys.stderr)\n"
        "print('null')\n",
        encoding="utf-8",
    )

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "init_auto_run_summary\n"
        "TASK_JSON=$(run_next_task_helper --auto-safe)\n"
        "print_auto_run_summary\n"
        "printf 'TASK_JSON=%s\\n' \"$TASK_JSON\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "TASK_SKIPPED_UNSAFE T01 BOOTSTRAP_FEATURE" in combined
    assert "AUTO_RUN_SUMMARY done=0 failed=0 blocked=0 skipped=1" in result.stdout
    assert "AUTO_TASK_RESULT T01 status=skipped reason=BOOTSTRAP_FEATURE" in result.stdout
    assert "TASK_JSON=null" in result.stdout


def test_auto_run_summary_records_dependency_deadlock_when_no_runnable_tasks_remain(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "scripts" / "next_task.py").write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "if '--explain' in sys.argv:\n"
        "    print(json.dumps({'reason': 'blocked_dependencies', 'blocked_pending': [{'id': 'R20-07', 'title': 'Summary task', 'unmet_dependencies': ['R20-03']}, {'id': 'R20-10', 'title': 'Skip unsafe features', 'unmet_dependencies': ['R20-03']}]}))\n"
        "else:\n"
        "    print('null')\n",
        encoding="utf-8",
    )

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "init_auto_run_summary\n"
        "set_queue_exit_state\n"
        "print_auto_run_summary\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "AUTO_RUN_SUMMARY done=0 failed=0 blocked=2 skipped=0" in result.stdout
    assert "AUTO_TASK_RESULT R20-07 status=blocked reason=dependency_deadlock" in result.stdout
    assert "AUTO_TASK_RESULT R20-10 status=blocked reason=dependency_deadlock" in result.stdout


def test_final_commit_noop_already_committed_detected_as_successful_finalization(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    init_git_repo(project_dir)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "wip(T01): coder changes"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    result = run_helper(
        project_dir,
        "TASK_ID='T01'\n"
        "CLASS=$(classify_final_commit_failure \"$TASK_ID\")\n"
        "if [ \"$CLASS\" = 'already_committed' ]; then log \"FINAL_COMMIT_NOOP_ALREADY_COMMITTED $TASK_ID\"; fi\n"
        "printf 'CLASS=%s\\n' \"$CLASS\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "CLASS=already_committed" in result.stdout
    assert "FINAL_COMMIT_NOOP_ALREADY_COMMITTED T01" in combined


def test_final_commit_noop_without_matching_wip_blocks_with_specific_reason(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    init_git_repo(project_dir)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "init_auto_run_summary\n"
        "TASK_ID='T01'\n"
        "CLASS=$(classify_final_commit_failure \"$TASK_ID\")\n"
        "if [ \"$CLASS\" = 'noop_without_changes' ]; then\n"
        "  log \"FINAL_COMMIT_NOOP_WITHOUT_CHANGES $TASK_ID\"\n"
        "  auto_record_task_result \"$TASK_ID\" blocked 'final_commit_noop_without_changes'\n"
        "fi\n"
        "print_auto_run_summary\n"
        "printf 'CLASS=%s\\n' \"$CLASS\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "CLASS=noop_without_changes" in result.stdout
    assert "FINAL_COMMIT_NOOP_WITHOUT_CHANGES T01" in combined
    assert "AUTO_TASK_RESULT T01 status=blocked reason=final_commit_noop_without_changes" in result.stdout


def test_final_commit_failure_with_remaining_changes_stays_blocking(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    init_git_repo(project_dir)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)
    (project_dir / "AGENTS.md").write_text("# AGENTS\nchanged\n", encoding="utf-8")

    result = run_helper(
        project_dir,
        "TASK_ID='T01'\n"
        "CLASS=$(classify_final_commit_failure \"$TASK_ID\")\n"
        "printf 'CLASS=%s\\n' \"$CLASS\"\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLASS=failed" in result.stdout


def test_scope_contract_invalid_blocks_auto_task_without_consuming_retry(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    shutil.copy2(REPO_ROOT / "scripts" / "update_task.py", project_dir / "scripts" / "update_task.py")
    (project_dir / "scripts" / "ralph_notify.py").write_text("print('ok')\n", encoding="utf-8")

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "TASK_ID='T01'\n"
        "FIX_RETRY=0\n"
        "TASK_BLOCKED=false\n"
        "TASK_DONE=false\n"
        "init_auto_run_summary\n"
        "defer_scope_contract_invalid_task 'tests/test_ralph_shell_helpers.py'\n"
        "print_auto_run_summary\n"
        "printf 'FIX_RETRY=%s\\nTASK_BLOCKED=%s\\nTASK_DONE=%s\\n' \"$FIX_RETRY\" \"$TASK_BLOCKED\" \"$TASK_DONE\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "TASK_CONTRACT_INVALID T01 tests/test_ralph_shell_helpers.py" in combined
    assert "AUTO_TASK_RESULT T01 status=blocked reason=scope_contract_invalid" in result.stdout
    assert "FIX_RETRY=0" in result.stdout
    assert "TASK_BLOCKED=true" in result.stdout
    assert "TASK_DONE=true" in result.stdout
    task = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    assert task["status"] == "blocked"
    assert task["revision_notes"] == (
        "scope_contract_invalid: auto-reverted out-of-scope files: tests/test_ralph_shell_helpers.py"
    )


def test_scope_contract_repair_suggestion_marks_missing_test_target(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    shutil.copy2(REPO_ROOT / "scripts" / "update_task.py", project_dir / "scripts" / "update_task.py")
    (project_dir / "scripts" / "ralph_notify.py").write_text("print('ok')\n", encoding="utf-8")

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "TASK_ID='T01'\n"
        "init_auto_run_summary\n"
        "defer_scope_contract_invalid_task $'tests/test_mutator_scripts.py\\nfoo/bar.py'\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert (
        "TASK_CONTRACT_REPAIR_SUGGESTION T01 reason=missing_test_target "
        "add_target_files=tests/test_mutator_scripts.py,foo/bar.py"
    ) in combined


def test_scope_contract_repair_suggestion_marks_missing_config_target(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    shutil.copy2(REPO_ROOT / "scripts" / "update_task.py", project_dir / "scripts" / "update_task.py")
    (project_dir / "scripts" / "ralph_notify.py").write_text("print('ok')\n", encoding="utf-8")

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "TASK_ID='T01'\n"
        "init_auto_run_summary\n"
        "defer_scope_contract_invalid_task $'.ralph/project.json\\npyproject.toml'\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert (
        "TASK_CONTRACT_REPAIR_SUGGESTION T01 reason=missing_config_target "
        "add_target_files=.ralph/project.json,pyproject.toml"
    ) in combined


def test_auto_apply_scope_contract_repair_adds_safe_test_target_and_commits(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    init_git_repo(project_dir)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)

    result = run_helper(
        project_dir,
        "TASK_ID='T01'\n"
        "TASK_CONTRACT_REPAIR_ATTEMPTED=0\n"
        "STATUS=0\n"
        "auto_apply_scope_contract_repair 'tests/test_ralph_shell_helpers.py' || STATUS=$?\n"
        "printf 'STATUS=%s\\n' \"$STATUS\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "STATUS=0" in result.stdout
    assert (
        "TASK_CONTRACT_REPAIR_APPLIED T01 reason=missing_test_target "
        "add_target_files=tests/test_ralph_shell_helpers.py"
    ) in combined
    task = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    assert task["target_files"] == ["scripts/ralph_bot.py", "tests/test_ralph_shell_helpers.py"]
    commit_subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert commit_subject == "chore: repair target_files for T01"


def test_auto_apply_scope_contract_repair_allows_known_config_path(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    init_git_repo(project_dir)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)

    result = run_helper(
        project_dir,
        "TASK_ID='T01'\n"
        "STATUS=0\n"
        "auto_apply_scope_contract_repair '.ralph/project.json' || STATUS=$?\n"
        "printf 'STATUS=%s\\n' \"$STATUS\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "STATUS=0" in result.stdout
    assert (
        "TASK_CONTRACT_REPAIR_APPLIED T01 reason=missing_config_target "
        "add_target_files=.ralph/project.json"
    ) in combined


def test_auto_apply_scope_contract_repair_refuses_unsafe_source_path(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    init_git_repo(project_dir)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)

    original_tasks = (project_dir / "tasks.json").read_text(encoding="utf-8")
    original_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = run_helper(
        project_dir,
        "TASK_ID='T01'\n"
        "STATUS=0\n"
        "auto_apply_scope_contract_repair 'src/app.py' || STATUS=$?\n"
        "printf 'STATUS=%s\\n' \"$STATUS\"\n",
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "STATUS=1" in result.stdout
    assert "TASK_CONTRACT_REPAIR_APPLIED" not in combined
    assert (project_dir / "tasks.json").read_text(encoding="utf-8") == original_tasks
    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert current_commit == original_commit


def test_recovery_startup_resets_stale_running_state_to_idle(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "ralph_state.json").write_text(
        json.dumps(
            {
                "status": "running",
                "current_task": "T01",
                "current_phase_step": "coder",
                "message": "Coder implementing...",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / "ralph_main.pid").write_text("4242\n", encoding="utf-8")

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "check_and_recover_state\n"
        "if [ \"$RECOVERY_MODE\" -eq 1 ]; then\n"
        "  write_state \"idle\" \"\" \"recovery\" \"Recovered stale non-idle state ($PREV_STATUS)\"\n"
        "else\n"
        "  write_state \"idle\" \"\" \"idle\" \"Ready\"\n"
        "fi\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads((project_dir / "ralph_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "idle"
    assert state["current_task"] == ""
    assert state["current_phase_step"] == "recovery"
    assert "Recovered stale non-idle state (running)" in state["message"]


def test_recovery_startup_blocks_on_malformed_state_file(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "ralph_state.json").write_text("{broken json\n", encoding="utf-8")

    result = run_helper(
        project_dir,
        "MODE=auto\n"
        "check_and_recover_state\n"
        "if [ \"${RECOVERY_INVALID_STATE:-0}\" -eq 1 ]; then\n"
        "  write_state \"blocked\" \"\" \"recovery\" \"${RECOVERY_INVALID_REASON:-Invalid ralph_state.json or runtime recovery metadata}\"\n"
        "  exit 1\n"
        "fi\n",
    )

    assert result.returncode == 1
    state = json.loads((project_dir / "ralph_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "blocked"
    assert state["current_phase_step"] == "recovery"
    assert "malformed state JSON" in state["message"]


def test_recovery_marks_idle_state_with_live_codex_pid_as_invalid_and_kills_it(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    sleeper = subprocess.Popen(["sleep", "30"], cwd=project_dir)
    try:
        (project_dir / "ralph_state.json").write_text(
            json.dumps(
                {
                    "status": "idle",
                    "current_task": "",
                    "current_phase_step": "completed",
                    "message": "Idle",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (project_dir / "ralph_codex.pid").write_text(f"{sleeper.pid}\n", encoding="utf-8")

        result = run_helper(
            project_dir,
            "check_and_recover_state\n"
            "printf '%s|%s\\n' \"$RECOVERY_INVALID_STATE\" \"$RECOVERY_INVALID_REASON\"\n",
        )

        assert result.returncode == 0, result.stdout + result.stderr
        invalid_state, reason = result.stdout.strip().splitlines()[-1].split("|", 1)
        assert invalid_state == "1"
        assert "Active ralph_codex.pid detected while previous state is idle" in reason
        sleeper.wait(timeout=5)
    finally:
        if sleeper.poll() is None:
            sleeper.terminate()
            sleeper.wait(timeout=5)


def test_apply_control_action_snapshot_blocks_on_empty_control_payload(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)

    result = run_helper(
        project_dir,
        "run_control_helper() { :; }\n"
        "TASK_ID='T01'\n"
        "apply_control_action_snapshot 'test_control'\n",
    )

    assert result.returncode == 1
    state = json.loads((project_dir / "ralph_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "blocked"
    assert state["current_task"] == "T01"
    assert state["current_phase_step"] == "control_file"
    assert "ralph_control.json" in state["message"] or "control payload" in state["message"]


def test_cleanup_kills_main_process_group_and_removes_pid_files(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    (project_dir / "ralph_codex.pgid").write_text("321\n", encoding="utf-8")
    (project_dir / "ralph_codex.pid").write_text("654\n", encoding="utf-8")
    (project_dir / "ralph_main.pid").write_text("987\n", encoding="utf-8")

    result = run_helper(
        project_dir,
        "kill_process_group() { printf 'pgid:%s\\n' \"$1\" >> cleanup_calls.log; }\n"
        "kill_tree() { printf 'pid:%s\\n' \"$1\" >> cleanup_calls.log; }\n"
        "process_group_for_pid() { if [ \"$1\" = \"987\" ]; then printf '9870\\n'; fi }\n"
        "OWNS_MAIN_PID=1\n"
        "cleanup\n"
        "cleanup\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = (project_dir / "cleanup_calls.log").read_text(encoding="utf-8").splitlines()
    assert "pgid:321" in calls
    assert "pid:654" in calls
    assert "pgid:9870" in calls
    assert "pid:987" in calls
    assert not (project_dir / "ralph_codex.pgid").exists()
    assert not (project_dir / "ralph_codex.pid").exists()
    assert not (project_dir / "ralph_main.pid").exists()


def test_task_scoped_diff_between_refs_includes_ralph_shell_changes(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    shutil.copy2(RALPH_SH, project_dir / "ralph.sh")
    init_git_repo(project_dir)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)
    base_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    ralph_path = project_dir / "ralph.sh"
    ralph_path.write_text(ralph_path.read_text(encoding="utf-8") + "\n# shell change\n", encoding="utf-8")
    subprocess.run(["git", "add", "ralph.sh"], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "change ralph shell"], cwd=project_dir, check=True, capture_output=True, text=True)
    head_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = run_helper(
        project_dir,
        f"task_scoped_diff_between_refs '{base_hash}' '{head_hash}'\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "diff --git a/ralph.sh b/ralph.sh" in result.stdout
    assert "+# shell change" in result.stdout


def test_write_benchmark_report_clamps_other_time_and_accepts_missing_manual_duration(tmp_path: Path) -> None:
    project_dir = build_shell_fixture(tmp_path)
    auto_logs = project_dir / "auto" / "logs"
    auto_logs.mkdir(parents=True)
    manual_results = project_dir / "manual.jsonl"
    report_file = project_dir / "report.json"
    (auto_logs / "metrics.csv").write_text(
        "\n".join(
            [
                "timestamp,task_id,status,duration_s,attempts",
                "2026-03-30T10:00:00Z,T01,success,5,1",
                "2026-03-30T10:01:00Z,T02,success,0,2",
                "2026-03-30T10:02:00Z,T03,success,1,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (auto_logs / "task_phase_timings.csv").write_text(
        "\n".join(
            [
                "timestamp,task_id,attempt,mode,phase,duration_s",
                "2026-03-30T10:00:10Z,T01,1,auto,coder,7",
                "2026-03-30T10:00:11Z,T02,1,auto,test,0",
                "2026-03-30T10:00:12Z,T03,1,auto,lead,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manual_results.write_text(
        "\n".join(
            [
                json.dumps({"task_id": "T01", "coder_duration_s": 2, "prompt_tokens": 100}),
                json.dumps({"task_id": "T02", "prompt_tokens": 200}),
                json.dumps({"task_id": "T03", "coder_duration_s": 1, "prompt_tokens": 300}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_helper(
        project_dir,
        f"write_benchmark_report '{project_dir / 'auto'}' '{manual_results}' '{report_file}' 'T01,T02,T03' '4' '2'\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_file.read_text(encoding="utf-8"))
    auto_tasks = {task["task_id"]: task for task in report["auto"]["tasks"]}
    assert auto_tasks["T01"]["other_duration_s"] == 0.0
    assert report["manual"]["task_total_duration_s"] == 3.0
    assert report["comparison"]["auto_to_manual_ratio"] == 2.0
