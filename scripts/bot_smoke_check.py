#!/usr/bin/env python3
"""Minimal smoke check for live Telegram command transport."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def configure_bot(project_dir: Path):
    import scripts.ralph_bot as bot

    bot.PROJECT_DIR = project_dir
    bot.STATE_FILE = project_dir / "ralph_state.json"
    bot.CONTROL_FILE = project_dir / "ralph_control.json"
    bot.TASKS_FILE = project_dir / "tasks.json"
    bot.PROGRESS_FILE = project_dir / "progress.md"
    bot.LOG_DIR = project_dir / "logs"
    bot.AUDIT_DIR = project_dir / ".ralph" / "audit"
    bot.BLOG_DRAFTS_FILE = project_dir / "BLOG_DRAFTS.md"
    bot.RALPH_MAIN_PID_FILE = project_dir / "ralph_main.pid"
    load_dotenv(project_dir / ".env")
    bot.TOKEN = os.environ.get("RALPH_TELEGRAM_TOKEN", "")
    bot.CHAT_ID = os.environ.get("RALPH_TELEGRAM_CHAT_ID", "")
    bot.API = f"https://api.telegram.org/bot{bot.TOKEN}"
    return bot


async def collect_command_output(bot, command: str, task_id: str | None, limit: int) -> list[str]:
    chunks: list[str] = []

    async def capture_safe_send(text: str, reply_markup=None) -> None:
        del reply_markup
        chunks.append(text)

    async def capture_split_send(text: str) -> None:
        chunks.append(text)

    original_safe_send = bot.safe_send
    original_split = bot.send_split_message
    bot.safe_send = capture_safe_send
    bot.send_split_message = capture_split_send
    try:
        if command == "help":
            await bot.cmd_help()
        elif command == "audit":
            resolved_task = task_id
            if not resolved_task:
                latest = sorted(bot.AUDIT_DIR.glob("*.json"))
                if not latest:
                    raise RuntimeError("No audit artifacts found; pass --task for audit smoke check")
                resolved_task = latest[-1].stem
            await bot.cmd_audit(resolved_task)
        elif command == "audit_last":
            await bot.cmd_audit_last(str(limit))
        elif command == "trust_report":
            await bot.cmd_trust_report()
        else:
            raise RuntimeError(f"Unsupported command: {command}")
    finally:
        bot.safe_send = original_safe_send
        bot.send_split_message = original_split
    return chunks


async def run_smoke(project_dir: Path, command: str, task_id: str | None, limit: int) -> int:
    bot = configure_bot(project_dir)
    if not bot.TOKEN or not bot.CHAT_ID:
        print("fail: missing RALPH_TELEGRAM_TOKEN or RALPH_TELEGRAM_CHAT_ID")
        return 1

    try:
        chunks = await collect_command_output(bot, command, task_id, limit)
    except Exception as exc:  # noqa: BLE001
        print(f"fail: command rendering error: {exc}")
        return 1

    if not chunks:
        print("fail: command produced empty output")
        return 1

    for chunk in chunks:
        bot.LAST_SEND_ERROR = None
        await bot.send_message(bot.prepare_html_message(chunk))
        if bot.LAST_SEND_ERROR:
            err = bot.LAST_SEND_ERROR
            print(
                "fail: "
                f"command={err.get('command_name', 'unknown')} "
                f"parse_mode={err.get('parse_mode', '')} "
                f"length={err.get('payload_length', 0)} "
                f"reason={err.get('error_body') or err.get('error')}"
            )
            return 1

    print(f"ok: command={command} chunks={len(chunks)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check Telegram transport for bot commands")
    parser.add_argument(
        "--command",
        required=True,
        choices=["help", "audit", "audit_last", "trust_report"],
        help="Command to render and send",
    )
    parser.add_argument("--task", default=None, help="Task ID for --command audit")
    parser.add_argument("--limit", type=int, default=10, help="Limit for audit_last")
    parser.add_argument("--project-dir", default=None, help="Project directory")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve() if args.project_dir else Path.cwd()
    if not (project_dir / "tasks.json").exists():
        print(f"fail: no tasks.json in {project_dir}")
        return 1
    return asyncio.run(run_smoke(project_dir, args.command, args.task, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
