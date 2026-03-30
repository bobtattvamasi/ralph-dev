"""Tests for bot hot-reload behavior."""

from __future__ import annotations

import importlib.util
import json
import urllib.request
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest


def load_bot_module() -> ModuleType:
    """Import scripts/ralph_bot.py for direct unit testing."""
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "ralph_bot.py"
    spec = importlib.util.spec_from_file_location("ralph_bot_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_reload_module(bot_module: ModuleType, replacement) -> ModuleType:
    """Create a module object with all reload exports populated."""
    module = ModuleType("ralph_bot_reload_fixture")
    for name in bot_module.HOT_RELOAD_EXPORTS:
        setattr(module, name, getattr(bot_module, name))
    module.cmd_help = replacement
    return module


def test_apply_hot_reload_swaps_handlers():
    bot = load_bot_module()

    async def replacement():
        return "reloaded"

    reloaded = build_reload_module(bot, replacement)

    bot.apply_hot_reload(reloaded)

    assert bot.cmd_help is replacement


def test_apply_hot_reload_rejects_incomplete_module():
    bot = load_bot_module()
    original = bot.cmd_help
    incomplete = ModuleType("broken_reload_module")

    with pytest.raises(RuntimeError, match="missing exports"):
        bot.apply_hot_reload(incomplete)

    assert bot.cmd_help is original


@pytest.mark.asyncio
async def test_cmd_reload_reports_failure_and_keeps_existing_handlers(monkeypatch):
    bot = load_bot_module()
    messages: list[str] = []
    original = bot.cmd_help

    async def fake_safe_send(text: str, reply_markup=None) -> None:
        messages.append(text)

    def broken_loader():
        raise RuntimeError("boom <bad>")

    monkeypatch.setattr(bot, "safe_send", fake_safe_send)
    monkeypatch.setattr(bot, "load_bot_module_from_source", broken_loader)

    await bot.cmd_reload()

    assert messages == ["❌ Reload failed: boom &lt;bad&gt;"]
    assert bot.cmd_help is original


@pytest.mark.asyncio
async def test_handle_update_dispatches_reload(monkeypatch):
    bot = load_bot_module()
    called: list[str] = []

    async def fake_reload() -> None:
        called.append("reload")

    monkeypatch.setattr(bot, "cmd_reload", fake_reload)

    await bot.handle_update({"message": {"text": "/reload"}})

    assert called == ["reload"]


@pytest.mark.asyncio
async def test_handle_update_dispatches_exit(monkeypatch):
    bot = load_bot_module()
    called: list[str] = []

    async def fake_exit() -> None:
        called.append("exit")

    monkeypatch.setattr(bot, "cmd_exit", fake_exit)

    await bot.handle_update({"message": {"text": "/exit", "from": {"id": 123}}})

    assert called == ["exit"]


@pytest.mark.asyncio
async def test_handle_update_logs_command_entry_exit_and_send_count(
    monkeypatch, capsys: pytest.CaptureFixture[str]
):
    bot = load_bot_module()
    send_message_mock = AsyncMock()

    async def fake_cmd_status() -> None:
        await bot.safe_send("first")
        await bot.safe_send("second")

    monkeypatch.setattr(bot, "send_message", send_message_mock)
    monkeypatch.setattr(bot, "cmd_status", fake_cmd_status)

    await bot.handle_update({"message": {"text": "/status", "from": {"id": 123}}})

    captured = capsys.readouterr()
    assert "[bot] CMD: /status from user_123" in captured.err
    assert "[bot] Handler: cmd_status START" in captured.err
    assert "[bot] Handler: cmd_status END (took " in captured.err
    assert "sent 2 messages" in captured.err
    assert send_message_mock.await_count == 2


@pytest.mark.asyncio
async def test_handle_update_logs_exception_with_traceback(
    monkeypatch, capsys: pytest.CaptureFixture[str]
):
    bot = load_bot_module()

    async def fake_cmd_status() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(bot, "cmd_status", fake_cmd_status)

    with pytest.raises(RuntimeError, match="boom"):
        await bot.handle_update({"message": {"text": "/status", "from": {"id": 123}}})

    captured = capsys.readouterr()
    assert "[bot] CMD: /status from user_123" in captured.err
    assert "[bot] Handler: cmd_status START" in captured.err
    assert "[bot] Handler: cmd_status ERROR (took " in captured.err
    assert "[bot] Exception in cmd_status: RuntimeError: boom" in captured.err
    assert "Traceback (most recent call last):" in captured.err


@pytest.mark.asyncio
async def test_poll_updates_logs_traceback_for_update_handler_errors(
    monkeypatch, capsys: pytest.CaptureFixture[str]
):
    bot = load_bot_module()

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps({"result": [{"update_id": 1, "message": {"text": "/status"}}]}).encode("utf-8")

    responses = iter([FakeResponse(), asyncio.CancelledError()])

    def fake_urlopen(url: str, timeout: int = 35):
        response = next(responses)
        if isinstance(response, BaseException):
            raise response
        return response

    async def fake_handle_update(update: dict) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(bot, "handle_update", fake_handle_update)

    with pytest.raises(asyncio.CancelledError):
        await bot.poll_updates()

    captured = capsys.readouterr()
    assert "[bot] Handler error: boom" in captured.err
    assert "Traceback (most recent call last):" in captured.err
