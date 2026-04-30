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
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

try:
    from scripts.models import RalphState
except ImportError:
    from models import RalphState

try:
    from ralph_common import (
        CRASH_ROLLBACK_COMMANDS,
        DESTRUCTIVE_ROLLBACK_POLICY_NOTICE,
        atomic_write_json,
        get_article_generation_timeout_sec,
        get_telegram_poll_backoff_initial_sec,
        get_telegram_poll_backoff_max_sec,
        get_telegram_poll_request_timeout_sec,
        get_telegram_poll_timeout_sec,
        get_telegram_timeout_sec,
        locked_path,
        load_tasks_data as shared_load_tasks_data,
        mutate_tasks_data as shared_mutate_tasks_data,
        resolve_project_dir,
        save_tasks_data as shared_save_tasks_data,
        write_state_payload,
        write_control_data,
        destructive_rollback_enabled,
    )
except ImportError:
    from scripts.ralph_common import (
        CRASH_ROLLBACK_COMMANDS,
        DESTRUCTIVE_ROLLBACK_POLICY_NOTICE,
        atomic_write_json,
        get_article_generation_timeout_sec,
        get_telegram_poll_backoff_initial_sec,
        get_telegram_poll_backoff_max_sec,
        get_telegram_poll_request_timeout_sec,
        get_telegram_poll_timeout_sec,
        get_telegram_timeout_sec,
        locked_path,
        load_tasks_data as shared_load_tasks_data,
        mutate_tasks_data as shared_mutate_tasks_data,
        resolve_project_dir,
        save_tasks_data as shared_save_tasks_data,
        write_state_payload,
        write_control_data,
        destructive_rollback_enabled,
    )

RALPH_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = Path.cwd()  # overridden in __main__
REGISTRY_DIR = Path.home() / ".ralph"
REGISTRY_FILE = REGISTRY_DIR / "projects.json"
DEFAULT_PROJECT_NAME = "ralph-dev"
DEFAULT_TEST_CMD = "make test"
ACTIVE_PROJECT_NAME = DEFAULT_PROJECT_NAME
STATE_FILE = PROJECT_DIR / "ralph_state.json"
CONTROL_FILE = PROJECT_DIR / "ralph_control.json"
TASKS_FILE = PROJECT_DIR / "tasks.json"
PROGRESS_FILE = PROJECT_DIR / "progress.md"
LOG_DIR = PROJECT_DIR / "logs"
AUDIT_DIR = PROJECT_DIR / ".ralph" / "audit"
DAILY_COST_LIMIT_USD = 500.0
BLOG_DRAFTS_FILE = PROJECT_DIR / "BLOG_DRAFTS.md"
RALPH_MAIN_PID_FILE = PROJECT_DIR / "ralph_main.pid"
COMPLETED_TASK_STATUSES = {"done", "verified_done"}

TOKEN = ""
CHAT_ID = ""
API = ""
ralph_process = None
caffeinate_process = None
LAST_SEND_ERROR: dict[str, object] | None = None
CURRENT_SEND_CONTEXT = ""
CURRENT_HANDLER_NAME = ""
CURRENT_HANDLER_SEND_COUNT = 0
RUNTIME = SimpleNamespace(
    ralph_process=None,
    caffeinate_process=None,
)
ASK_USAGE_TEXT = "Usage: /ask <question>\nExample: /ask what is Ralph doing now?"
ASK_MAX_QUESTION_CHARS = 280
ASK_MAX_RESPONSE_CHARS = 1200
ASK_STREAM_CHUNK_CHARS = 700
ASK_BACKEND_ENV = "RALPH_ASK_BACKEND"
ASK_CODEX_MODEL_ENV = "RALPH_ASK_CODEX_MODEL"
ASK_CODEX_TIMEOUT_ENV = "RALPH_ASK_TIMEOUT_SEC"
ASK_CODEX_TIMEOUT_SEC = 90
ASK_CONTEXT_MAX_CHARS = 4000
ASK_TASKS_CONTEXT_MAX_CHARS = 1800
ASK_LOG_CONTEXT_LINES = 20
ASK_CODE_SNIPPET_MAX_LINES = 20
TELEGRAM_TIMEOUT_SEC = get_telegram_timeout_sec()
TELEGRAM_POLL_TIMEOUT_SEC = get_telegram_poll_timeout_sec()
TELEGRAM_POLL_REQUEST_TIMEOUT_SEC = get_telegram_poll_request_timeout_sec()
TELEGRAM_POLL_BACKOFF_INITIAL_SEC = get_telegram_poll_backoff_initial_sec()
TELEGRAM_POLL_BACKOFF_MAX_SEC = get_telegram_poll_backoff_max_sec()
ARTICLE_GENERATION_TIMEOUT_SEC = get_article_generation_timeout_sec()

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
    "cmd_projects",
    "cmd_switch",
    "cmd_status",
    "cmd_start_task",
    "cmd_start_phase",
    "cmd_start_auto",
    "cmd_stop",
    "cmd_exit",
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
    "cmd_audit",
    "cmd_audit_last",
    "cmd_trust_report",
    "cmd_ask",
    "cmd_help",
    "cmd_reload",
    "handle_update",
]


def configure_module_runtime(module: ModuleType) -> None:
    """Inject current runtime state into a freshly loaded hot-reload module."""
    module.RALPH_DIR = RALPH_DIR
    module.REGISTRY_DIR = REGISTRY_DIR
    module.REGISTRY_FILE = REGISTRY_FILE
    module.DEFAULT_PROJECT_NAME = DEFAULT_PROJECT_NAME
    module.DEFAULT_TEST_CMD = DEFAULT_TEST_CMD
    module.ACTIVE_PROJECT_NAME = ACTIVE_PROJECT_NAME
    module.PROJECT_DIR = PROJECT_DIR
    module.STATE_FILE = PROJECT_DIR / "ralph_state.json"
    module.CONTROL_FILE = PROJECT_DIR / "ralph_control.json"
    module.TASKS_FILE = PROJECT_DIR / "tasks.json"
    module.PROGRESS_FILE = PROJECT_DIR / "progress.md"
    module.LOG_DIR = PROJECT_DIR / "logs"
    module.AUDIT_DIR = PROJECT_DIR / ".ralph" / "audit"
    module.BLOG_DRAFTS_FILE = PROJECT_DIR / "BLOG_DRAFTS.md"
    module.RALPH_MAIN_PID_FILE = PROJECT_DIR / "ralph_main.pid"
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


def default_project_entry() -> dict[str, str]:
    """Return the built-in registry entry for the Ralph repo itself."""
    return {
        "path": str(RALPH_DIR),
        "test_cmd": DEFAULT_TEST_CMD,
    }


def default_projects_registry() -> dict[str, object]:
    """Return the default registry payload when none exists yet."""
    return {
        "version": 1,
        "active_project": DEFAULT_PROJECT_NAME,
        "projects": {
            DEFAULT_PROJECT_NAME: default_project_entry(),
        },
    }


def save_projects_registry(data: dict[str, object]) -> None:
    """Persist ~/.ralph/projects.json with the shared Ralph file lock."""
    with locked_path(REGISTRY_FILE):
        atomic_write_json(REGISTRY_FILE, data)


