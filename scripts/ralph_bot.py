#!/usr/bin/env python3
"""Telegram bot for Ralph orchestration monitoring and control."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
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
caffeinate_process: subprocess.Popen | None = None


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
        tasks = [item for item in tasks if str(item.get("phase", "")) == phase]
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
            lines.append(f"  {task['id']} [{task.get('priority', 'medium')}] {task['title']}{dep_str}")
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
        lines = latest.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        tail = lines[-n:] if len(lines) > n else lines
        header = f"📋 {latest.name} (last {len(tail)} lines)\n"
        return header + "\n".join(tail)
    except Exception as e:  # noqa: BLE001
        return f"Error reading {latest.name}: {e}"


async def send_message(text: str, reply_markup: dict | None = None) -> None:
    """Send message via Telegram API."""
    import urllib.request

    if not text:
        return

    max_len = 4000
    chunks: list[str] = []
    while len(text) > max_len:
        cut = text.rfind("\n", 0, max_len)
        if cut < 100:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)

    for idx, chunk in enumerate(chunks):
        payload: dict[str, object] = {
            "chat_id": CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
        }
        if reply_markup and idx == 0:
            payload["reply_markup"] = reply_markup

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{API}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            retry_payload: dict[str, object] = {
                "chat_id": CHAT_ID,
                "text": chunk,
                "parse_mode": "HTML",
            }
            if reply_markup and idx == 0:
                retry_payload["reply_markup"] = reply_markup
            try:
                data = json.dumps(retry_payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{API}/sendMessage",
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=10)
            except Exception as exc2:  # noqa: BLE001
                print(f"[bot] Send error (retry failed): {exc2}", file=sys.stderr)


async def safe_send(text: str, reply_markup: dict | None = None) -> None:
    """Best-effort message send; never raises to caller."""
    try:
        await send_message(text, reply_markup=reply_markup)
    except Exception as exc:  # noqa: BLE001
        print(f"[bot] Send error: {exc}", file=sys.stderr)


def set_idle_state(message: str = "Idle") -> None:
    """Force state file to idle when bot detects runner failure/exit."""
    payload = {
        "status": "idle",
        "current_task": None,
        "current_phase_step": None,
        "last_update": datetime.now(timezone.utc).isoformat(),
        "message": message,
    }
    try:
        STATE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"[bot] State write error: {exc}", file=sys.stderr)


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

    await safe_send("\n".join(lines))


async def cmd_start_task(task_id: str) -> None:
    """Start single task."""
    global ralph_process
    state = read_state()
    if state.get("status") == "running":
        await safe_send("⚠️ Ralph already running. /stop first.")
        return
    write_control("continue", "")
    ralph_process = subprocess.Popen(
        [str(RALPH_DIR / "ralph.sh"), "task", task_id],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    await safe_send(f"▶️ Started task {task_id}\nPID: {ralph_process.pid}")


async def cmd_start_phase(phase: str) -> None:
    """Start phase execution."""
    global ralph_process
    state = read_state()
    if state.get("status") == "running":
        await safe_send("⚠️ Ralph already running. /stop first.")
        return
    write_control("continue", "")
    ralph_process = subprocess.Popen(
        [str(RALPH_DIR / "ralph.sh"), "phase", phase],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    await safe_send(f"▶️ Started phase {phase}\nPID: {ralph_process.pid}")


async def cmd_start_auto() -> None:
    """Start auto mode."""
    global ralph_process, caffeinate_process
    state = read_state()
    if state.get("status") == "running":
        await safe_send("⚠️ Ralph already running. /stop first.")
        return
    try:
        write_control("continue", "")
        try:
            caffeinate_process = subprocess.Popen(["caffeinate", "-dims"])
        except FileNotFoundError:
            caffeinate_process = None
        ralph_process = subprocess.Popen(
            [str(RALPH_DIR / "ralph.sh"), "auto"],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        await safe_send(f"🚀 Auto mode started\nPID: {ralph_process.pid}")
    except Exception as exc:  # noqa: BLE001
        set_idle_state("Ralph failed to start")
        await safe_send(f"❌ Ralph crashed: {exc}")


async def cmd_stop(force: bool = False) -> None:
    """Stop or kill Ralph."""
    global ralph_process, caffeinate_process

    if force:
        # 1. Kill all ralph processes by PID files
        killed_pids = []
        for pf in ["ralph_codex.pid", "ralph_main.pid"]:
            p = PROJECT_DIR / pf
            if p.exists():
                try:
                    pid = int(p.read_text().strip())
                    os.kill(pid, signal.SIGKILL)
                    subprocess.run(["pkill", "-KILL", "-P", str(pid)], capture_output=True)
                    killed_pids.append(pid)
                except (ProcessLookupError, ValueError):
                    pass
                p.unlink(missing_ok=True)

        # 2. Kill ralph_process if bot tracks it
        if ralph_process and ralph_process.poll() is None:
            ralph_process.kill()
            ralph_process.wait()

        # 3. Kill caffeinate
        if caffeinate_process:
            caffeinate_process.terminate()
            caffeinate_process = None

        # 4. CRITICAL: Update state file to idle
        set_idle_state("Stopped by user (force kill)")

        # 5. Clean up control file
        write_control("", "")

        # 6. Reset globals
        ralph_process = None

        # 7. Confirm
        await safe_send(f"⏹ Ralph killed. PIDs: {killed_pids or 'none'}\nState: idle")
    else:
        # Graceful stop
        write_control("stop", "")
        if ralph_process and ralph_process.poll() is None:
            await safe_send("⏹ Ralph will stop after current task")
            # Wait up to 30 seconds for graceful shutdown
            for _ in range(30):
                await asyncio.sleep(1)
                if ralph_process.poll() is not None:
                    break
            # If still running after 30s, force kill
            if ralph_process.poll() is None:
                await safe_send("⚠️ Ralph did not stop gracefully, force killing...")
                await cmd_stop(force=True)
                return
            # Stopped gracefully
            set_idle_state("Stopped gracefully by user")
            if caffeinate_process:
                caffeinate_process.terminate()
                caffeinate_process = None
            ralph_process = None
            await safe_send("⏹ Ralph stopped gracefully. State: idle")
        else:
            set_idle_state("Idle")
            ralph_process = None
            await safe_send("⏸ Ralph is not running")


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
        await safe_send(f"🔄 {task_id} reset to pending{suffix}")
    except subprocess.CalledProcessError as exc:
        await safe_send(f"❌ Error: {exc.stderr.decode()}")


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
        await safe_send(f"<pre>{diff}</pre>")
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ {exc}")


async def cmd_cost() -> None:
    """Show today's token usage and estimated cost."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"ralph_{today}.log"

    if not log_file.exists():
        await safe_send(f"📊 No log for today ({today})")
        return

    total_tokens = 0
    task_count = 0

    with log_file.open(encoding="utf-8", errors="replace") as f:
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
    await safe_send(msg)


