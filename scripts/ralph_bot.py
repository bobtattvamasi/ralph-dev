#!/usr/bin/env python3
"""Telegram bot for Ralph orchestration monitoring and control."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RALPH_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = Path.cwd()  # overridden in __main__
STATE_FILE = PROJECT_DIR / "ralph_state.json"
CONTROL_FILE = PROJECT_DIR / "ralph_control.json"
TASKS_FILE = PROJECT_DIR / "tasks.json"
PROGRESS_FILE = PROJECT_DIR / "progress.md"
LOG_DIR = PROJECT_DIR / "logs"

TOKEN = ""
CHAT_ID = ""
API = ""
ralph_process: subprocess.Popen | None = None


def read_state() -> dict:
    """Read ralph state file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"status": "idle", "current_task": None, "last_update": None}


def write_control(action: str, comment: str = "") -> None:
    """Write control signal for ralph."""
    data = {
        "action": action,
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    CONTROL_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def get_tasks_summary(phase: str | None = None) -> str:
    """Get formatted tasks summary."""
    if not TASKS_FILE.exists():
        return "No tasks.json found"
    data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    if phase:
        tasks = [item for item in tasks if str(item["phase"]) == phase]
    done = [item for item in tasks if item["status"] == "done"]
    pending = [item for item in tasks if item["status"] == "pending"]
    lines = [f"📊 Tasks: {len(done)}/{len(tasks)} done\n"]
    if pending:
        lines.append("📋 Pending:")
        done_ids = {item["id"] for item in done}
        for task in pending[:8]:
            dep_str = ""
            deps = task.get("dependencies", [])
            if deps:
                unmet = [dep for dep in deps if dep not in done_ids]
                if unmet:
                    dep_str = f" ⛔ needs {','.join(unmet)}"
            lines.append(f"  {task['id']} [{task['priority']}] {task['title']}{dep_str}")
    if done:
        lines.append(f"\n✅ Done: {', '.join(item['id'] for item in done)}")
    return "\n".join(lines)


def get_log_tail(n: int = 15) -> str:
    """Get last N lines from the most recent ralph log file."""
    if not LOG_DIR.exists():
        return "No logs/ directory found"

    log_files = sorted(LOG_DIR.glob("ralph_*.log"), reverse=True)
    if not log_files:
        return "No ralph log files found"

    latest = log_files[0]
    try:
        lines = latest.read_text(encoding="utf-8").strip().splitlines()
        tail = lines[-n:] if len(lines) > n else lines
        header = f"📋 {latest.name} (last {len(tail)} lines)\n"
        return header + "\n".join(tail)
    except Exception as e:  # noqa: BLE001
        return f"Error reading {latest.name}: {e}"


async def send_message(text: str, reply_markup: dict | None = None) -> None:
    """Send message via Telegram API."""
    import urllib.parse
    import urllib.request

    payload: dict = {
        "chat_id": CHAT_ID,
        "text": text[:4096],
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(f"{API}/sendMessage", data=data)
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:  # noqa: BLE001
        print(f"[bot] Send error: {exc}", file=sys.stderr)


async def cmd_status() -> None:
    """Send status overview."""
    state = read_state()
    status = state.get("status", "idle")
    icons = {"idle": "⏸", "running": "🏃", "waiting_human": "🚨", "stopped": "⏹"}
    icon = icons.get(status, "❓")

    lines = [f"{icon} Status: <b>{status}</b>"]
    if state.get("current_task"):
        lines.append(f"📋 Task: {state['current_task']}")
    if state.get("current_phase_step"):
        lines.append(f"🔄 Step: {state['current_phase_step']}")
    if state.get("last_update"):
        lines.append(f"🕐 Updated: {state['last_update']}")
    if state.get("message"):
        lines.append(f"💬 {state['message']}")

    await send_message("\n".join(lines))


async def cmd_start_task(task_id: str) -> None:
    """Start single task."""
    global ralph_process
    state = read_state()
    if state.get("status") == "running":
        await send_message("⚠️ Ralph already running. /stop first.")
        return
    write_control("continue", "")
    ralph_process = subprocess.Popen(
        [str(RALPH_DIR / "ralph.sh"), "task", task_id],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    await send_message(f"▶️ Started task {task_id}\nPID: {ralph_process.pid}")


async def cmd_start_phase(phase: str) -> None:
    """Start phase execution."""
    global ralph_process
    state = read_state()
    if state.get("status") == "running":
        await send_message("⚠️ Ralph already running. /stop first.")
        return
    write_control("continue", "")
    ralph_process = subprocess.Popen(
        [str(RALPH_DIR / "ralph.sh"), "phase", phase],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    await send_message(f"▶️ Started phase {phase}\nPID: {ralph_process.pid}")


async def cmd_start_auto() -> None:
    """Start auto mode."""
    global ralph_process
    state = read_state()
    if state.get("status") == "running":
        await send_message("⚠️ Ralph already running. /stop first.")
        return
    write_control("continue", "")
    ralph_process = subprocess.Popen(
        [str(RALPH_DIR / "ralph.sh"), "auto"],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    await send_message(f"🚀 Auto mode started\nPID: {ralph_process.pid}")


async def cmd_stop(force: bool = False) -> None:
    """Stop or kill Ralph."""
    global ralph_process
    write_control("stop_now" if force else "stop", "")
    if ralph_process and ralph_process.poll() is None:
        if force:
            ralph_process.kill()
            await send_message("⏹ Ralph killed immediately")
        else:
            await send_message("⏹ Ralph will stop after current task")
    else:
        await send_message("⏸ Ralph is not running")
    ralph_process = None


async def cmd_redo(task_id: str, notes: str) -> None:
    """Reset task to pending."""
    try:
        subprocess.run(
            ["python3", "scripts/update_task.py", task_id, "pending", notes or "Redo via Telegram"],
            cwd=str(PROJECT_DIR),
            check=True,
            capture_output=True,
        )
        suffix = f"\nNotes: {notes}" if notes else ""
        await send_message(f"🔄 {task_id} reset to pending{suffix}")
    except subprocess.CalledProcessError as exc:
        await send_message(f"❌ Error: {exc.stderr.decode()}")


async def cmd_diff() -> None:
    """Send last diff stat."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--stat"],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
        )
        diff = result.stdout[:3000] or "No changes"
        await send_message(f"<pre>{diff}</pre>")
    except Exception as exc:  # noqa: BLE001
        await send_message(f"❌ {exc}")


async def cmd_cost() -> None:
    """Show today's token usage and estimated cost."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"ralph_{today}.log"

    if not log_file.exists():
        await send_message(f"📊 No log for today ({today})")
        return

    total_tokens = 0
    task_count = 0

    with log_file.open(encoding="utf-8") as f:
        for line in f:
            if "tokens=" in line:
                try:
                    for part in line.split():
                        if part.startswith("tokens="):
                            tokens = int(part.split("=")[1].rstrip(","))
                            total_tokens += tokens
                            task_count += 1
                except (ValueError, IndexError):
                    pass
            elif "Tokens:" in line:
                # Backward-compatible parsing for current log format:
                # "... [CODER] Tokens: 1,234 | ..."
                try:
                    token_part = line.split("Tokens:", 1)[1].strip().split()[0]
                    tokens = int(token_part.replace(",", ""))
                    total_tokens += tokens
                    task_count += 1
                except (ValueError, IndexError):
                    pass

    # Rough estimate for mixed Codex usage.
    cost_estimate = total_tokens / 1000 * 0.01

    msg = (
        f"📊 Cost Report — {today}\n"
        f"Tasks completed: {task_count}\n"
        f"Total tokens: {total_tokens:,}\n"
        f"Estimated cost: ${cost_estimate:.2f}\n"
        f"Log: {log_file.name}"
    )
    await send_message(msg)


async def cmd_progress(n: int = 20) -> None:
    """Show tail of progress.md."""
    if not PROGRESS_FILE.exists():
        await send_message("No progress.md found")
        return
    lines = PROGRESS_FILE.read_text(encoding="utf-8").strip().splitlines()
    tail = lines[-n:] if len(lines) > n else lines
    await send_message(f"<pre>{chr(10).join(tail)}</pre>")


async def cmd_help() -> None:
    """Send help text."""
    await send_message(
        "🤖 <b>Ralph Bot</b>\n\n"
        "/status — current state\n"
        "/tasks [phase] — task list\n"
        "/start TASK_ID — run one task\n"
        "/phase NUM — run phase\n"
        "/auto — run all\n"
        "/stop — stop after current task\n"
        "/stop now — kill immediately\n"
        "/redo TASK_ID [notes] — redo task\n"
        "/comment text — instruction for next task\n"
        "/log [N] — last N lines from ralph execution log\n"
        "/progress [N] — last N lines from progress.md\n"
        "/cost — token usage & cost estimate\n"
        "/diff — last commit changes\n"
    )


async def handle_update(update: dict) -> None:
    """Handle incoming Telegram update."""
    msg = update.get("message", {})
    text = msg.get("text", "").strip()
    callback = update.get("callback_query", {})

    if callback:
        data = callback.get("data", "")
        if data == "stop":
            await cmd_stop(force=False)
        elif data == "stop_now":
            await cmd_stop(force=True)
        elif data.startswith("skip:"):
            task_id = data.split(":", 1)[1]
            write_control("skip", task_id)
            await send_message(f"⏭ Skipping {task_id}")
        return

    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "/status":
        await cmd_status()
    elif cmd == "/tasks":
        await send_message(get_tasks_summary(args or None))
    elif cmd == "/start" and args:
        await cmd_start_task(args)
    elif cmd == "/phase" and args:
        await cmd_start_phase(args)
    elif cmd == "/auto":
        await cmd_start_auto()
    elif cmd == "/stop":
        await cmd_stop(force="now" in args)
    elif cmd == "/redo" and args:
        args_parts = args.split(maxsplit=1)
        task_id = args_parts[0]
        notes = args_parts[1] if len(args_parts) > 1 else ""
        await cmd_redo(task_id, notes)
    elif cmd == "/comment" and args:
        write_control("comment", args)
        await send_message(f"📝 Comment saved for next task:\n{args}")
    elif cmd == "/log":
        n = int(args) if args.isdigit() else 15
        await send_message(f"<pre>{get_log_tail(n)}</pre>")
    elif cmd == "/progress":
        n = int(args) if args.isdigit() else 20
        await cmd_progress(n)
    elif cmd == "/cost":
        await cmd_cost()
    elif cmd == "/diff":
        await cmd_diff()
    elif cmd == "/help" or (cmd == "/start" and not args):
        await cmd_help()
    else:
        await send_message("Unknown command. Try /help")


async def poll_updates() -> None:
    """Long-polling loop for Telegram updates."""
    import urllib.request

    offset = 0
    while True:
        try:
            url = f"{API}/getUpdates?offset={offset}&timeout=30"
            resp = urllib.request.urlopen(url, timeout=35)
            data = json.loads(resp.read())
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                try:
                    await handle_update(update)
                except Exception as exc:  # noqa: BLE001
                    print(f"[bot] Handler error: {exc}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"[bot] Poll error: {exc}", file=sys.stderr)
            await asyncio.sleep(5)


async def watch_state() -> None:
    """Watch ralph_state.json for notifications."""
    last_task = None
    last_status = None

    while True:
        await asyncio.sleep(3)
        state = read_state()
        status = state.get("status")
        task = state.get("current_task")

        if task != last_task and task:
            last_task = task
            await send_message(f"📋 Working on: <b>{task}</b>")

        if status != last_status:
            if status == "waiting_human":
                reason = state.get("alert_reason", "Unknown")
                await send_message(
                    f"🚨 <b>HUMAN NEEDED</b>\n\n{reason}",
                    reply_markup={
                        "inline_keyboard": [
                            [
                                {"text": "⏹ Stop", "callback_data": "stop"},
                                {"text": "💀 Kill", "callback_data": "stop_now"},
                            ],
                            [
                                {"text": f"⏭ Skip {task}", "callback_data": f"skip:{task}"},
                            ],
                        ]
                    },
                )
            elif status == "idle" and last_status == "running":
                await send_message("✅ Ralph finished!")
            last_status = status


async def main() -> None:
    """Start bot loops."""
    if not TOKEN or not CHAT_ID:
        print("Set RALPH_TELEGRAM_TOKEN and RALPH_TELEGRAM_CHAT_ID in .env")
        sys.exit(1)

    await send_message("🤖 Ralph Bot started! Type /help for commands.")
    await asyncio.gather(poll_updates(), watch_state())


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description="Ralph Telegram Bot")
    parser.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="Path to the project directory (contains tasks.json)",
    )
    args = parser.parse_args()

    # RALPH_DIR is always where this script lives
    RALPH_DIR = Path(__file__).resolve().parent.parent

    # PROJECT_DIR priority: --project-dir > RALPH_PROJECT_DIR env > cwd
    if args.project_dir:
        PROJECT_DIR = Path(args.project_dir).resolve()
    elif os.environ.get("RALPH_PROJECT_DIR"):
        PROJECT_DIR = Path(os.environ["RALPH_PROJECT_DIR"]).resolve()
    else:
        PROJECT_DIR = Path.cwd()

    if not (PROJECT_DIR / "tasks.json").exists():
        print(f"❌ No tasks.json in {PROJECT_DIR}")
        print("Run ralph-init.sh first or pass --project-dir")
        sys.exit(1)

    # Update all paths that depend on PROJECT_DIR
    STATE_FILE = PROJECT_DIR / "ralph_state.json"
    CONTROL_FILE = PROJECT_DIR / "ralph_control.json"
    TASKS_FILE = PROJECT_DIR / "tasks.json"
    PROGRESS_FILE = PROJECT_DIR / "progress.md"
    LOG_DIR = PROJECT_DIR / "logs"

    load_dotenv(PROJECT_DIR / ".env")
    TOKEN = os.environ.get("RALPH_TELEGRAM_TOKEN", "")
    CHAT_ID = os.environ.get("RALPH_TELEGRAM_CHAT_ID", "")
    API = f"https://api.telegram.org/bot{TOKEN}"

    print("🤖 Ralph Bot")
    print(f"   RALPH_DIR:   {RALPH_DIR}")
    print(f"   PROJECT_DIR: {PROJECT_DIR}")
    print(f"   Tasks:       {TASKS_FILE}")

    asyncio.run(main())
