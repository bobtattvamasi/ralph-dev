from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.bot_smoke_check as smoke
from scripts.ralph_common import (
    consume_control_comment,
    load_tasks_data,
    locked_path,
    save_tasks_data,
    write_control_data,
)


ROOT = Path(__file__).resolve().parent.parent
EXPLAIN_TASK = ROOT / "scripts" / "explain_task.py"
REOPEN_TASKS = ROOT / "scripts" / "reopen_tasks.py"
RALPH_COMMON = ROOT / "scripts" / "ralph_common.py"
UPDATE_TASK = ROOT / "scripts" / "update_task.py"
UPDATE_PROGRESS = ROOT / "scripts" / "update_progress.py"


def create_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    (project_dir / ".ralph" / "audit").mkdir(parents=True)
    (project_dir / "logs").mkdir()
    (project_dir / "tests").mkdir()
    (project_dir / "scripts").mkdir()
    (project_dir / "scripts" / "ralph_bot.py").write_text(
        "async def cmd_start_auto():\n    pass\n",
        encoding="utf-8",
    )
    (project_dir / "tasks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project": "test-project",
                "tasks": [
                    {
                        "id": "T01",
                        "phase": "R1",
                        "title": "Runnable task",
                        "description": "Use /audit and trust report docs.",
                        "status": "pending",
                        "target_files": ["test_file.py"],
                        "dependencies": [],
                    },
                    {
                        "id": "T02",
                        "phase": "R1",
                        "title": "Blocked task",
                        "description": "Depends on T99.",
                        "status": "pending",
                        "target_files": ["test_file.py"],
                        "dependencies": ["T99"],
                    },
                    {
                        "id": "T03",
                        "phase": "R1",
                        "title": "Completed task",
                        "description": "Ready to reopen.",
                        "status": "verified_done",
                        "dependencies": [],
                        "completed_at": "2026-03-18T00:00:00+00:00",
                        "revision_notes": "old note",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / ".ralph" / "audit" / "T01.json").write_text(
        json.dumps(
            {
                "task_id": "T01",
                "title": "Runnable task",
                "status": "done",
                "verification": {
                    "result": "pass",
                    "reason": "evidence exists",
                    "task_class": "docs-only",
                    "evidence_files": ["docs/TRUST_LAYER.md"],
                },
                "changes": {
                    "all": ["docs/TRUST_LAYER.md"],
                    "non_bookkeeping": ["docs/TRUST_LAYER.md"],
                },
                "review": {"raw": "", "parsed": {}},
                "attempts": 1,
                "duration_sec": 12,
                "timestamp": "2026-03-18T00:00:00+00:00",
                "runtime_success": True,
                "verified_success": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_dir


def test_explain_task_shows_runnable_summary(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    env = os.environ.copy()
    env["RALPH_PROJECT_DIR"] = str(project_dir)

    result = subprocess.run(
        ["python3", str(EXPLAIN_TASK), "T01"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Task: T01 — Runnable task" in result.stdout
    assert "Status: pending" in result.stdout
    assert "Runnable: yes" in result.stdout
    assert "Suggested next action: Run ./ralph.sh task T01" in result.stdout
    assert "Audit summary:" in result.stdout


def test_explain_task_shows_non_runnable_reason(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    env = os.environ.copy()
    env["RALPH_PROJECT_DIR"] = str(project_dir)

    result = subprocess.run(
        ["python3", str(EXPLAIN_TASK), "T02"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Runnable: no" in result.stdout
    assert "Why not runnable: unmet dependencies: T99" in result.stdout


def test_reopen_tasks_updates_status_and_notes(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)

    result = subprocess.run(
        [
            "python3",
            str(REOPEN_TASKS),
            "--task",
            "T03",
            "--to-status",
            "pending",
            "--note",
            "Manual review requested",
        ],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Updated T03: verified_done -> pending" in result.stdout
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    task = next(item for item in data["tasks"] if item["id"] == "T03")
    assert task["status"] == "pending"
    assert task["completed_at"] is None
    assert "old note" in task["revision_notes"]
    assert "Manual review requested" in task["revision_notes"]


def test_reopen_tasks_prefers_cwd_over_polluted_ralph_project_dir(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    polluted_root = tmp_path / "polluted"
    polluted_root.mkdir()
    (polluted_root / "tasks.json").write_text(
        json.dumps({"version": 1, "project": "polluted", "tasks": []}, indent=2) + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["RALPH_PROJECT_DIR"] = str(polluted_root)

    result = subprocess.run(
        [
            "python3",
            str(REOPEN_TASKS),
            "--task",
            "T03",
            "--to-status",
            "pending",
            "--note",
            "Manual review requested",
        ],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Updated T03: verified_done -> pending" in result.stdout
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    task = next(item for item in data["tasks"] if item["id"] == "T03")
    assert task["status"] == "pending"


def test_explain_task_prefers_cwd_over_polluted_ralph_project_dir(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    polluted_root = tmp_path / "polluted"
    polluted_root.mkdir()
    (polluted_root / "tasks.json").write_text(
        json.dumps(
            {"version": 1, "project": "polluted", "tasks": [{"id": "T01", "title": "Wrong task", "status": "done"}]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["RALPH_PROJECT_DIR"] = str(polluted_root)

    result = subprocess.run(
        ["python3", str(EXPLAIN_TASK), "T01"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Task: T01 — Runnable task" in result.stdout
    assert "Status: pending" in result.stdout


def test_bot_smoke_check_collects_help_output() -> None:
    fake_bot = SimpleNamespace()

    async def fake_cmd_help():
        await fake_bot.safe_send("🤖 <b>Ralph Bot</b>\n/trust_report")

    fake_bot.cmd_help = fake_cmd_help
    fake_bot.cmd_audit = fake_cmd_help
    fake_bot.cmd_audit_last = fake_cmd_help
    fake_bot.cmd_trust_report = fake_cmd_help
    fake_bot.safe_send = None
    fake_bot.send_split_message = None
    fake_bot.AUDIT_DIR = Path(".")

    chunks = asyncio.run(smoke.collect_command_output(fake_bot, "help", None, 10))

    assert chunks
    assert "Ralph Bot" in chunks[0]
    assert "/trust_report" in chunks[0]


def test_bot_smoke_check_reports_send_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    project_dir = create_project(tmp_path)

    async def fake_cmd_help():
        return None

    async def fake_send_message(_text: str):
        fake_bot.LAST_SEND_ERROR = {
            "command_name": "/help",
            "parse_mode": "HTML",
            "payload_length": 12,
            "error": "HTTPError: 400",
            "error_body": "Bad Request",
        }

    fake_bot = SimpleNamespace(
        TOKEN="token",
        CHAT_ID="chat",
        LAST_SEND_ERROR=None,
        AUDIT_DIR=project_dir / ".ralph" / "audit",
        cmd_help=fake_cmd_help,
        cmd_audit=fake_cmd_help,
        cmd_audit_last=fake_cmd_help,
        cmd_trust_report=fake_cmd_help,
        safe_send=None,
        send_split_message=None,
        send_message=fake_send_message,
        prepare_html_message=lambda text: text,
    )

    async def fake_collect(_bot, command, task_id, limit):  # noqa: ARG001
        return ["payload"]

    monkeypatch.setattr(smoke, "configure_bot", lambda _project_dir: fake_bot)
    monkeypatch.setattr(smoke, "collect_command_output", fake_collect)

    rc = asyncio.run(smoke.run_smoke(project_dir, "help", None, 10))
    captured = capsys.readouterr()

    assert rc == 1
    assert "fail: command=/help parse_mode=HTML length=12 reason=Bad Request" in captured.out


def test_bot_smoke_check_resolve_project_dir_prefers_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = create_project(tmp_path)
    polluted_root = tmp_path / "polluted"
    polluted_root.mkdir()
    (polluted_root / "tasks.json").write_text(
        json.dumps({"version": 1, "project": "polluted", "tasks": []}, indent=2) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("RALPH_PROJECT_DIR", str(polluted_root))
    monkeypatch.chdir(project_dir)

    assert smoke.resolve_project_dir() == project_dir


def test_shared_tasks_io_round_trips_validated_payload(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    data = load_tasks_data(project_dir)

    data["tasks"].append(
        {
            "id": "T04",
            "phase": "R1",
            "title": "New task",
            "description": "Shared save path",
            "status": "pending",
            "target_files": ["test_file.py"],
            "dependencies": [],
        }
    )
    save_tasks_data(project_dir, data)

    reloaded = load_tasks_data(project_dir)
    assert [task["id"] for task in reloaded["tasks"]] == ["T01", "T02", "T03", "T04"]


def test_shared_control_io_normalizes_and_consumes_comment(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)

    write_control_data(project_dir, "comment", "Operator note")
    control = json.loads((project_dir / "ralph_control.json").read_text(encoding="utf-8"))

    assert control["action"] == "comment"
    assert control["comment"] == "Operator note"
    assert "timestamp" in control
    assert consume_control_comment(project_dir) == "Operator note"

    cleared = json.loads((project_dir / "ralph_control.json").read_text(encoding="utf-8"))
    assert cleared["action"] == "comment"
    assert cleared["comment"] == ""


def test_control_write_waits_for_lock(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    control_path = project_dir / "ralph_control.json"

    with locked_path(control_path):
        proc = subprocess.Popen(
            [
                sys.executable,
                str(RALPH_COMMON),
                "control-write",
                "pause",
                "Operator note",
                "--project-dir",
                str(project_dir),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.2)
        assert not control_path.exists()

    stdout, stderr = proc.communicate(timeout=5)
    assert proc.returncode == 0, stdout + stderr
    control = json.loads(control_path.read_text(encoding="utf-8"))
    assert control["action"] == "pause"
    assert control["comment"] == "Operator note"


def test_state_write_waits_for_lock_and_replaces_atomically(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    state_path = project_dir / "ralph_state.json"
    state_path.write_text('{"status":"idle"}\n', encoding="utf-8")

    with locked_path(state_path):
        proc = subprocess.Popen(
            [
                sys.executable,
                str(RALPH_COMMON),
                "state-write",
                "running",
                "T01",
                "coder",
                "Locked write",
                "--project-dir",
                str(project_dir),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.2)
        assert json.loads(state_path.read_text(encoding="utf-8")) == {"status": "idle"}

    stdout, stderr = proc.communicate(timeout=5)
    assert proc.returncode == 0, stdout + stderr
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "running"
    assert state["current_task"] == "T01"
    assert state["current_phase_step"] == "coder"
    assert state["message"] == "Locked write"


def test_update_task_preserves_concurrent_task_status_changes(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    env = {**os.environ, "RALPH_PROJECT_DIR": str(project_dir), "PYTHONPATH": str(ROOT)}
    slow_update = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from scripts.ralph_common import mutate_tasks_data\n"
        "project_dir = Path(sys.argv[1])\n"
        "task_id = sys.argv[2]\n"
        "status = sys.argv[3]\n"
        "def apply(data):\n"
        "    for task in data['tasks']:\n"
        "        if task['id'] == task_id:\n"
        "            time.sleep(0.3)\n"
        "            task['status'] = status\n"
        "            return\n"
        "    raise SystemExit(f'missing task {task_id}')\n"
        "mutate_tasks_data(project_dir, apply)\n"
    )
    slow_proc = subprocess.Popen(
        [sys.executable, "-c", slow_update, str(project_dir), "T01", "done"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.05)
    fast_result = subprocess.run(
        [sys.executable, str(UPDATE_TASK), "T02", "blocked", "Concurrent update"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    slow_stdout, slow_stderr = slow_proc.communicate(timeout=5)

    assert slow_proc.returncode == 0, slow_stdout + slow_stderr
    assert fast_result.returncode == 0, fast_result.stdout + fast_result.stderr

    tasks = {task["id"]: task for task in load_tasks_data(project_dir)["tasks"]}
    assert tasks["T01"]["status"] == "done"
    assert tasks["T02"]["status"] == "blocked"
    assert tasks["T02"]["revision_notes"] == "Concurrent update"


def test_update_progress_serializes_concurrent_appends(tmp_path: Path) -> None:
    project_dir = create_project(tmp_path)
    (project_dir / "progress.md").write_text("# Progress\n", encoding="utf-8")
    env = {**os.environ, "RALPH_PROJECT_DIR": str(project_dir)}

    proc_a = subprocess.Popen(
        [sys.executable, str(UPDATE_PROGRESS), "T01", "First note"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    proc_b = subprocess.Popen(
        [sys.executable, str(UPDATE_PROGRESS), "T02", "Second note"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_a, stderr_a = proc_a.communicate(timeout=5)
    stdout_b, stderr_b = proc_b.communicate(timeout=5)

    assert proc_a.returncode == 0, stdout_a + stderr_a
    assert proc_b.returncode == 0, stdout_b + stderr_b

    progress = (project_dir / "progress.md").read_text(encoding="utf-8")
    assert progress.count("**T01**") == 1
    assert progress.count("**T02**") == 1
    assert "First note" in progress
    assert "Second note" in progress
