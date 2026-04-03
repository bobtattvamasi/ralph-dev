from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import AsyncMock, call, patch

import pytest

import scripts.ralph_bot as bot


@pytest.fixture
def bot_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "logs").mkdir()
    (project_dir / "scripts").mkdir()
    (project_dir / "tasks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project": "test-project",
                "tasks": [
                    {
                        "id": "T01",
                        "phase": "R1",
                        "title": "Test task",
                        "description": "Test task",
                        "status": "pending",
                        "target_files": ["test_file.py"],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / "scripts" / "ralph_bot.py").write_text(
        "def cmd_ask(prompt: str) -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )
    (project_dir / "ralph.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(bot, "PROJECT_DIR", project_dir)
    monkeypatch.setattr(bot, "STATE_FILE", project_dir / "ralph_state.json")
    monkeypatch.setattr(bot, "CONTROL_FILE", project_dir / "ralph_control.json")
    monkeypatch.setattr(bot, "TASKS_FILE", project_dir / "tasks.json")
    monkeypatch.setattr(bot, "PROGRESS_FILE", project_dir / "progress.md")
    monkeypatch.setattr(bot, "LOG_DIR", project_dir / "logs")
    monkeypatch.setattr(bot, "BLOG_DRAFTS_FILE", project_dir / "BLOG_DRAFTS.md")
    monkeypatch.setattr(bot, "RALPH_MAIN_PID_FILE", project_dir / "ralph_main.pid")

    safe_send_mock = AsyncMock()
    send_message_mock = AsyncMock()
    monkeypatch.setattr(bot, "safe_send", safe_send_mock)
    monkeypatch.setattr(bot, "send_message", send_message_mock)

    return {
        "project_dir": project_dir,
        "control_file": project_dir / "ralph_control.json",
        "safe_send": safe_send_mock,
        "send_message": send_message_mock,
    }


@pytest.mark.asyncio
async def test_cmd_help_sends_command_list(bot_env: dict[str, object]) -> None:
    await bot.cmd_help()

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once()
    message = safe_send.await_args.args[0]
    assert "/help" not in message or "Ralph Bot" in message
    assert "/article [new]" in message
    assert "/timeout [seconds]" in message
    assert "/done [task_id]" in message
    assert "/audit &lt;task_id&gt;" in message
    assert "/ask &lt;question&gt;" in message


@pytest.mark.asyncio
async def test_cmd_ask_without_input_returns_usage(bot_env: dict[str, object]) -> None:
    await bot.cmd_ask("   ")

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with(bot.ASK_USAGE_TEXT)


@pytest.mark.asyncio
async def test_cmd_ask_uses_llm_provider_query_and_streams_chunks(
    bot_env: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send_split_mock = AsyncMock()
    monkeypatch.setattr(bot, "send_split_message", send_split_mock)

    captured: dict[str, str] = {}

    class FakeProvider:
        def __init__(self) -> None:
            self.backend_name = "repo_local"

        async def query(self, question: str, context: str) -> list[str]:
            captured["question"] = question
            captured["context"] = context
            return ["chunk one", "chunk two"]

    monkeypatch.setattr(bot, "LLMProvider", FakeProvider)

    await bot.cmd_ask("what is Ralph doing now?")

    assert captured["question"] == "what is Ralph doing now?"
    assert "tasks.json (task truth):" in captured["context"]
    assert "project state:" in captured["context"]
    send_split_mock.assert_has_awaits([call("chunk one"), call("chunk two")])


def test_build_ask_project_context_injects_tasks_state_logs_and_code(
    bot_env: dict[str, object],
) -> None:
    project_dir = bot_env["project_dir"]
    bot.STATE_FILE.write_text(
        json.dumps({"status": "running", "current_task": "T01", "current_phase_step": "coder"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "logs" / "ralph_20260330.log").write_text(
        "first line\nsecond line\nthird line\n",
        encoding="utf-8",
    )

    context = bot.build_ask_project_context()

    assert "project state:" in context
    assert '"current_task": "T01"' in context
    assert "tasks.json (task truth):" in context
    assert '"id": "T01"' in context
    assert "recent logs:" in context
    assert "second line" in context
    assert "relevant code snippets:" in context
    assert f"File: {bot.PROJECT_DIR / 'scripts' / 'ralph_bot.py'}" in context
    assert "progress.md is narrative-only context" in context


@pytest.mark.asyncio
async def test_llm_provider_codex_query_builds_prompt_with_injected_context(
    bot_env: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen_calls: list[dict[str, object]] = []

    class FakeStdout:
        def __init__(self, lines: list[str]) -> None:
            self._lines = iter(lines)

        def readline(self) -> str:
            return next(self._lines, "")

    class FakePopen:
        def __init__(self, command: list[str], **kwargs: object) -> None:
            popen_calls.append({"command": command, "kwargs": kwargs})
            self.stdout = FakeStdout(["Ralph status looks healthy.\n", "Current task is idle.\n"])

        def wait(self) -> int:
            return 0

        def kill(self) -> None:
            raise AssertionError("kill() should not be called in success path")

    monkeypatch.setattr(bot.subprocess, "Popen", FakePopen)

    provider = bot.LLMProvider("codex")
    chunks = await provider.query("what is Ralph doing now?", "tasks.json (task truth):\nT01\nrecent logs:\nOK")

    assert chunks == ["Ralph status looks healthy.\nCurrent task is idle."]
    assert popen_calls
    call = popen_calls[0]
    assert call["kwargs"]["cwd"] == str(bot.PROJECT_DIR)
    command = call["command"]
    assert command[:4] == ["codex", "exec", "-s", "danger-full-access"]
    prompt = command[-1]
    assert "Operator question:\nwhat is Ralph doing now?" in prompt
    assert "tasks.json (task truth):\nT01" in prompt
    assert "recent logs:\nOK" in prompt
    assert "progress.md is narrative-only context" not in prompt


def test_get_ask_backend_defaults_to_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(bot.ASK_BACKEND_ENV, raising=False)

    backend = bot.get_ask_backend()

    assert backend["name"] == "codex_cli"


def test_get_ask_backend_can_switch_to_repo_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(bot.ASK_BACKEND_ENV, "repo_local")

    backend = bot.get_ask_backend()

    assert backend["name"] == "repo_local_single_shot"


@pytest.mark.asyncio
async def test_cmd_timeout_writes_control_file(bot_env: dict[str, object]) -> None:
    await bot.cmd_timeout("60")

    control_file = bot_env["control_file"]
    assert control_file.exists()
    payload = json.loads(control_file.read_text(encoding="utf-8"))
    assert payload["action"] == "timeout"
    assert payload["comment"] == "60"

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with("⏱ Timeout override set to 60s for the next task step")


@pytest.mark.asyncio
async def test_cmd_pause_writes_pause_action(bot_env: dict[str, object]) -> None:
    await bot.cmd_pause()

    control_file = bot_env["control_file"]
    payload = json.loads(control_file.read_text(encoding="utf-8"))
    assert payload["action"] == "pause"
    assert payload["comment"] == ""

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with("⏸ Ralph paused (will wait before next step)")


@pytest.mark.asyncio
async def test_cmd_resume_writes_continue_action(bot_env: dict[str, object]) -> None:
    await bot.cmd_resume()

    control_file = bot_env["control_file"]
    payload = json.loads(control_file.read_text(encoding="utf-8"))
    assert payload["action"] == "continue"
    assert payload["comment"] == ""

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with("▶️ Ralph resumed")


@pytest.mark.asyncio
async def test_cmd_done_marks_task_done(bot_env: dict[str, object]) -> None:
    with patch("scripts.ralph_bot.subprocess.run") as run_mock:
        await bot.cmd_done("T01")

    run_mock.assert_called_once_with(
        ["python3", "scripts/update_task.py", "T01", "done", "Done via Telegram"],
        cwd=str(bot.PROJECT_DIR),
        check=True,
        capture_output=True,
        text=True,
    )
    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with("✅ Task T01 marked done")


@pytest.mark.asyncio
async def test_cmd_progress_shows_phase_bars(bot_env: dict[str, object]) -> None:
    bot.TASKS_FILE.write_text(
        json.dumps(
            {
                "version": 1,
                "project": "test-project",
                "phases": {
                    "R0": {"name": "Foundation"},
                    "R1": {"name": "Reliability"},
                    "R2": {"name": "Convenience"},
                },
                "tasks": [
                    {"id": "R0-01", "phase": "R0", "title": "Init", "status": "done"},
                    {"id": "R1-01", "phase": "R1", "title": "Retry", "status": "done"},
                    {"id": "R1-02", "phase": "R1", "title": "Watchdog", "status": "pending", "target_files": ["test_file.py"]},
                    {
                        "id": "R2-01",
                        "phase": "R2",
                        "title": "Plan",
                        "status": "pending",
                        "target_files": ["test_file.py"],
                        "dependencies": ["R1-02"],
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    await bot.cmd_progress()

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once()
    message = safe_send.await_args.args[0]
    assert "📊 Ralph Progress" in message
    assert "████" in message
    assert "2/4 done (50%)" in message
    assert "R0" in message and "Foundation" in message
    assert "⏳ Blocked: R2-01" in message
    assert "🔜 Next: R1-02" in message


def test_get_tasks_summary_counts_verified_done_and_keeps_dependency_hints(
    bot_env: dict[str, object],
) -> None:
    bot.TASKS_FILE.write_text(
        json.dumps(
            {
                "version": 1,
                "project": "test-project",
                "tasks": [
                    {"id": "T01", "phase": "R1", "title": "Verified", "status": "verified_done"},
                    {"id": "T02", "phase": "R1", "title": "Done", "status": "done"},
                    {"id": "T03", "phase": "R1", "title": "Free pending", "status": "pending", "target_files": ["test_file.py"]},
                    {
                        "id": "T04",
                        "phase": "R1",
                        "title": "Depends on verified",
                        "status": "pending",
                        "target_files": ["test_file.py"],
                        "dependencies": ["T01"],
                    },
                    {
                        "id": "T05",
                        "phase": "R1",
                        "title": "Depends on false positive",
                        "status": "pending",
                        "target_files": ["test_file.py"],
                        "dependencies": ["T06"],
                    },
                    {"id": "T06", "phase": "R1", "title": "False positive", "status": "false_positive"},
                    {"id": "T07", "phase": "R1", "title": "Blocked task", "status": "blocked"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    message = bot.get_tasks_summary()

    assert "📊 Tasks: 2/7 done" in message
    assert "T04" in message
    assert "Depends on verified" in message
    assert "T04 [medium] Depends on verified" in message
    assert "needs T01" not in message
    assert "T05 [medium] Depends on false positive ⛔ needs T06" in message
    assert "T07" not in message


@pytest.mark.asyncio
async def test_handle_update_routes_tasks_with_trust_aware_counts(bot_env: dict[str, object]) -> None:
    bot.TASKS_FILE.write_text(
        json.dumps(
            {
                "version": 1,
                "project": "test-project",
                "tasks": [
                    {"id": "T01", "phase": "R1", "title": "Verified", "status": "verified_done"},
                    {"id": "T02", "phase": "R1", "title": "Todo", "status": "pending", "target_files": ["test_file.py"], "dependencies": ["T01"]},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    await bot.handle_update({"message": {"text": "/tasks"}})

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once()
    message = safe_send.await_args.args[0]
    assert "📊 Tasks: 1/2 done" in message
    assert "needs T01" not in message


@pytest.mark.asyncio
async def test_handle_update_routes_help(bot_env: dict[str, object]) -> None:
    await bot.handle_update({"message": {"text": "/help"}})

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once()
    message = safe_send.await_args.args[0]
    assert "/pause" in message
    assert "/resume" in message


@pytest.mark.asyncio
async def test_handle_update_routes_timeout(bot_env: dict[str, object]) -> None:
    await bot.handle_update({"message": {"text": "/timeout 60"}})

    control_file = bot_env["control_file"]
    payload = json.loads(control_file.read_text(encoding="utf-8"))
    assert payload["action"] == "timeout"
    assert payload["comment"] == "60"


@pytest.mark.asyncio
async def test_handle_update_routes_ask(bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    ask_mock = AsyncMock()
    monkeypatch.setattr(bot, "cmd_ask", ask_mock)

    await bot.handle_update({"message": {"text": "/ask what is Ralph doing now?"}})

    ask_mock.assert_awaited_once_with("what is Ralph doing now?")


@pytest.mark.asyncio
async def test_handle_update_routes_empty_ask_to_usage(bot_env: dict[str, object]) -> None:
    await bot.handle_update({"message": {"text": "/ask   "}})

    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with(bot.ASK_USAGE_TEXT)


@pytest.mark.asyncio
async def test_cmd_audit_returns_summary(bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    split_send = AsyncMock()
    monkeypatch.setattr(bot, "send_split_message", split_send)
    monkeypatch.setattr(bot, "get_audit_summary", lambda task_id: f"Audit: {task_id} — done")

    await bot.cmd_audit("T01")

    split_send.assert_awaited_once_with("Audit: T01 — done")


@pytest.mark.asyncio
async def test_handle_update_routes_audit(bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    split_send = AsyncMock()
    monkeypatch.setattr(bot, "send_split_message", split_send)
    monkeypatch.setattr(bot, "get_audit_summary", lambda task_id: f"Audit: {task_id} — done")

    await bot.handle_update({"message": {"text": "/audit T01"}})

    split_send.assert_awaited_once_with("Audit: T01 — done")


@pytest.mark.asyncio
async def test_cmd_audit_last_returns_summary(bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    split_send = AsyncMock()
    monkeypatch.setattr(bot, "send_split_message", split_send)
    monkeypatch.setattr(bot, "get_audit_last_summary", lambda limit=10: f"=== Last {limit} audit tasks ===")

    await bot.cmd_audit_last("5")

    split_send.assert_awaited_once_with("=== Last 5 audit tasks ===")


@pytest.mark.asyncio
async def test_handle_update_routes_audit_last(bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    split_send = AsyncMock()
    monkeypatch.setattr(bot, "send_split_message", split_send)
    monkeypatch.setattr(bot, "get_audit_last_summary", lambda limit=10: f"=== Last {limit} audit tasks ===")

    await bot.handle_update({"message": {"text": "/audit_last 3"}})

    split_send.assert_awaited_once_with("=== Last 3 audit tasks ===")


@pytest.mark.asyncio
async def test_handle_update_routes_trust_report(bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    split_send = AsyncMock()
    monkeypatch.setattr(bot, "send_split_message", split_send)
    monkeypatch.setattr(bot, "get_trust_report_summary", lambda: "=== Trust Report ===")

    await bot.handle_update({"message": {"text": "/trust_report"}})

    split_send.assert_awaited_once_with("=== Trust Report ===")


@pytest.mark.asyncio
async def test_send_message_logs_diagnostics_on_http_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bot.API = "https://api.telegram.org/botTEST"
    bot.CHAT_ID = "123"
    bot.set_send_context("/help")

    def failing_urlopen(_req, timeout=10):  # noqa: ARG001
        raise HTTPError(
            url=bot.API + "/sendMessage",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=BytesIO(b"{\"ok\":false,\"description\":\"Bad Request: can't parse entities\"}"),
        )

    monkeypatch.setattr("urllib.request.urlopen", failing_urlopen)

    await bot.send_message("broken <payload>")

    captured = capsys.readouterr()
    assert "command=/help" in captured.err
    assert "parse_mode=HTML" in captured.err
    assert "payload_length=" in captured.err
    assert "payload_preview=broken <payload>" in captured.err
    assert "can't parse entities" in captured.err


@pytest.mark.asyncio
async def test_watch_state_recovers_crashed_running_task(
    bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    bot.STATE_FILE.write_text(
        json.dumps(
            {
                "status": "running",
                "current_task": "T01",
                "last_update": "2026-03-13T00:00:00+00:00",
                "message": "Coder implementing...",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    class CrashedProcess:
        returncode = 1

        def poll(self) -> int:
            return 1

    crashed_process = CrashedProcess()
    monkeypatch.setattr(bot, "ralph_process", crashed_process)
    monkeypatch.setattr(bot.RUNTIME, "ralph_process", crashed_process)
    monkeypatch.setattr(bot, "caffeinate_process", None)
    monkeypatch.setattr(bot.RUNTIME, "caffeinate_process", None)

    sleep_calls = {"count": 0}

    async def fake_sleep(_seconds: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(bot.asyncio, "sleep", fake_sleep)

    with patch("scripts.ralph_bot.subprocess.run") as run_mock:
        with pytest.raises(asyncio.CancelledError):
            await bot.watch_state()

    called_commands = [call.args[0] for call in run_mock.call_args_list]
    assert ["python3", "scripts/update_task.py", "T01", "pending"] in called_commands
    assert ["git", "-C", str(bot.PROJECT_DIR), "reset", "HEAD", "--", "."] not in called_commands
    assert ["git", "-C", str(bot.PROJECT_DIR), "checkout", "--", "."] not in called_commands

    safe_send = bot_env["safe_send"]
    messages = [call.args[0] for call in safe_send.await_args_list]
    assert any(
        "🔄 Ralph crashed during T01. Task reset to pending. Worktree rollback skipped by policy." in msg
        for msg in messages
    )


@pytest.mark.asyncio
async def test_cmd_start_auto_rejects_when_state_running(bot_env: dict[str, object]) -> None:
    bot.STATE_FILE.write_text(
        json.dumps(
            {
                "status": "running",
                "current_task": "T01",
                "current_phase_step": "coder",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    with patch("scripts.ralph_bot.reset_stale_state") as reset_mock:
        with patch("scripts.ralph_bot.subprocess.Popen") as popen_mock:
            await bot.cmd_start_auto()

    reset_mock.assert_called_once()
    popen_mock.assert_not_called()
    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with("⚠️ Ralph already running. /stop first.")


@pytest.mark.asyncio
async def test_cmd_start_auto_rejects_when_pid_file_is_alive(
    bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    bot.RALPH_MAIN_PID_FILE.write_text("4242\n", encoding="utf-8")

    monkeypatch.setattr(bot, "is_pid_alive", lambda pid: int(pid) == 4242)

    with patch("scripts.ralph_bot.reset_stale_state") as reset_mock:
        with patch("scripts.ralph_bot.subprocess.Popen") as popen_mock:
            await bot.cmd_start_auto()

    reset_mock.assert_called_once()
    popen_mock.assert_not_called()
    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with("⚠️ Ralph уже работает (PID: 4242). Используй /stop сначала.")


@pytest.mark.asyncio
async def test_cmd_start_auto_ignores_stale_pid_file(
    bot_env: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    bot.RALPH_MAIN_PID_FILE.write_text("4242\n", encoding="utf-8")

    monkeypatch.setattr(bot, "is_pid_alive", lambda _pid: False)

    process = AsyncMock()
    process.pid = 7777
    with patch("scripts.ralph_bot.reset_stale_state") as reset_mock:
        with patch("scripts.ralph_bot.subprocess.Popen", return_value=process) as popen_mock:
            await bot.cmd_start_auto()

    reset_mock.assert_called_once()
    assert popen_mock.call_count == 2
    assert popen_mock.call_args_list[1].args[0] == [str(bot.RALPH_DIR / "ralph.sh"), "auto"]
    assert not bot.RALPH_MAIN_PID_FILE.exists()
    safe_send = bot_env["safe_send"]
    safe_send.assert_awaited_once_with("🚀 Auto mode started\nPID: 7777")


def test_read_state_returns_idle_for_broken_json(bot_env: dict[str, object]) -> None:
    bot.STATE_FILE.write_text("{broken json", encoding="utf-8")

    state = bot.read_state()

    assert state["status"] == "idle"
    assert state["current_task"] is None