def load_projects_registry() -> dict[str, object]:
    """Load the Ralph project registry, creating the default file when missing."""
    if not REGISTRY_FILE.exists():
        data = default_projects_registry()
        save_projects_registry(data)
        return data

    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed registry JSON: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError("Registry must contain a JSON object.")

    projects = data.get("projects")
    if not isinstance(projects, dict):
        raise ValueError("Registry must contain a top-level 'projects' object.")

    data.setdefault("version", 1)
    data.setdefault("active_project", DEFAULT_PROJECT_NAME)
    if DEFAULT_PROJECT_NAME not in projects:
        projects[DEFAULT_PROJECT_NAME] = default_project_entry()
    if data.get("active_project") not in projects:
        data["active_project"] = DEFAULT_PROJECT_NAME

    save_projects_registry(data)
    return data


def apply_project_runtime(project_dir: Path, *, project_name: str | None = None) -> None:
    """Update all project-scoped globals after a context switch."""
    global PROJECT_DIR, ACTIVE_PROJECT_NAME, STATE_FILE, CONTROL_FILE, TASKS_FILE
    global PROGRESS_FILE, LOG_DIR, AUDIT_DIR, BLOG_DRAFTS_FILE, RALPH_MAIN_PID_FILE

    PROJECT_DIR = project_dir.resolve()
    if project_name:
        ACTIVE_PROJECT_NAME = project_name
    STATE_FILE = PROJECT_DIR / "ralph_state.json"
    CONTROL_FILE = PROJECT_DIR / "ralph_control.json"
    TASKS_FILE = PROJECT_DIR / "tasks.json"
    PROGRESS_FILE = PROJECT_DIR / "progress.md"
    LOG_DIR = PROJECT_DIR / "logs"
    AUDIT_DIR = PROJECT_DIR / ".ralph" / "audit"
    BLOG_DRAFTS_FILE = PROJECT_DIR / "BLOG_DRAFTS.md"
    RALPH_MAIN_PID_FILE = PROJECT_DIR / "ralph_main.pid"


def sync_active_project_runtime() -> None:
    """Refresh project-scoped globals from the registry active project."""
    try:
        registry = load_projects_registry()
    except ValueError:
        return

    active_name = registry.get("active_project")
    projects = registry.get("projects", {})
    if not isinstance(active_name, str) or not isinstance(projects, dict):
        return

    payload = projects.get(active_name)
    if not isinstance(payload, dict):
        return

    raw_path = payload.get("path")
    if not isinstance(raw_path, str):
        return

    project_dir = Path(raw_path).expanduser().resolve()
    if not (project_dir / "tasks.json").exists():
        return

    apply_project_runtime(project_dir, project_name=active_name)


def get_project_display_name(project_dir: Path, registry: dict[str, object] | None = None) -> str:
    """Return the registry name for a project path if available."""
    project_dir_resolved = project_dir.resolve()
    if registry is None:
        try:
            registry = load_projects_registry()
        except ValueError:
            return project_dir_resolved.name

    projects = registry.get("projects", {})
    if isinstance(projects, dict):
        for name, payload in projects.items():
            if not isinstance(name, str) or not isinstance(payload, dict):
                continue
            raw_path = payload.get("path")
            if not isinstance(raw_path, str):
                continue
            try:
                if Path(raw_path).expanduser().resolve() == project_dir_resolved:
                    return name
            except OSError:
                continue

    return project_dir_resolved.name


def get_project_snapshot(project_name: str, project_path: Path) -> dict[str, object]:
    """Collect lightweight status/progress data for one registered project."""
    snapshot: dict[str, object] = {
        "name": project_name,
        "path": project_path,
        "has_tasks": False,
        "status": "missing",
        "done_total": 0,
        "all_total": 0,
        "pct": 0,
        "current_task": None,
    }

    tasks_path = project_path / "tasks.json"
    state_path = project_path / "ralph_state.json"
    snapshot["has_tasks"] = tasks_path.exists()
    if tasks_path.exists():
        try:
            summary = get_task_summary(tasks_path)
        except (json.JSONDecodeError, OSError):
            snapshot["status"] = "tasks_error"
        else:
            snapshot.update(summary)
            snapshot["status"] = "idle"

    if state_path.exists():
        try:
            raw_state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            snapshot["status"] = "state_error"
        else:
            state = normalize_state_for_display(raw_state)
            snapshot["status"] = str(state.get("status", snapshot["status"]))
            snapshot["current_task"] = state.get("current_task")

    return snapshot


def resolve_initial_project_context(cli_project_dir: str | None) -> tuple[Path, str]:
    """Resolve startup context from explicit input first, then the active registry project."""
    if cli_project_dir or os.environ.get("RALPH_PROJECT_DIR"):
        project_dir = resolve_project_dir(cli_project_dir)
        return project_dir, get_project_display_name(project_dir)

    try:
        registry = load_projects_registry()
    except ValueError:
        project_dir = resolve_project_dir(None)
        return project_dir, project_dir.name

    active_name = str(registry.get("active_project", DEFAULT_PROJECT_NAME))
    projects = registry.get("projects", {})
    if isinstance(projects, dict):
        payload = projects.get(active_name)
        if isinstance(payload, dict):
            raw_path = payload.get("path")
            if isinstance(raw_path, str):
                candidate = Path(raw_path).expanduser().resolve()
                if (candidate / "tasks.json").exists():
                    return candidate, active_name

    project_dir = resolve_project_dir(None)
    return project_dir, get_project_display_name(project_dir, registry)


def read_state() -> dict:
    """Read ralph state file."""
    if STATE_FILE.exists():
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if raw.get("current_task") is None:
                raw["current_task"] = ""
            if raw.get("current_phase_step") is None:
                raw["current_phase_step"] = ""
            validated = RalphState.model_validate(raw).model_dump()
            return normalize_state_for_display(validated)
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


def get_live_ralph_pid() -> int | None:
    """Return live Ralph PID from pid file and clean up stale data."""
    try:
        raw_pid = RALPH_MAIN_PID_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    try:
        pid = int(raw_pid)
    except ValueError:
        RALPH_MAIN_PID_FILE.unlink(missing_ok=True)
        return None

    if is_pid_alive(pid):
        return pid

    RALPH_MAIN_PID_FILE.unlink(missing_ok=True)
    return None


def has_live_tracked_runtime() -> bool:
    """Return True when Ralph or its tracked Codex child is still alive."""
    if get_live_ralph_pid() is not None:
        return True
    codex_pid = _read_pid_value(PROJECT_DIR / "ralph_codex.pid")
    return codex_pid is not None and is_pid_alive(codex_pid)


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
            if not has_live_tracked_runtime():
                state["status"] = "idle"
                state["current_task"] = ""
                state["step"] = ""
                state["current_phase_step"] = ""
                state["message"] = "Auto-reset stale state on /auto"
                write_state_payload(STATE_FILE, state)
                write_control("", "")  # R20-02: reset control too
                log_bot(f"Recovered stale state from {status} to idle")
    except json.JSONDecodeError as exc:
        log_bot(f"Failed to reset stale state: malformed {STATE_FILE.name}: {exc}")
    except OSError as exc:
        log_bot(f"Failed to reset stale state: {exc}")


def write_control(action: str, comment: str = "") -> None:
    """Write control signal for ralph."""
    write_control_data(PROJECT_DIR, action, comment)


def get_tasks_summary(phase: str | None = None) -> str:
    """Get formatted tasks summary."""
    if not TASKS_FILE.exists():
        return "No tasks.json found"
    data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    if phase:
        tasks = [item for item in tasks if str(item.get("phase", "")) == phase]
    done = [item for item in tasks if item["status"] in COMPLETED_TASK_STATUSES]
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


