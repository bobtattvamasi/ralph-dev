"""Tests for bot metrics aggregation and /stats command."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def load_bot_module() -> ModuleType:
    """Import scripts/ralph_bot.py for direct unit testing."""
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "ralph_bot.py"
    spec = importlib.util.spec_from_file_location("ralph_bot_stats_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summarize_metrics_aggregates_expected_fields():
    bot = load_bot_module()
    rows = [
        {
            "status": "success",
            "duration_s": "10",
            "attempts": "1",
            "files_changed": "2",
            "cost_est": "0.03",
        },
        {
            "status": "failed",
            "duration_s": "20",
            "attempts": "3",
            "files_changed": "5",
            "cost_est": "0.09",
        },
    ]

    summary = bot.summarize_metrics(rows)

    assert summary == {
        "total_tasks": 2,
        "success_count": 1,
        "failed_count": 1,
        "avg_duration": 15.0,
        "avg_attempts": 2.0,
        "avg_files_changed": 3.5,
        "total_cost": 0.12,
    }


@pytest.mark.asyncio
async def test_cmd_stats_reports_aggregated_metrics(tmp_path, monkeypatch):
    bot = load_bot_module()
    bot.LOG_DIR = tmp_path / "logs"
    bot.LOG_DIR.mkdir()
    (bot.LOG_DIR / "metrics.csv").write_text(
        "\n".join(
            [
                "timestamp,task_id,status,duration_s,attempts,files_changed,quality,cost_est",
                "2026-03-12T17:31:02Z,R2-08,success,100,1,2,?,0.10",
                "2026-03-12T17:40:02Z,R2-09,failed,200,3,4,?,0.20",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    messages: list[str] = []

    async def fake_safe_send(text: str, reply_markup=None) -> None:
        messages.append(text)

    monkeypatch.setattr(bot, "safe_send", fake_safe_send)

    await bot.cmd_stats()

    assert messages == [
        "📊 <b>Ralph Stats</b>\n"
        "Всего задач: 2\n"
        "Успешных: 1\n"
        "Проваленных: 1\n"
        "Средняя длительность: 150.0s\n"
        "Среднее число попыток: 2.0\n"
        "Среднее число измененных файлов: 3.0\n"
        "Оценка стоимости: $0.30"
    ]


@pytest.mark.asyncio
async def test_cmd_stats_handles_missing_metrics_file(tmp_path, monkeypatch):
    bot = load_bot_module()
    bot.LOG_DIR = tmp_path / "logs"
    bot.LOG_DIR.mkdir()
    messages: list[str] = []

    async def fake_safe_send(text: str, reply_markup=None) -> None:
        messages.append(text)

    monkeypatch.setattr(bot, "safe_send", fake_safe_send)

    await bot.cmd_stats()

    assert messages == ["📊 No metrics available yet. Run some tasks!"]