async def cmd_progress(n: int = 20) -> None:
    """Show tail of progress.md."""
    if not PROGRESS_FILE.exists():
        await safe_send("No progress.md found")
        return
    lines = PROGRESS_FILE.read_text(encoding="utf-8").strip().splitlines()
    tail = lines[-n:] if len(lines) > n else lines
    await safe_send(f"<pre>{chr(10).join(tail)}</pre>")


async def cmd_tail(n: int = 20) -> None:
    """Show last N lines from most recent codex output file."""
    import glob

    patterns = ["/tmp/ralph_coder_*.txt", "/tmp/ralph_lead_*.txt"]
    all_files = []
    for pattern in patterns:
        all_files.extend(glob.glob(pattern))

    if not all_files:
        await safe_send("No codex output files found in /tmp/")
        return

    latest = max(all_files, key=lambda f: Path(f).stat().st_mtime)
    name = Path(latest).name
    age_sec = int(time.time() - Path(latest).stat().st_mtime)

    try:
        lines = Path(latest).read_text(encoding="utf-8", errors="replace").strip().splitlines()
        tail = lines[-n:] if len(lines) > n else lines

        if age_sec < 60:
            freshness = f"🟢 {age_sec}s ago (likely running)"
        elif age_sec < 300:
            freshness = f"🟡 {age_sec // 60}m ago"
        else:
            freshness = f"🔴 {age_sec // 60}m ago (stale)"

        header = f"📡 {name} — {freshness}\n"
        text = header + "\n".join(tail)
        if len(text) > 4000:
            text = text[:4000] + "\n... (truncated)"
        await safe_send(f"<pre>{text}</pre>")
    except Exception as e:  # noqa: BLE001
        await safe_send(f"Error reading {name}: {e}")