def build_repo_local_ask_backend() -> dict[str, object]:
    """Return the explicit repo-local backend contract used by /ask.

    This backend is intentionally bounded and single-shot:
    - input: one question string
    - context: current repo-local Ralph state plus pending-task summary
    - output: one rendered response string
    - memory: none; no chat history or multi-turn state is stored
    """
    return {
        "name": "repo_local_single_shot",
        "mode": "single_shot",
        "max_question_chars": ASK_MAX_QUESTION_CHARS,
        "max_response_chars": ASK_MAX_RESPONSE_CHARS,
        "stream_answer": stream_repo_local_answer,
    }


def answer_repo_local_question(question: str) -> str:
    """Answer one /ask question from repo-local state without keeping history."""
    bounded_question = " ".join(question.split())[:ASK_MAX_QUESTION_CHARS]
    state = read_state()
    state_status = state.get("status", "idle")
    current_task = state.get("current_task") or "none"
    tasks_summary = get_tasks_summary()
    tasks_summary = tasks_summary[:600].strip()
    response = (
        "🧠 Ralph single-shot reply\n"
        f"Question: {bounded_question}\n"
        f"Status: {state_status}\n"
        f"Current task: {current_task}\n\n"
        "Repo-local snapshot:\n"
        f"{tasks_summary}"
    )
    return response[:ASK_MAX_RESPONSE_CHARS].rstrip()


async def stream_repo_local_answer(question: str) -> None:
    """Send the repo-local fallback answer as a single bounded reply."""
    await safe_send(answer_repo_local_question(question))


class AskTimeoutError(RuntimeError):
    """Raised when the bounded /ask provider exceeds its timeout."""


class LLMProvider:
    """Bounded single-shot LLM provider used by /ask."""

    def __init__(self, backend_name: str | None = None) -> None:
        name = backend_name or os.environ.get(ASK_BACKEND_ENV, "codex")
        self.backend_name = name.strip().lower() or "codex"

    async def query(self, question: str, context: str) -> list[str]:
        """Return bounded response chunks for one operator question."""
        bounded_question = " ".join(question.split())[:ASK_MAX_QUESTION_CHARS]
        if self.backend_name == "repo_local":
            response = answer_repo_local_question(bounded_question)
            return [response[:ASK_MAX_RESPONSE_CHARS].rstrip()] if response.strip() else []
        return await self._query_codex_cli(bounded_question, context)

    async def _query_codex_cli(self, question: str, context: str) -> list[str]:
        prompt = build_codex_ask_prompt(question, context)
        command = build_codex_ask_command(prompt)
        timeout_sec = get_ask_timeout_sec()

        try:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise RuntimeError(f"/ask backend failed to start Codex: {exc}") from exc

        stdout = process.stdout
        if stdout is None:
            process.kill()
            process.wait()
            raise RuntimeError("/ask backend returned no stdout pipe")

        chunks: list[str] = []
        chunks_sent_chars = 0
        buffer = ""
        deadline = time.monotonic() + timeout_sec

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                if buffer.strip() and chunks_sent_chars < ASK_MAX_RESPONSE_CHARS:
                    rendered = buffer.rstrip()
                    chunks.append(rendered)
                raise AskTimeoutError(f"⏱ /ask timed out after {timeout_sec}s")
            try:
                line = await asyncio.wait_for(asyncio.to_thread(stdout.readline), timeout=remaining)
            except asyncio.TimeoutError as exc:
                process.kill()
                process.wait()
                if buffer.strip() and chunks_sent_chars < ASK_MAX_RESPONSE_CHARS:
                    rendered = buffer.rstrip()
                    chunks.append(rendered)
                raise AskTimeoutError(f"⏱ /ask timed out after {timeout_sec}s") from exc

            if line == "":
                break

            if chunks_sent_chars >= ASK_MAX_RESPONSE_CHARS:
                continue

            allowed = ASK_MAX_RESPONSE_CHARS - chunks_sent_chars
            snippet = line[:allowed]
            if not snippet:
                continue
            buffer += snippet

            if len(buffer) >= ASK_STREAM_CHUNK_CHARS or buffer.endswith("\n\n"):
                rendered = buffer.rstrip()
                if rendered:
                    chunks.append(rendered)
                    chunks_sent_chars += len(rendered)
                buffer = ""

        exit_code = await asyncio.to_thread(process.wait)
        if buffer.strip() and chunks_sent_chars < ASK_MAX_RESPONSE_CHARS:
            rendered = buffer.rstrip()
            chunks.append(rendered)
            chunks_sent_chars += len(rendered)

        if exit_code != 0:
            raise RuntimeError(f"/ask Codex exited with code {exit_code}")

        return chunks


def get_ask_timeout_sec() -> int:
    """Return the bounded timeout for /ask Codex runs."""
    raw = os.environ.get(ASK_CODEX_TIMEOUT_ENV, "").strip()
    if not raw:
        return ASK_CODEX_TIMEOUT_SEC
    try:
        value = int(raw)
    except ValueError:
        return ASK_CODEX_TIMEOUT_SEC
    return max(15, value)


def get_ask_backend() -> dict[str, object]:
    """Resolve the operator /ask backend from repo-local configuration."""
    backends = {
        "codex": build_codex_cli_ask_backend,
        "repo_local": build_repo_local_ask_backend,
    }
    backend_name = os.environ.get(ASK_BACKEND_ENV, "codex").strip().lower() or "codex"
    backend_factory = backends.get(backend_name, build_codex_cli_ask_backend)
    return backend_factory()


def build_codex_cli_ask_backend() -> dict[str, object]:
    """Return the Codex-backed /ask contract with swappable backend metadata."""
    return {
        "name": "codex_cli",
        "mode": "single_shot_stream",
        "max_question_chars": ASK_MAX_QUESTION_CHARS,
        "max_response_chars": ASK_MAX_RESPONSE_CHARS,
        "stream_answer": stream_codex_cli_answer,
    }


def _read_bounded_text(path: Path, max_chars: int) -> str:
    """Read a bounded text payload from disk if available."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars].strip()
    except OSError:
        return ""


def _read_recent_log_excerpt(max_lines: int = ASK_LOG_CONTEXT_LINES) -> str:
    """Return the most recent Ralph log excerpt for /ask context."""
    if not LOG_DIR.exists():
        return "No logs/ directory found"

    log_files = sorted(LOG_DIR.glob("ralph_*.log"), reverse=True)
    if not log_files:
        return "No ralph log files found"

    latest = log_files[0]
    try:
        lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"Error reading {latest.name}: {exc}"
    excerpt = lines[-max_lines:] if len(lines) > max_lines else lines
    body = "\n".join(excerpt).strip()
    return f"{latest.name}\n{body}".strip()


def _build_code_snippet(path: Path, start_line: int, end_line: int) -> str:
    """Render a small file snippet for prompt grounding."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return f"File: {path}\n(unavailable)"

    if not lines:
        return f"File: {path}\n(empty file)"

    line_count = len(lines)
    start_idx = max(0, start_line - 1)
    if start_idx >= line_count:
        start_idx = max(0, line_count - ASK_CODE_SNIPPET_MAX_LINES)
    end_idx = min(line_count, max(end_line, start_idx + ASK_CODE_SNIPPET_MAX_LINES))
    snippet_lines = lines[start_idx:end_idx][:ASK_CODE_SNIPPET_MAX_LINES]
    if not snippet_lines:
        return f"File: {path}\n(no snippet lines available)"
    numbered = "\n".join(f"{start_idx + index + 1}: {line}" for index, line in enumerate(snippet_lines))
    return f"File: {path}\n{numbered}".strip()


