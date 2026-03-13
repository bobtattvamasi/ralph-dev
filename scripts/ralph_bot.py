#!/usr/bin/env python3
"""Telegram bot for Ralph orchestration monitoring and control."""

from __future__ import annotations

import asyncio
import csv
import datetime
import html
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

RALPH_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = Path.cwd()  # overridden in __main__
STATE_FILE = PROJECT_DIR / "ralph_state.json"
CONTROL_FILE = PROJECT_DIR / "ralph_control.json"
TASKS_FILE = PROJECT_DIR / "tasks.json"
PROGRESS_FILE = PROJECT_DIR / "progress.md"
LOG_DIR = PROJECT_DIR / "logs"
DAILY_COST_LIMIT_USD = 500.0
BLOG_DRAFTS_FILE = PROJECT_DIR / "BLOG_DRAFTS.md"

TOKEN = ""
CHAT_ID = ""
API = ""
ralph_process = None
caffeinate_process = None
RUNTIME = SimpleNamespace(
    ralph_process=None,
    caffeinate_process=None,
)

HOT_RELOAD_EXPORTS = [
    "read_state",
    "write_control",
    "get_tasks_summary",
    "get_log_tail",
    "load_tasks_data",
    "save_tasks_data",
    "send_message",
    "safe_send",
    "send_split_message",
    "set_idle_state",
    "cmd_status",
    "cmd_start_task",
    "cmd_start_phase",
    "cmd_start_auto",
    "cmd_stop",
    "cmd_redo",
    "cmd_pause",
    "cmd_resume",
    "cmd_add",
    "cmd_rm",
    "cmd_diff",
    "cmd_cost",
    "cmd_stats",
    "cmd_limits",
    "cmd_plan",
    "cmd_article",
    "cmd_progress",
    "cmd_tail",
    "cmd_help",
    "cmd_reload",
    "handle_update",
]


def configure_module_runtime(module: ModuleType) -> None:
    """Inject current runtime state into a freshly loaded hot-reload module."""
    module.RALPH_DIR = RALPH_DIR
    module.PROJECT_DIR = PROJECT_DIR
    module.STATE_FILE = PROJECT_DIR / "ralph_state.json"
    module.CONTROL_FILE = PROJECT_DIR / "ralph_control.json"
    module.TASKS_FILE = PROJECT_DIR / "tasks.json"
    module.PROGRESS_FILE = PROJECT_DIR / "progress.md"
    module.LOG_DIR = PROJECT_DIR / "logs"
    module.BLOG_DRAFTS_FILE = PROJECT_DIR / "BLOG_DRAFTS.md"
    module.TOKEN = TOKEN
    module.CHAT_ID = CHAT_ID
    module.API = API
    module.ralph_process = RUNTIME.ralph_process
    module.caffeinate_process = RUNTIME.caffeinate_process
    module.RUNTIME = RUNTIME


