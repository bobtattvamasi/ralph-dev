from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import scripts.ralph_bot as bot


@pytest.fixture
def bot_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "logs").mkdir()
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
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(bot, "PROJECT_DIR", project_dir)
    monkeypatch.setattr(bot, "STATE_FILE", project_dir / "ralph_state.json")
    monkeypatch.setattr(bot, "CONTROL_FILE", project_dir / "ralph_control.json")
    monkeypatch.setattr(bot, "TASKS_FILE", project_dir / "tasks.json")
    monkeypatch.setattr(bot, "PROGRESS_FILE", project_dir / "progress.md")
    monkeypatch.setattr(bot, "LOG_DIR", project_dir / "logs")
    monkeypatch.setattr(bot, "BLOG_DRAFTS_FILE", project_dir / "BLOG_DRAFTS.md")

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
    assert ["git", "-C", str(bot.PROJECT_DIR), "reset", "HEAD", "--", "."] in called_commands
    assert ["git", "-C", str(bot.PROJECT_DIR), "checkout", "--", "."] in called_commands

    safe_send = bot_env["safe_send"]
    messages = [call.args[0] for call in safe_send.await_args_list]
    assert any("🔄 Ralph crashed during T01. Task reset to pending, changes rolled back." in msg for msg in messages)


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


def test_read_state_returns_idle_for_broken_json(bot_env: dict[str, object]) -> None:
    bot.STATE_FILE.write_text("{broken json", encoding="utf-8")

    state = bot.read_state()

    assert state["status"] == "idle"
    assert state["current_task"] is None