def build_ask_code_snippets() -> str:
    """Return small repo snippets relevant to operator /ask answers."""
    snippets = [
        _build_code_snippet(PROJECT_DIR / "scripts" / "ralph_bot.py", 1498, 1524),
        _build_code_snippet(PROJECT_DIR / "ralph.sh", 1, 20),
    ]
    return "\n\n".join(snippet for snippet in snippets if snippet).strip()


def build_ask_project_context() -> str:
    """Build the repo-local snapshot injected into the /ask provider context."""
    state = read_state()
    state_payload = json.dumps(state, indent=2, ensure_ascii=False)[:600].strip()
    tasks_payload = _read_bounded_text(TASKS_FILE, ASK_TASKS_CONTEXT_MAX_CHARS) or "No tasks.json found"
    recent_logs = _read_recent_log_excerpt()
    code_snippets = build_ask_code_snippets()
    context_lines = [
        f"Project directory: {PROJECT_DIR}",
        "",
        "project state:",
        state_payload or "{}",
        "",
        "tasks.json (task truth):",
        tasks_payload,
        "",
        "recent logs:",
        recent_logs,
        "",
        "relevant code snippets:",
        code_snippets or "No code snippets available",
        "",
        "progress.md is narrative-only context and should not override tasks.json.",
    ]
    return "\n".join(context_lines).strip()[:ASK_CONTEXT_MAX_CHARS]


def build_codex_ask_prompt(question: str, context: str) -> str:
    """Render the bounded prompt for Codex-backed /ask analysis."""
    bounded_question = " ".join(question.split())[:ASK_MAX_QUESTION_CHARS]
    return (
        "You are answering a Telegram /ask operator question about the current Ralph repository.\n"
        "Work from the current repo state in the working directory.\n"
        "Read code, tasks.json, and lightweight context as needed before answering.\n"
        "Use tasks.json as task truth. Use progress.md only as narrative context if needed.\n"
        "Keep the answer concise, concrete, and operationally useful.\n"
        "If something is uncertain, say so explicitly.\n\n"
        "Operator question:\n"
        f"{bounded_question}\n\n"
        "Repo-local context:\n"
        f"{context}\n"
    )


def build_codex_ask_command(prompt: str) -> list[str]:
    """Build the Codex CLI command for one bounded /ask run."""
    command = ["codex", "exec", "-s", "danger-full-access"]
    model = os.environ.get(ASK_CODEX_MODEL_ENV, "").strip()
    if model:
        command.extend(["-m", model])
    command.append(prompt)
    return command


async def emit_ask_stream_chunk(chunk: str) -> None:
    """Send one streamed /ask chunk after trimming empty content."""
    text = chunk.strip()
    if not text:
        return
    await send_split_message(text)


async def stream_codex_cli_answer(question: str) -> None:
    """Run a bounded Codex CLI analysis and stream its output back to Telegram."""
    try:
        await safe_send("🧠 Codex is analyzing the repo...")
        provider = LLMProvider("codex")
        context = build_ask_project_context()
        chunks = await provider.query(question, context)
    except AskTimeoutError as exc:
        await safe_send(str(exc))
        return
    except RuntimeError as exc:
        await safe_send(f"❌ {exc}")
        return

    for chunk in chunks:
        await emit_ask_stream_chunk(chunk)

    if not chunks:
        await safe_send("⚠️ /ask returned an empty Codex response")


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
    return shared_load_tasks_data(PROJECT_DIR)


def save_tasks_data(data: dict) -> None:
    """Persist tasks.json with stable formatting."""
    shared_save_tasks_data(PROJECT_DIR, data)


def mutate_tasks_data(mutator):
    """Load, mutate, and persist tasks.json under one shared lock."""
    return shared_mutate_tasks_data(PROJECT_DIR, mutator)


def get_audit_summary(task_id: str) -> str:
    """Return a human-readable audit summary for a task."""
    result = subprocess.run(
        ["python3", str(RALPH_DIR / "scripts" / "audit_artifact.py"), "show", task_id],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
    )
    output = (result.stdout or result.stderr).strip()
    return output or f"Audit artifact not found for {task_id}"


def get_audit_last_summary(limit: int = 10) -> str:
    """Return a compact summary for the most recent audit artifacts."""
    result = subprocess.run(
        ["python3", str(RALPH_DIR / "scripts" / "audit_artifact.py"), "list", str(limit)],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
    )
    output = (result.stdout or result.stderr).strip()
    return output or "No audit artifacts found."


def get_trust_report_summary() -> str:
    """Return aggregate trust report across audit artifacts."""
    result = subprocess.run(
        ["python3", str(RALPH_DIR / "scripts" / "audit_artifact.py"), "report"],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
    )
    output = (result.stdout or result.stderr).strip()
    return output or "No trust report available."


def get_task_summary(tasks_path: Path) -> dict:
    """Summarize task progress for /status and /progress."""
    if not tasks_path.exists():
        return {
            "done_total": 0,
            "all_total": 0,
            "pct": 0,
            "phases": [],
            "blocked": [],
            "next": [],
        }

    data = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks = data.get("tasks", [])
    phases_meta = data.get("phases", {})
    done_ids = {task.get("id") for task in tasks if task.get("status") in COMPLETED_TASK_STATUSES}
    done_total = sum(1 for task in tasks if task.get("status") in COMPLETED_TASK_STATUSES)
    all_total = len(tasks)
    pct = int(round((done_total / all_total) * 100)) if all_total else 0

    phase_ids = [phase_id for phase_id in phases_meta.keys()]
    for task in tasks:
        phase_id = str(task.get("phase", "?"))
        if phase_id not in phase_ids:
            phase_ids.append(phase_id)

    phase_rows = []
    blocked = []
    next_tasks = []
    for phase_id in phase_ids:
        phase_tasks = [task for task in tasks if str(task.get("phase", "?")) == phase_id]
        total = len(phase_tasks)
        done = sum(1 for task in phase_tasks if task.get("status") in COMPLETED_TASK_STATUSES)
        filled = int(round((done / total) * 8)) if total else 0
        bar = ("█" * filled) + ("░" * (8 - filled))

        if total == 0:
            icon = "⬜"
        elif done == total:
            icon = "✅"
        elif any(task.get("status") in {"running", "in_progress", "pending"} for task in phase_tasks):
            icon = "🔄"
        else:
            icon = "⬜"

        name = str(phases_meta.get(phase_id, {}).get("name", phase_id))
        phase_rows.append(
            {
                "phase_id": phase_id,
                "bar": bar,
                "done": done,
                "total": total,
                "name": name,
                "icon": icon,
            }
        )

        for task in phase_tasks:
            if task.get("status") != "pending":
                continue
            deps = task.get("dependencies", []) or []
            unmet = [dep for dep in deps if dep not in done_ids]
            if unmet:
                blocked.append(str(task.get("id")))
            else:
                next_tasks.append(str(task.get("id")))

    return {
        "done_total": done_total,
        "all_total": all_total,
        "pct": pct,
        "phases": phase_rows,
        "blocked": blocked,
        "next": next_tasks[:5],
    }