def load_bot_module_from_source() -> ModuleType:
    """Load the current bot file as a standalone module for hot reload."""
    module_path = Path(__file__).resolve()
    spec = importlib.util.spec_from_file_location("ralph_bot_hotreload", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {module_path.name}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    configure_module_runtime(module)
    return module


def apply_hot_reload(module: ModuleType) -> None:
    """Swap command/helper functions to the freshly loaded module version."""
    missing = [name for name in HOT_RELOAD_EXPORTS if not hasattr(module, name)]
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise RuntimeError(f"Reload module missing exports: {missing_str}")

    for name in HOT_RELOAD_EXPORTS:
        globals()[name] = getattr(module, name)


def read_state() -> dict:
    """Read ralph state file."""
    if STATE_FILE.exists():
        try:
            return normalize_state_for_display(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return {"status": "idle", "current_task": None, "last_update": None}


def is_pid_alive(pid: object) -> bool:
    """Return True if the given PID belongs to a live process."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def normalize_state_for_display(state: dict) -> dict:
    """Treat stale waiting/running/paused state as idle for display only."""
    if not isinstance(state, dict):
        return {"status": "idle", "current_task": None, "last_update": None}

    status = state.get("status", "idle")
    if status not in ("waiting_human", "running", "paused"):
        return state

    last_update = state.get("last_update")
    if not last_update:
        return state

    try:
        updated_at = datetime.fromisoformat(str(last_update).replace("Z", "+00:00"))
    except ValueError:
        return state

    if (datetime.now(timezone.utc) - updated_at).total_seconds() <= 600:
        return state

    if is_pid_alive(state.get("pid")):
        return state

    display_state = dict(state)
    display_state["status"] = "idle"
    display_state["message"] = "Auto-detected stale state"
    return display_state


def reset_stale_state() -> None:
    """Сбрасывает зависший стейт если ralph процесс не живой."""
    if not STATE_FILE.exists():
        return
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        status = state.get("status", "idle")
        if status in ("waiting_human", "running", "paused"):
            ralph_alive = is_pid_alive(state.get("pid"))
            if not ralph_alive:
                state["status"] = "idle"
                state["current_task"] = ""
                state["step"] = ""
                state["current_phase_step"] = ""
                state["message"] = "Auto-reset stale state on /auto"
                STATE_FILE.write_text(
                    json.dumps(state, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
    except Exception:
        pass


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


def load_tasks_data() -> dict:
    """Load tasks.json as a dict."""
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def save_tasks_data(data: dict) -> None:
    """Persist tasks.json with stable formatting."""
    TASKS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare_html_message(text: str) -> str:
    """Escape plain text while preserving the bot's small allowed HTML subset."""
    if any(tag in text for tag in ("<b>", "</b>", "<pre>", "</pre>", "<code>", "</code>")):
        return text
    return html.escape(text)


def parse_metric_number(row: dict, key: str) -> float:
    """Parse a numeric metrics field with safe fallback."""
    try:
        return float(row.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def summarize_metrics(rows: list[dict]) -> dict[str, float | int]:
    """Aggregate task metrics for /stats output."""
    total_tasks = len(rows)
    success_rows = [row for row in rows if row.get("status") == "success"]
    failed_rows = [row for row in rows if row.get("status") == "failed"]

    avg_duration = (
        sum(parse_metric_number(row, "duration_s") for row in rows) / total_tasks
        if total_tasks
        else 0.0
    )
    avg_attempts = (
        sum(parse_metric_number(row, "attempts") for row in rows) / total_tasks
        if total_tasks
        else 0.0
    )
    avg_files_changed = (
        sum(parse_metric_number(row, "files_changed") for row in rows) / total_tasks
        if total_tasks
        else 0.0
    )
    total_cost = sum(parse_metric_number(row, "cost_est") for row in rows)

    return {
        "total_tasks": total_tasks,
        "success_count": len(success_rows),
        "failed_count": len(failed_rows),
        "avg_duration": avg_duration,
        "avg_attempts": avg_attempts,
        "avg_files_changed": avg_files_changed,
        "total_cost": total_cost,
    }


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
        await send_message(prepare_html_message(text), reply_markup=reply_markup)
    except Exception as exc:  # noqa: BLE001
        print(f"[bot] Send error: {exc}", file=sys.stderr)


async def send_split_message(text: str) -> None:
    """Send a long message in chunks close to Telegram's limit."""
    if not text:
        return

    if len(text) <= 4000:
        await safe_send(text)
        return

    remaining = text
    while remaining:
        if len(remaining) <= 4000:
            chunk = remaining
            remaining = ""
        else:
            cut = remaining.rfind("\n", 0, 4000)
            if cut < 100:
                cut = 4000
            chunk = remaining[:cut]
            remaining = remaining[cut:].lstrip("\n")
        await safe_send(chunk)


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
    RUNTIME.ralph_process = subprocess.Popen(
        [str(RALPH_DIR / "ralph.sh"), "task", task_id],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    ralph_process = RUNTIME.ralph_process
    await safe_send(f"▶️ Started task {task_id}\nPID: {RUNTIME.ralph_process.pid}")


async def cmd_start_phase(phase: str) -> None:
    """Start phase execution."""
    global ralph_process
    state = read_state()
    if state.get("status") == "running":
        await safe_send("⚠️ Ralph already running. /stop first.")
        return
    write_control("continue", "")
    RUNTIME.ralph_process = subprocess.Popen(
        [str(RALPH_DIR / "ralph.sh"), "phase", phase],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    ralph_process = RUNTIME.ralph_process
    await safe_send(f"▶️ Started phase {phase}\nPID: {RUNTIME.ralph_process.pid}")


async def cmd_start_auto() -> None:
    """Start auto mode."""
    global ralph_process, caffeinate_process
    reset_stale_state()
    state = read_state()
    if state.get("status") == "running":
        await safe_send("⚠️ Ralph already running. /stop first.")
        return
    try:
        write_control("continue", "")
        try:
            RUNTIME.caffeinate_process = subprocess.Popen(["caffeinate", "-dims"])
        except FileNotFoundError:
            RUNTIME.caffeinate_process = None
        caffeinate_process = RUNTIME.caffeinate_process
        RUNTIME.ralph_process = subprocess.Popen(
            [str(RALPH_DIR / "ralph.sh"), "auto"],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        ralph_process = RUNTIME.ralph_process
        await safe_send(f"🚀 Auto mode started\nPID: {RUNTIME.ralph_process.pid}")
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
        if RUNTIME.ralph_process and RUNTIME.ralph_process.poll() is None:
            RUNTIME.ralph_process.kill()
            RUNTIME.ralph_process.wait()
        ralph_process = None

        # 3. Kill caffeinate
        if RUNTIME.caffeinate_process:
            RUNTIME.caffeinate_process.terminate()
            RUNTIME.caffeinate_process = None
        caffeinate_process = None

        # 4. CRITICAL: Update state file to idle
        set_idle_state("Stopped by user (force kill)")

        # 5. Clean up control file
        write_control("", "")

        # 6. Reset globals
        RUNTIME.ralph_process = None
        ralph_process = None

        # 7. Confirm
        await safe_send(f"⏹ Ralph killed. PIDs: {killed_pids or 'none'}\nState: idle")
    else:
        # Graceful stop
        write_control("stop", "")
        if RUNTIME.ralph_process and RUNTIME.ralph_process.poll() is None:
            await safe_send("⏹ Ralph will stop after current task")
            # Wait up to 30 seconds for graceful shutdown
            for _ in range(30):
                await asyncio.sleep(1)
                if RUNTIME.ralph_process.poll() is not None:
                    break
            # If still running after 30s, force kill
            if RUNTIME.ralph_process.poll() is None:
                await safe_send("⚠️ Ralph did not stop gracefully, force killing...")
                await cmd_stop(force=True)
                return
            # Stopped gracefully
            set_idle_state("Stopped gracefully by user")
            if RUNTIME.caffeinate_process:
                RUNTIME.caffeinate_process.terminate()
                RUNTIME.caffeinate_process = None
            caffeinate_process = None
            RUNTIME.ralph_process = None
            ralph_process = None
            await safe_send("⏹ Ralph stopped gracefully. State: idle")
        else:
            set_idle_state("Idle")
            RUNTIME.ralph_process = None
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


async def cmd_done(task_id: str) -> None:
    """Mark a task as done from Telegram."""
    if not task_id:
        await safe_send("Usage: /done [task_id]")
        return
    try:
        subprocess.run(
            ["python3", "scripts/update_task.py", task_id, "done", "Done via Telegram"],
            cwd=str(PROJECT_DIR),
            check=True,
            capture_output=True,
            text=True,
        )
        await safe_send(f"✅ Task {task_id} marked done")
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        await safe_send(f"❌ Error: {err}")


async def cmd_timeout(seconds: str) -> None:
    """Store a timeout override in ralph_control.json."""
    value = seconds.strip()
    if not value.isdigit():
        await safe_send("Usage: /timeout [seconds]")
        return
    write_control("timeout", value)
    await safe_send(f"⏱ Timeout override set to {value}s for the next task step")


async def cmd_pause() -> None:
    """Pause Ralph until /resume is sent."""
    write_control("pause", "")
    await safe_send("⏸ Ralph paused (will wait before next step)")


async def cmd_resume() -> None:
    """Resume Ralph after pause."""
    write_control("continue", "")
    await safe_send("▶️ Ralph resumed")


async def cmd_add(args: str) -> None:
    """Add a new pending task to tasks.json."""
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await safe_send("Usage: /add <phase> <title>")
        return

    phase, title = parts[0].strip(), parts[1].strip()
    if not phase or not title:
        await safe_send("Usage: /add <phase> <title>")
        return

    if not TASKS_FILE.exists():
        await safe_send("No tasks.json found")
        return

    try:
        data = load_tasks_data()
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error reading tasks.json: {exc}")
        return

    tasks = data.get("tasks", [])
    phase_pattern = re.compile(rf"^{re.escape(phase)}-(\d+)$")
    next_num = 1
    for task in tasks:
        match = phase_pattern.match(str(task.get("id", "")))
        if match:
            next_num = max(next_num, int(match.group(1)) + 1)

    task_id = f"{phase}-{next_num:02d}"
    new_task = {
        "id": task_id,
        "phase": phase,
        "category": "feature",
        "priority": "medium",
        "title": title,
        "description": title,
        "acceptance_criteria": [],
        "test_steps": [],
        "dependencies": [],
        "status": "pending",
    }
    tasks.append(new_task)
    data["tasks"] = tasks

    try:
        save_tasks_data(data)
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error saving tasks.json: {exc}")
        return

    await safe_send(f"✅ Task {task_id} added")


async def cmd_rm(args: str) -> None:
    """Remove a task from tasks.json by id."""
    task_id = args.strip()
    if not task_id:
        await safe_send("Usage: /rm <task_id>")
        return

    if not TASKS_FILE.exists():
        await safe_send("No tasks.json found")
        return

    try:
        data = load_tasks_data()
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error reading tasks.json: {exc}")
        return

    tasks = data.get("tasks", [])
    filtered_tasks = [task for task in tasks if task.get("id") != task_id]
    if len(filtered_tasks) == len(tasks):
        await safe_send(f"❌ Task {task_id} not found")
        return

    data["tasks"] = filtered_tasks
    try:
        save_tasks_data(data)
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error saving tasks.json: {exc}")
        return

    await safe_send(f"🗑 Task {task_id} removed")


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


async def cmd_stats() -> None:
    """Show aggregated execution stats from logs/metrics.csv."""
    metrics_file = LOG_DIR / "metrics.csv"
    if not metrics_file.exists() or metrics_file.stat().st_size == 0:
        await safe_send("📊 No metrics available yet. Run some tasks!")
        return

    try:
        with metrics_file.open(encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error reading metrics.csv: {exc}")
        return

    if not rows:
        await safe_send("📊 No metrics available yet. Run some tasks!")
        return

    summary = summarize_metrics(rows)

    msg = (
        "📊 <b>Ralph Stats</b>\n"
        f"Всего задач: {summary['total_tasks']}\n"
        f"Успешных: {summary['success_count']}\n"
        f"Проваленных: {summary['failed_count']}\n"
        f"Средняя длительность: {summary['avg_duration']:.1f}s\n"
        f"Среднее число попыток: {summary['avg_attempts']:.1f}\n"
        f"Среднее число измененных файлов: {summary['avg_files_changed']:.1f}\n"
        f"Оценка стоимости: ${summary['total_cost']:.2f}"
    )
    await safe_send(msg)


async def cmd_limits() -> None:
    """Show today's usage against the current daily cost limit."""
    metrics_file = LOG_DIR / "metrics.csv"
    if not metrics_file.exists() or metrics_file.stat().st_size == 0:
        await safe_send("📊 No metrics available yet. Run some tasks!")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with metrics_file.open(encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error reading metrics.csv: {exc}")
        return

    today_rows = [row for row in rows if str(row.get("timestamp", "")).startswith(today)]
    if not today_rows:
        await safe_send("📊 No metrics available yet. Run some tasks!")
        return

    def parse_float(row: dict, key: str) -> float:
        try:
            return float(row.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    total_tasks = len(today_rows)
    total_cost = sum(parse_float(row, "cost_est") for row in today_rows)
    status = "WARNING" if total_cost > DAILY_COST_LIMIT_USD else "OK"

    msg = (
        "💰 <b>Today's Usage</b>\n"
        f"Tasks: {total_tasks}\n"
        f"Cost: ${total_cost:.2f} / ${DAILY_COST_LIMIT_USD:.2f}\n"
        f"Status: {status}"
    )
    await safe_send(msg)


async def cmd_plan() -> None:
    """Show tasks grouped by phase plus next pending tasks."""
    if not TASKS_FILE.exists():
        await safe_send("No tasks.json found")
        return

    try:
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error reading tasks.json: {exc}")
        return

    tasks = data.get("tasks", [])
    if not tasks:
        await safe_send("No tasks.json found")
        return

    phase_order = data.get("phases", {})
    ordered_phases = sorted(
        {str(task.get("phase", "?")) for task in tasks},
        key=lambda phase: list(phase_order).index(phase) if phase in phase_order else phase,
    )

    lines = ["📋 <b>Ralph Plan</b>"]
    for phase in ordered_phases:
        phase_tasks = [task for task in tasks if str(task.get("phase", "?")) == phase]
        done_count = sum(1 for task in phase_tasks if task.get("status") == "done")
        lines.append(f"Phase {phase}: {done_count}/{len(phase_tasks)} done")

    pending_tasks = [task for task in tasks if task.get("status") == "pending"]
    if pending_tasks:
        lines.append("")
        for task in pending_tasks[:5]:
            lines.append(f"Next: {task['id']} - {task['title']}")

    await safe_send("\n".join(lines))


async def cmd_article(mode: str = "") -> None:
    """Generate an article pack and send the latest draft."""
    script_path = RALPH_DIR / "scripts" / "write_article.sh"
    if not script_path.exists():
        await safe_send("❌ scripts/write_article.sh not found")
        return

    latest_article = ""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if mode != "new" and BLOG_DRAFTS_FILE.exists():
        drafts_text = BLOG_DRAFTS_FILE.read_text(encoding="utf-8", errors="replace")
        date_headers = list(re.finditer(r"(?m)^## (\d{4}-\d{2}-\d{2}).*UTC\s*$", drafts_text))
        if date_headers:
            last_match = date_headers[-1]
            last_date = last_match.group(1)
            if last_date == today:
                latest_article = drafts_text[last_match.end():].strip()
                if latest_article:
                    await safe_send("📖 Нашел готовую статью за сегодня. Отправляю...")

        try:
            if mode == "new" or not latest_article:
                await safe_send("⏳ Журналист собирает логи и пишет статью. Это займет 1-2 минуты...")
                process = await asyncio.create_subprocess_exec(
                    str(script_path),
                    cwd=str(PROJECT_DIR),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
                except asyncio.TimeoutError:
                    await safe_send("❌ Таймаут: скрипт работал дольше 5 минут")
                    return
                if process.returncode != 0:
                    err_text = html.escape(stderr.decode("utf-8", errors="replace")[:3500])
                    await safe_send(f"❌ Ошибка:\n<pre>{err_text}</pre>")
                    return
                latest_article = stdout.decode("utf-8", errors="replace").strip()
        except Exception as exc:  # noqa: BLE001
            await safe_send(f"❌ Article generation failed: {exc}")
            return

    if not latest_article:
        await safe_send("✅ Статья готова в BLOG_DRAFTS.md")
        return

    match = re.search(
        r"(?:===TELEGRAM===|## Telegram)\s*(.*?)\s*(?:===LINKEDIN===|## LinkedIn)\s*(.*?)\s*(?:===PROMPTS===|## Cover Prompts|## Prompts)\s*(.*)",
        latest_article,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        await send_split_message("⚠️ Не удалось разобрать секции:\n\n" + latest_article)
        return

    telegram_text = match.group(1).strip()
    linkedin_text = match.group(2).strip()
    prompts_text = match.group(3).strip()

    await send_split_message("===TELEGRAM===\n" + telegram_text)
    await send_split_message("===LINKEDIN===\n" + linkedin_text)
    await send_split_message("===PROMPTS===\n" + prompts_text)


async def cmd_progress(n: int = 20) -> None:
    """Show tail of progress.md."""
    if not PROGRESS_FILE.exists():
        await safe_send("No progress.md found")
        return
    lines = PROGRESS_FILE.read_text(encoding="utf-8").strip().splitlines()
    tail = lines[-n:] if len(lines) > n else lines
    progress_text = html.escape(chr(10).join(tail))
    await safe_send(f"<pre>{progress_text}</pre>")


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
        tail_text = header + "\n".join(tail)
        if len(tail_text) > 4000:
            tail_text = tail_text[:4000] + "\n... (truncated)"
        tail_text = html.escape(tail_text)
        await safe_send(f"<pre>{tail_text}</pre>")
    except Exception as e:  # noqa: BLE001
        await safe_send(f"Error reading {name}: {e}")


async def cmd_reload() -> None:
    """Hot-reload bot helpers and command handlers from source."""
    try:
        module = load_bot_module_from_source()
        apply_hot_reload(module)
        await safe_send("♻️ Bot modules reloaded")
    except Exception as exc:  # noqa: BLE001
        error_text = html.escape(str(exc))[:500] or exc.__class__.__name__
        await safe_send(f"❌ Reload failed: {error_text}")


async def cmd_help() -> None:
    """Send help text."""
    await safe_send(
        "🤖 <b>Ralph Bot</b>\n\n"
        "/status — current state\n"
        "/tasks [phase] — task list\n"
        "/plan — phase summary and next pending tasks\n"
        "/article [new] — get today's article or generate a new one\n"
        "/add [phase] [title] — add a pending task\n"
        "/rm [task_id] — remove a task\n"
        "/pause — pause before next step\n"
        "/resume — resume after pause\n"
        "/start TASK_ID — run one task\n"
        "/phase NUM — run phase\n"
        "/auto — run all\n"
        "/stop — stop after current task\n"
        "/stop now — kill immediately\n"
        "/done [task_id] — mark task done\n"
        "/redo [task_id] [notes] — redo task\n"
        "/timeout [seconds] — set timeout override\n"
        "/comment text — instruction for next task\n"
        "/log [N] — last N lines from ralph execution log\n"
        "/progress [N] — last N lines from progress.md\n"
        "/tail [N] — last N lines of live codex output\n"
        "/cost — token usage & cost estimate\n"
        "/stats — aggregated task metrics from metrics.csv\n"
        "/limits — today's spend vs cost limit\n"
        "/diff — last commit changes\n"
        "/reload — hot-reload bot handlers\n"
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
    elif cmd == "/plan":
        await cmd_plan()
    elif cmd == "/article":
        await cmd_article(args.strip())
    elif cmd == "/add" and args:
        await cmd_add(args)
    elif cmd == "/rm":
        await cmd_rm(args)
    elif cmd == "/pause":
        await cmd_pause()
    elif cmd == "/resume":
        await cmd_resume()
    elif cmd == "/start" and args:
        await cmd_start_task(args)
    elif cmd == "/phase" and args:
        await cmd_start_phase(args)
    elif cmd == "/auto":
        await cmd_start_auto()
    elif cmd == "/stop":
        await cmd_stop(force="now" in args)
    elif cmd == "/done":
        await cmd_done(args.strip())
    elif cmd == "/redo" and args:
        args_parts = args.split(maxsplit=1)
        task_id = args_parts[0]
        notes = args_parts[1] if len(args_parts) > 1 else ""
        await cmd_redo(task_id, notes)
    elif cmd == "/timeout":
        await cmd_timeout(args.strip())
    elif cmd == "/comment" and args:
        write_control("comment", args)
        await safe_send(f"📝 Comment saved for next task:\n{args}")
    elif cmd == "/log":
        n = int(args) if args.isdigit() else 15
        log_text = html.escape(get_log_tail(n))
        await safe_send(f"<pre>{log_text}</pre>")
    elif cmd == "/progress":
        n = int(args) if args.isdigit() else 20
        await cmd_progress(n)
    elif cmd == "/tail":
        n = int(args) if args.isdigit() else 20
        await cmd_tail(n)
    elif cmd == "/cost":
        await cmd_cost()
    elif cmd == "/stats":
        await cmd_stats()
    elif cmd == "/limits":
        await cmd_limits()
    elif cmd == "/diff":
        await cmd_diff()
    elif cmd == "/reload":
        await cmd_reload()
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

        if ralph_process is None and RUNTIME.ralph_process is not None:
            ralph_process = RUNTIME.ralph_process
        if caffeinate_process is None and RUNTIME.caffeinate_process is not None:
            caffeinate_process = RUNTIME.caffeinate_process

        if ralph_process and ralph_process.poll() is not None:
            code = ralph_process.returncode
            if code != 0 and code != last_exit_code:
                await safe_send(f"⚠️ Ralph exited with code {code}")
            try:
                raw_state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
            except Exception:
                raw_state = {}

            current_task = str(raw_state.get("current_task") or "").strip()
            if raw_state.get("status") == "running" and current_task:
                try:
                    subprocess.run(
                        ["python3", "scripts/update_task.py", current_task, "pending"],
                        cwd=str(PROJECT_DIR),
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except Exception:
                    pass

                for rollback_cmd in (
                    ["git", "-C", str(PROJECT_DIR), "reset", "HEAD", "--", "."],
                    ["git", "-C", str(PROJECT_DIR), "checkout", "--", "."],
                ):
                    try:
                        subprocess.run(
                            rollback_cmd,
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                    except Exception:
                        pass

                await safe_send(
                    f"🔄 Ralph crashed during {current_task}. Task reset to pending, changes rolled back."
                )
            last_exit_code = code
            set_idle_state(f"Ralph exited with code {code}")
            if caffeinate_process:
                caffeinate_process.terminate()
                caffeinate_process = None
                RUNTIME.caffeinate_process = None
            ralph_process = None
            RUNTIME.ralph_process = None

        state = read_state()
        status = state.get("status")
        task = state.get("current_task")

        if task != last_task and task:
            last_task = task
            await safe_send(f"📋 Working on: <b>{task}</b>")

        if status != last_status:
            if status == "waiting_human":
                reason = state.get("message", "Unknown")
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