async def cmd_help() -> None:
    """Send help text."""
    await safe_send(
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
        "/tail [N] — last N lines of live codex output\n"
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
            await safe_send(f"⏭ Skipping {task_id}")
        return

    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "/status":
        await cmd_status()
    elif cmd == "/tasks":
        await safe_send(get_tasks_summary(args or None))
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
        await safe_send(f"📝 Comment saved for next task:\n{args}")
    elif cmd == "/log":
        n = int(args) if args.isdigit() else 15
        await safe_send(f"<pre>{get_log_tail(n)}</pre>")
    elif cmd == "/progress":
        n = int(args) if args.isdigit() else 20
        await cmd_progress(n)
    elif cmd == "/tail":
        n = int(args) if args.isdigit() else 20
        await cmd_tail(n)
    elif cmd == "/cost":
        await cmd_cost()
    elif cmd == "/diff":
        await cmd_diff()
    elif cmd == "/help" or (cmd == "/start" and not args):
        await cmd_help()
    else:
        await safe_send("Unknown command. Try /help")


async def poll_updates() -> None:
    """Long-polling loop for Telegram updates."""
    import urllib.request

    offset = 0
    consecutive_errors = 0
    backoff_seconds = 5
    while True:
        try:
            url = f"{API}/getUpdates?offset={offset}&timeout=30"
            resp = urllib.request.urlopen(url, timeout=35)
            data = json.loads(resp.read())

            if consecutive_errors > 0:
                await safe_send(f"⚠️ Bot reconnected after {consecutive_errors} poll errors")
                consecutive_errors = 0
                backoff_seconds = 5

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                try:
                    await handle_update(update)
                except Exception as exc:  # noqa: BLE001
                    print(f"[bot] Handler error: {exc}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            consecutive_errors += 1
            delay = min(backoff_seconds, 60)
            print(f"[bot] Poll error #{consecutive_errors}, retry in {delay}s: {exc}", file=sys.stderr)
            await asyncio.sleep(delay)
            backoff_seconds = min(backoff_seconds * 2, 60)


async def watch_state() -> None:
    """Watch ralph_state.json for notifications."""
    global ralph_process, caffeinate_process

    last_task = None
    last_status = None
    last_exit_code: int | None = None

    while True:
        await asyncio.sleep(3)

        if ralph_process and ralph_process.poll() is not None:
            code = ralph_process.returncode
            if code != 0 and code != last_exit_code:
                await safe_send(f"⚠️ Ralph exited with code {code}")
            last_exit_code = code
            set_idle_state(f"Ralph exited with code {code}")
            if caffeinate_process:
                caffeinate_process.terminate()
                caffeinate_process = None
            ralph_process = None

        state = read_state()
        status = state.get("status")
        task = state.get("current_task")

        if task != last_task and task:
            last_task = task
            await safe_send(f"📋 Working on: <b>{task}</b>")

        if status != last_status:
            if status == "waiting_human":
                reason = state.get("alert_reason", "Unknown")
                await safe_send(
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
                await safe_send("✅ Ralph finished!")
            last_status = status


async def main() -> None:
    """Start bot loops."""
    if not TOKEN or not CHAT_ID:
        print("Set RALPH_TELEGRAM_TOKEN and RALPH_TELEGRAM_CHAT_ID in .env")
        sys.exit(1)

    # Clean up orphaned state from previous bot crash
    for pf in ["ralph_codex.pid", "ralph_main.pid"]:
        p = PROJECT_DIR / pf
        if p.exists():
            try:
                pid = int(p.read_text().strip())
                os.kill(pid, 0)  # check if alive
            except (ProcessLookupError, ValueError):
                p.unlink(missing_ok=True)  # dead process, clean up

    await safe_send("🤖 Ralph Bot started! Type /help for commands.")
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
    print("   caffeinate: enabled during auto mode")

    asyncio.run(main())