def prepare_html_message(text: str) -> str:
    """Escape plain text while preserving the bot's small allowed HTML subset."""
    if any(tag in text for tag in ("<b>", "</b>", "<pre>", "</pre>", "<code>", "</code>")):
        return text
    return html.escape(text)


def set_send_context(command_name: str) -> None:
    """Record the active command for Telegram diagnostics."""
    global CURRENT_SEND_CONTEXT
    CURRENT_SEND_CONTEXT = command_name


def log_bot(message: str) -> None:
    """Emit a structured bot log line."""
    print(f"[bot] {message}", file=sys.stderr)


def _read_pid_value(path: Path) -> int | None:
    """Return a numeric pid/pgid from a pidfile when present."""
    try:
        value = int(path.read_text().strip())
    except (OSError, ValueError):
        return None
    return value if value > 1 else None


def terminate_tracked_processes(reason: str) -> list[str]:
    """Best-effort teardown for tracked Ralph/Codex processes."""
    killed: list[str] = []
    killed_pgids: set[int] = set()
    pgid_file = PROJECT_DIR / "ralph_codex.pgid"
    pgid = _read_pid_value(pgid_file)
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGTERM)
            killed.append(f"pgid:{pgid}")
            killed_pgids.add(pgid)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            log_bot(f"{reason}: failed SIGTERM for codex pgid {pgid}: {exc}")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except (PermissionError, OSError) as exc:
            log_bot(f"{reason}: failed SIGKILL for codex pgid {pgid}: {exc}")
        pgid_file.unlink(missing_ok=True)

    for pf in ["ralph_codex.pid", "ralph_main.pid"]:
        pid_file = PROJECT_DIR / pf
        pid = _read_pid_value(pid_file)
        if pid is None:
            pid_file.unlink(missing_ok=True)
            continue
        try:
            live_pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError, OSError, ValueError):
            live_pgid = None
        if live_pgid is not None and live_pgid > 1 and live_pgid not in killed_pgids:
            try:
                os.killpg(live_pgid, signal.SIGTERM)
                killed.append(f"{pf}.pgid:{live_pgid}")
                killed_pgids.add(live_pgid)
            except (ProcessLookupError, PermissionError, OSError) as exc:
                log_bot(f"{reason}: failed SIGTERM for {pf} pgid {live_pgid}: {exc}")
            try:
                os.killpg(live_pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except (PermissionError, OSError) as exc:
                log_bot(f"{reason}: failed SIGKILL for {pf} pgid {live_pgid}: {exc}")
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(f"{pf}:{pid}")
        except (ProcessLookupError, PermissionError, OSError) as exc:
            log_bot(f"{reason}: failed SIGTERM for {pf}={pid}: {exc}")
        for sig_name in ("TERM", "KILL"):
            try:
                subprocess.run(["pkill", f"-{sig_name}", "-P", str(pid)], capture_output=True, check=False)
            except OSError as exc:
                log_bot(f"{reason}: failed pkill -{sig_name} -P {pid}: {exc}")
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except (PermissionError, OSError) as exc:
            log_bot(f"{reason}: failed SIGKILL for {pf}={pid}: {exc}")
        pid_file.unlink(missing_ok=True)

    if killed:
        log_bot(f"{reason}: terminated tracked processes: {', '.join(killed)}")
    else:
        log_bot(f"{reason}: no tracked processes to terminate")
    return killed


def _begin_handler_logging(handler_name: str) -> None:
    """Reset per-handler send counters before command execution."""
    global CURRENT_HANDLER_NAME, CURRENT_HANDLER_SEND_COUNT
    CURRENT_HANDLER_NAME = handler_name
    CURRENT_HANDLER_SEND_COUNT = 0


def _finish_handler_logging() -> int:
    """Clear per-handler logging context and return sent message count."""
    global CURRENT_HANDLER_NAME, CURRENT_HANDLER_SEND_COUNT
    sent_count = CURRENT_HANDLER_SEND_COUNT
    CURRENT_HANDLER_NAME = ""
    CURRENT_HANDLER_SEND_COUNT = 0
    return sent_count


def get_update_user_label(update: dict) -> str:
    """Return normalized user label for message or callback updates."""
    message_user = update.get("message", {}).get("from", {})
    callback_user = update.get("callback_query", {}).get("from", {})
    user = message_user or callback_user
    user_id = user.get("id")
    return f"user_{user_id}" if user_id is not None else "user_unknown"


async def execute_logged_handler(
    command_name: str,
    user_label: str,
    handler_name: str,
    handler_coro,
) -> None:
    """Run a bot handler with timing, send counting, and traceback logging."""
    set_send_context(command_name)
    log_bot(f"CMD: {command_name} from {user_label}")
    log_bot(f"Handler: {handler_name} START")
    started_at = time.perf_counter()
    _begin_handler_logging(handler_name)
    try:
        await handler_coro
    except Exception:  # noqa: BLE001
        duration_s = time.perf_counter() - started_at
        sent_count = _finish_handler_logging()
        log_bot(f"Handler: {handler_name} ERROR (took {duration_s:.3f}s, sent {sent_count} messages)")
        exc_type, exc_value, _ = sys.exc_info()
        if exc_type is not None:
            log_bot(f"Exception in {handler_name}: {exc_type.__name__}: {exc_value}")
        traceback.print_exc(file=sys.stderr)
        raise

    duration_s = time.perf_counter() - started_at
    sent_count = _finish_handler_logging()
    log_bot(f"Handler: {handler_name} END (took {duration_s:.3f}s, sent {sent_count} messages)")


def _read_error_body(exc: Exception) -> str:
    if not hasattr(exc, "read"):
        return ""
    try:
        body = exc.read()
    except Exception:  # noqa: BLE001
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _log_send_error(exc: Exception, payload: dict[str, object]) -> None:
    """Emit structured send diagnostics for Telegram 4xx/5xx cases."""
    global LAST_SEND_ERROR
    text = str(payload.get("text", ""))
    preview = text[:300].replace("\n", "\\n")
    body = _read_error_body(exc)
    LAST_SEND_ERROR = {
        "command_name": CURRENT_SEND_CONTEXT or "unknown",
        "parse_mode": str(payload.get("parse_mode", "")),
        "payload_length": len(text),
        "payload_preview": preview,
        "error": f"{exc.__class__.__name__}: {exc}",
        "error_body": body,
    }
    print(
        "[bot] Send error: "
        f"command={LAST_SEND_ERROR['command_name']} "
        f"parse_mode={LAST_SEND_ERROR['parse_mode']} "
        f"payload_length={LAST_SEND_ERROR['payload_length']} "
        f"payload_preview={LAST_SEND_ERROR['payload_preview']} "
        f"error={LAST_SEND_ERROR['error']} "
        f"error_body={body}",
        file=sys.stderr,
    )


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

    global LAST_SEND_ERROR, CURRENT_HANDLER_SEND_COUNT
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
            LAST_SEND_ERROR = None
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{API}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=TELEGRAM_TIMEOUT_SEC)
            if CURRENT_HANDLER_NAME:
                CURRENT_HANDLER_SEND_COUNT += 1
        except Exception as exc1:  # noqa: BLE001
            _log_send_error(exc1, payload)
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
                urllib.request.urlopen(req, timeout=TELEGRAM_TIMEOUT_SEC)
                if CURRENT_HANDLER_NAME:
                    CURRENT_HANDLER_SEND_COUNT += 1
            except Exception as exc2:  # noqa: BLE001
                _log_send_error(exc2, retry_payload)


