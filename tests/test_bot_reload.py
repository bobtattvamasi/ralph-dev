"""Tests for bot hot-reload behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

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
