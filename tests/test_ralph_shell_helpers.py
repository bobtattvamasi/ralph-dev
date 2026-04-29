from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


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
                        "acceptance_criteria": ["test_auto_route covers /auto"],
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

    for script_name in ("extract_json.py", "ralph_common.py"):
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
    assert status_ok.stdout.strip() == "status-ok"


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