async def safe_send(text: str, reply_markup: dict | None = None) -> None:
    """Best-effort message send; never raises to caller."""
    try:
        await send_message(prepare_html_message(text), reply_markup=reply_markup)
    except Exception as exc:  # noqa: BLE001
        log_bot(f"Send error: {exc}")


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
        write_state_payload(STATE_FILE, payload)
    except OSError as exc:
        print(f"[bot] State write error: {exc}", file=sys.stderr)


async def cmd_status() -> None:
    """Send status overview."""
    reset_stale_state()  # R20-02: auto-heal before showing status
    sync_active_project_runtime()
    state = read_state()
    summary = get_task_summary(TASKS_FILE)
    status = state.get("status", "idle")
    icons = {"idle": "⏸", "running": "🏃", "waiting_human": "🚨", "stopped": "⏹"}
    icon = icons.get(status, "❓")

    lines = [f"{icon} Status: <b>{status}</b>"]
    lines.append(f"📁 Project: <b>{html.escape(ACTIVE_PROJECT_NAME)}</b>")
    lines.append(f"📍 Path: <code>{html.escape(str(PROJECT_DIR))}</code>")
    if state.get("current_task"):
        lines.append(f"📋 Task: {state['current_task']}")
    if state.get("current_phase_step"):
        lines.append(f"🔄 Step: {state['current_phase_step']}")
    if state.get("last_update"):
        lines.append(f"🕐 Updated: {state['last_update']}")
    if state.get("message"):
        lines.append(f"💬 {state['message']}")
    lines.append(
        f"📊 {summary['done_total']}/{summary['all_total']} ({summary['pct']}%) complete"
    )

    await safe_send("\n".join(lines))


async def cmd_projects() -> None:
    """List registered projects with active marker and short status/progress."""
    try:
        registry = load_projects_registry()
    except ValueError as exc:
        await safe_send(f"❌ Cannot read projects registry: {html.escape(str(exc))}")
        return

    active_name = str(registry.get("active_project", ACTIVE_PROJECT_NAME))
    projects = registry.get("projects", {})
    if not isinstance(projects, dict) or not projects:
        await safe_send("No registered projects found")
        return

    lines = ["📚 <b>Projects</b>"]
    for project_name in sorted(projects):
        payload = projects.get(project_name)
        if not isinstance(payload, dict):
            continue

        raw_path = payload.get("path")
        if not isinstance(raw_path, str):
            continue

        project_path = Path(raw_path).expanduser()
        snapshot = get_project_snapshot(project_name, project_path)
        marker = "👉" if project_name == active_name else "•"
        status = html.escape(str(snapshot.get("status", "unknown")))
        done_total = int(snapshot.get("done_total", 0))
        all_total = int(snapshot.get("all_total", 0))
        pct = int(snapshot.get("pct", 0))
        path_text = html.escape(str(project_path.resolve()))
        current_task = snapshot.get("current_task")

        lines.append(
            f"{marker} <b>{html.escape(project_name)}</b> [{status}] {done_total}/{all_total} ({pct}%)"
        )
        lines.append(f"   <code>{path_text}</code>")
        if current_task:
            lines.append(f"   task: {html.escape(str(current_task))}")

    await send_split_message("\n".join(lines))


async def cmd_switch(project_name: str) -> None:
    """Switch active bot context to a different registered project."""
    normalized_name = project_name.strip()
    if not normalized_name:
        await safe_send("Usage: /switch <project>")
        return

    state = read_state()
    if state.get("status") in {"running", "waiting_human", "paused"} or get_live_ralph_pid():
        await safe_send("⚠️ Cannot switch project while Ralph is active. Stop the current run first.")
        return

    try:
        registry = load_projects_registry()
    except ValueError as exc:
        await safe_send(f"❌ Cannot read projects registry: {html.escape(str(exc))}")
        return

    projects = registry.get("projects", {})
    if not isinstance(projects, dict):
        await safe_send("❌ Projects registry is invalid")
        return

    payload = projects.get(normalized_name)
    if not isinstance(payload, dict):
        await safe_send(f"❌ Unknown project: {html.escape(normalized_name)}")
        return

    raw_path = payload.get("path")
    if not isinstance(raw_path, str):
        await safe_send(f"❌ Project {html.escape(normalized_name)} has no valid path")
        return

    project_dir = Path(raw_path).expanduser().resolve()
    if not (project_dir / "tasks.json").exists():
        await safe_send(f"❌ No tasks.json in {html.escape(str(project_dir))}")
        return

    registry["active_project"] = normalized_name
    save_projects_registry(registry)
    apply_project_runtime(project_dir, project_name=normalized_name)

    summary = get_task_summary(TASKS_FILE)
    await safe_send(
        "\n".join(
            [
                f"🔀 Switched to <b>{html.escape(normalized_name)}</b>",
                f"📍 <code>{html.escape(str(PROJECT_DIR))}</code>",
                f"📊 {summary['done_total']}/{summary['all_total']} ({summary['pct']}%) complete",
            ]
        )
    )


async def cmd_start_task(task_id: str) -> None:
    """Start single task."""
    global ralph_process
    reset_stale_state()
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
    reset_stale_state()
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
    existing_pid = get_live_ralph_pid()
    if existing_pid is not None:
        await safe_send(f"⚠️ Ralph уже работает (PID: {existing_pid}). Используй /stop сначала.")
        return
    state = read_state()
    if state.get("status") == "running":
        await safe_send("⚠️ Ralph already running. /stop first.")
        return
    if state.get("status") == "blocked":
        await safe_send("⚠️ Ralph is blocked. Use /reset or /unblock first.")
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
        killed_pids = terminate_tracked_processes("Force stop")

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


async def cmd_exit() -> None:
    """Force-stop Ralph via legacy /exit command."""
    await cmd_stop(force=True)


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
        phase_pattern = re.compile(rf"^{re.escape(phase)}-(\d+)$")

        def add_task(data: dict) -> str:
            tasks = data.get("tasks", [])
            next_num = 1
            for task in tasks:
                match = phase_pattern.match(str(task.get("id", "")))
                if match:
                    next_num = max(next_num, int(match.group(1)) + 1)

            task_id = f"{phase}-{next_num:02d}"
            tasks.append(
                {
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
            )
            data["tasks"] = tasks
            return task_id

        task_id = mutate_tasks_data(add_task)
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
        def remove_task(data: dict) -> bool:
            tasks = data.get("tasks", [])
            filtered_tasks = [task for task in tasks if task.get("id") != task_id]
            if len(filtered_tasks) == len(tasks):
                return False
            data["tasks"] = filtered_tasks
            return True

        removed = mutate_tasks_data(remove_task)
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error saving tasks.json: {exc}")
        return

    if not removed:
        await safe_send(f"❌ Task {task_id} not found")
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
        done_count = sum(1 for task in phase_tasks if task.get("status") in COMPLETED_TASK_STATUSES)
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
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=ARTICLE_GENERATION_TIMEOUT_SEC,
                    )
                except asyncio.TimeoutError:
                    await safe_send(
                        f"❌ Таймаут: скрипт работал дольше {ARTICLE_GENERATION_TIMEOUT_SEC} секунд"
                    )
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


async def cmd_progress() -> None:
    """Show phase-by-phase progress bars from tasks.json."""
    if not TASKS_FILE.exists():
        await safe_send("No tasks.json found")
        return

    try:
        summary = get_task_summary(TASKS_FILE)
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Error reading tasks.json: {exc}")
        return

    lines = [
        f"📊 Ralph Progress — {summary['done_total']}/{summary['all_total']} done ({summary['pct']}%)",
        "",
    ]

    for row in summary["phases"]:
        lines.append(
            f"{row['phase_id']} {row['bar']}  {row['done']}/{row['total']}   {row['name']:<16} {row['icon']}"
        )

    if summary["blocked"]:
        lines.append("")
        lines.append("⏳ Blocked: " + ", ".join(summary["blocked"]))

    if summary["next"]:
        lines.append("")
        lines.append("🔜 Next: " + ", ".join(summary["next"]))

    await safe_send("\n".join(lines))


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


async def cmd_audit(task_id: str) -> None:
    """Show latest audit summary for a task."""
    set_send_context("/audit")
    task_id = task_id.strip()
    if not task_id:
        await safe_send("Usage: /audit <task_id>")
        return
    try:
        summary = get_audit_summary(task_id)
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Audit error: {exc}")
        return
    await send_split_message(summary)


async def cmd_audit_last(limit_text: str) -> None:
    """Show compact summary for the most recent audit artifacts."""
    set_send_context("/audit_last")
    raw = limit_text.strip() if limit_text else ""
    try:
        limit = int(raw) if raw else 10
    except ValueError:
        limit = 10
    if limit <= 0:
        limit = 10
    try:
        summary = get_audit_last_summary(limit)
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Audit-last error: {exc}")
        return
    await send_split_message(summary)


async def cmd_trust_report() -> None:
    """Show aggregate trust report from audit artifacts."""
    set_send_context("/trust_report")
    try:
        summary = get_trust_report_summary()
    except Exception as exc:  # noqa: BLE001
        await safe_send(f"❌ Trust report error: {exc}")
        return
    await send_split_message(summary)


async def cmd_ask(prompt: str) -> None:
    """Handle /ask through the bounded LLM provider with injected context."""
    set_send_context("/ask")
    question = prompt.strip()
    if not question:
        await safe_send(ASK_USAGE_TEXT)
        return
    provider = LLMProvider()
    context = build_ask_project_context()

    if provider.backend_name == "codex":
        await safe_send("🧠 Codex is analyzing the repo...")

    try:
        chunks = await provider.query(question, context)
    except AskTimeoutError as exc:
        await safe_send(str(exc))
        return
    except RuntimeError as exc:
        await safe_send(f"❌ {exc}")
        return

    for chunk in chunks:
        await emit_ask_stream_chunk(chunk)

    if not chunks:
        await safe_send("⚠️ /ask returned an empty response")


async def cmd_reload() -> None:
    """Hot-reload bot helpers and command handlers from source."""
    set_send_context("/reload")
    try:
        module = load_bot_module_from_source()
        apply_hot_reload(module)
        await safe_send("♻️ Bot modules reloaded")
    except Exception as exc:  # noqa: BLE001
        error_text = html.escape(str(exc))[:500] or exc.__class__.__name__
        await safe_send(f"❌ Reload failed: {error_text}")


async def cmd_help() -> None:
    """Send help text."""
    set_send_context("/help")
    await safe_send(
        "🤖 <b>Ralph Bot</b>\n\n"
        "/status — current state\n"
        "/projects — list registered projects\n"
        "/switch <name> — switch active project context\n"
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
        "/exit — force kill immediately\n"
        "/done [task_id] — mark task done\n"
        "/redo [task_id] [notes] — redo task\n"
        "/timeout [seconds] — set timeout override\n"
        "/comment text — instruction for next task\n"
        "/log [N] — last N lines from ralph execution log\n"
        "/progress — phase progress bars\n"
        "/tail [N] — last N lines of live codex output\n"
        "/audit &lt;task_id&gt; — latest trust audit summary\n"
        "/audit_last [N] — latest audit summaries\n"
        "/trust_report — trust summary across audit artifacts\n"
        "/ask &lt;question&gt; — bounded operator question entrypoint\n"
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
        user_label = get_update_user_label(update)
        if data == "stop":
            await execute_logged_handler("callback:stop", user_label, "cmd_stop", cmd_stop(force=False))
        elif data == "stop_now":
            await execute_logged_handler("callback:stop_now", user_label, "cmd_stop", cmd_stop(force=True))
        elif data.startswith("skip:"):
            task_id = data.split(":", 1)[1]
            async def skip_handler() -> None:
                write_control("skip", task_id)
                await safe_send(f"⏭ Skipping {task_id}")

            await execute_logged_handler("callback:skip", user_label, "callback_skip", skip_handler())
        return

    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]
    args = parts[1] if len(parts) > 1 else ""
    user_label = get_update_user_label(update)

    handler_name = ""
    handler_coro = None

    if cmd == "/status":
        handler_name = "cmd_status"
        handler_coro = cmd_status()
    elif cmd == "/projects":
        handler_name = "cmd_projects"
        handler_coro = cmd_projects()
    elif cmd == "/switch":
        handler_name = "cmd_switch"
        handler_coro = cmd_switch(args)
    elif cmd == "/tasks":
        handler_name = "tasks_summary"
        handler_coro = safe_send(get_tasks_summary(args or None))
    elif cmd == "/plan":
        handler_name = "cmd_plan"
        handler_coro = cmd_plan()
    elif cmd == "/article":
        handler_name = "cmd_article"
        handler_coro = cmd_article(args.strip())
    elif cmd == "/add" and args:
        handler_name = "cmd_add"
        handler_coro = cmd_add(args)
    elif cmd == "/rm":
        handler_name = "cmd_rm"
        handler_coro = cmd_rm(args)
    elif cmd == "/pause":
        handler_name = "cmd_pause"
        handler_coro = cmd_pause()
    elif cmd == "/resume":
        handler_name = "cmd_resume"
        handler_coro = cmd_resume()
    elif cmd == "/start" and args:
        handler_name = "cmd_start_task"
        handler_coro = cmd_start_task(args)
    elif cmd == "/phase" and args:
        handler_name = "cmd_start_phase"
        handler_coro = cmd_start_phase(args)
    elif cmd == "/auto":
        handler_name = "cmd_start_auto"
        handler_coro = cmd_start_auto()
    elif cmd == "/stop":
        handler_name = "cmd_stop"
        handler_coro = cmd_stop(force="now" in args)
    elif cmd == "/exit":
        handler_name = "cmd_exit"
        handler_coro = cmd_exit()
    elif cmd == "/done":
        handler_name = "cmd_done"
        handler_coro = cmd_done(args.strip())
    elif cmd == "/redo" and args:
        args_parts = args.split(maxsplit=1)
        task_id = args_parts[0]
        notes = args_parts[1] if len(args_parts) > 1 else ""
        handler_name = "cmd_redo"
        handler_coro = cmd_redo(task_id, notes)
    elif cmd == "/timeout":
        handler_name = "cmd_timeout"
        handler_coro = cmd_timeout(args.strip())
    elif cmd == "/comment" and args:
        async def comment_handler() -> None:
            write_control("comment", args)
            await safe_send(f"📝 Comment saved for next task:\n{args}")

        handler_name = "comment_save"
        handler_coro = comment_handler()
    elif cmd == "/log":
        async def log_handler() -> None:
            n = int(args) if args.isdigit() else 15
            log_text = html.escape(get_log_tail(n))
            await safe_send(f"<pre>{log_text}</pre>")

        handler_name = "cmd_log"
        handler_coro = log_handler()
    elif cmd == "/progress":
        handler_name = "cmd_progress"
        handler_coro = cmd_progress()
    elif cmd == "/tail":
        handler_name = "cmd_tail"
        handler_coro = cmd_tail(int(args) if args.isdigit() else 20)
    elif cmd == "/audit":
        handler_name = "cmd_audit"
        handler_coro = cmd_audit(args)
    elif cmd == "/audit_last":
        handler_name = "cmd_audit_last"
        handler_coro = cmd_audit_last(args)
    elif cmd == "/trust_report":
        handler_name = "cmd_trust_report"
        handler_coro = cmd_trust_report()
    elif cmd == "/ask":
        handler_name = "cmd_ask"
        handler_coro = cmd_ask(args.lstrip())
    elif cmd == "/cost":
        handler_name = "cmd_cost"
        handler_coro = cmd_cost()
    elif cmd == "/stats":
        handler_name = "cmd_stats"
        handler_coro = cmd_stats()
    elif cmd == "/limits":
        handler_name = "cmd_limits"
        handler_coro = cmd_limits()
    elif cmd == "/diff":
        handler_name = "cmd_diff"
        handler_coro = cmd_diff()
    elif cmd == "/reload":
        handler_name = "cmd_reload"
        handler_coro = cmd_reload()
    elif cmd == "/help" or (cmd == "/start" and not args):
        handler_name = "cmd_help"
        handler_coro = cmd_help()
    else:
        handler_name = "unknown_command"
        handler_coro = safe_send("Unknown command. Try /help")

    await execute_logged_handler(cmd, user_label, handler_name, handler_coro)


async def poll_updates() -> None:
    """Long-polling loop for Telegram updates."""
    import urllib.request

    offset = 0
    consecutive_errors = 0
    backoff_seconds = TELEGRAM_POLL_BACKOFF_INITIAL_SEC
    while True:
        try:
            url = f"{API}/getUpdates?offset={offset}&timeout={TELEGRAM_POLL_TIMEOUT_SEC}"
            resp = urllib.request.urlopen(url, timeout=TELEGRAM_POLL_REQUEST_TIMEOUT_SEC)
            data = json.loads(resp.read())

            if consecutive_errors > 0:
                await safe_send(f"⚠️ Bot reconnected after {consecutive_errors} poll errors")
                consecutive_errors = 0
                backoff_seconds = TELEGRAM_POLL_BACKOFF_INITIAL_SEC

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                try:
                    await handle_update(update)
                except Exception as exc:  # noqa: BLE001
                    log_bot(f"Handler error: {exc}")
                    traceback.print_exc(file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            consecutive_errors += 1
            delay = min(backoff_seconds, TELEGRAM_POLL_BACKOFF_MAX_SEC)
            log_bot(f"Poll error #{consecutive_errors}, retry in {delay}s: {exc}")
            await asyncio.sleep(delay)
            backoff_seconds = min(backoff_seconds * 2, TELEGRAM_POLL_BACKOFF_MAX_SEC)


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
                terminate_tracked_processes("Crash recovery")
            try:
                raw_state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
            except json.JSONDecodeError as exc:
                log_bot(f"Crash recovery failed to read {STATE_FILE.name}: malformed JSON: {exc}")
                raw_state = {}
            except OSError as exc:
                log_bot(f"Crash recovery failed to read {STATE_FILE.name}: {exc}")
                raw_state = {}

            current_task = str(raw_state.get("current_task") or "").strip()
            if raw_state.get("status") == "running" and current_task:
                try:
                    update_result = subprocess.run(
                        ["python3", "scripts/update_task.py", current_task, "pending"],
                        cwd=str(PROJECT_DIR),
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    if update_result.stderr.strip():
                        log_bot(f"Crash recovery update_task stderr for {current_task}: {update_result.stderr.strip()}")
                except subprocess.CalledProcessError as exc:
                    stderr = (exc.stderr or "").strip()
                    stdout = (exc.stdout or "").strip()
                    detail = stderr or stdout or str(exc)
                    log_bot(f"Crash recovery failed to reset task {current_task} to pending: {detail}")
                except OSError as exc:
                    log_bot(f"Crash recovery failed to launch update_task for {current_task}: {exc}")

                rollback_performed = False
                if destructive_rollback_enabled():
                    for rollback_args in CRASH_ROLLBACK_COMMANDS:
                        rollback_cmd = ["git", "-C", str(PROJECT_DIR), *rollback_args]
                        try:
                            rollback_result = subprocess.run(
                                rollback_cmd,
                                check=False,
                                capture_output=True,
                                text=True,
                            )
                            if rollback_result.returncode != 0:
                                detail = (rollback_result.stderr or rollback_result.stdout or "").strip()
                                log_bot(
                                    f"Crash recovery rollback command failed ({' '.join(rollback_cmd)}): "
                                    f"{detail or f'exit {rollback_result.returncode}'}"
                                )
                            else:
                                rollback_performed = True
                        except OSError as exc:
                            log_bot(f"Crash recovery rollback launch failed ({' '.join(rollback_cmd)}): {exc}")
                else:
                    log_bot(f"Crash recovery rollback skipped. {DESTRUCTIVE_ROLLBACK_POLICY_NOTICE}")

                if rollback_performed:
                    await safe_send(
                        f"🔄 Ralph crashed during {current_task}. Task reset to pending, changes rolled back."
                    )
                else:
                    await safe_send(
                        f"🔄 Ralph crashed during {current_task}. Task reset to pending. "
                        "Worktree rollback skipped by policy."
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
    reset_stale_state()

    await safe_send("🤖 Ralph Bot started! Type /help for commands.")
    try:
        await asyncio.gather(poll_updates(), watch_state())
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    finally:
        await safe_send("🔴 Ralph Bot going offline.")


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
    PROJECT_DIR, ACTIVE_PROJECT_NAME = resolve_initial_project_context(args.project_dir)

    if not (PROJECT_DIR / "tasks.json").exists():
        print(f"❌ No tasks.json in {PROJECT_DIR}")
        print("Run ralph-init.sh first or pass --project-dir")
        sys.exit(1)

    # Update all paths that depend on PROJECT_DIR
    apply_project_runtime(PROJECT_DIR, project_name=ACTIVE_PROJECT_NAME)

    load_dotenv(PROJECT_DIR / ".env")
    TOKEN = os.environ.get("RALPH_TELEGRAM_TOKEN", "")
    CHAT_ID = os.environ.get("RALPH_TELEGRAM_CHAT_ID", "")
    API = f"https://api.telegram.org/bot{TOKEN}"

    print("🤖 Ralph Bot")
    print(f"   RALPH_DIR:   {RALPH_DIR}")
    print(f"   PROJECT:     {ACTIVE_PROJECT_NAME}")
    print(f"   PROJECT_DIR: {PROJECT_DIR}")
    print(f"   Tasks:       {TASKS_FILE}")
    print("   caffeinate: enabled during auto mode")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🔴 Ralph Bot stopped.")
