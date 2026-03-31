#!/usr/bin/env python3
"""Shared project, task, control, and task-truth helpers for Ralph."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONTROL_ACTION = "continue"
COMPLETED_STATUSES = {"done", "verified_done"}
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
BOOKKEEPING_EXACT = {
    "tasks.json",
    "progress.md",
    "audit_report.md",
    "ralph_state.json",
    "ralph_control.json",
    "ralph_alerts.log",
    "ralph_main.pid",
    "ralph_codex.pid",
    "ralph_codex.pgid",
    ".ralph/memory/recent.md",
    ".ralph/memory/decisions.md",
    ".ralph/memory/patterns.md",
}
BOOKKEEPING_PREFIXES = (
    "logs/",
    ".pytest_cache/",
    "__pycache__/",
    ".ralph/audit/",
    "ralph/audit/",
)
DOC_KEYWORDS = (
    "readme",
    "documentation",
    "docs/",
    "postmortem",
    "prompt_version",
    "changelog",
)
DEFAULT_CODER_TIMEOUT_SEC = 900
DEFAULT_LEAD_TIMEOUT_SEC = 300
DEFAULT_TELEGRAM_TIMEOUT_SEC = 10
DEFAULT_TELEGRAM_POLL_TIMEOUT_SEC = 30
DEFAULT_TELEGRAM_POLL_REQUEST_TIMEOUT_SEC = 35
DEFAULT_TELEGRAM_POLL_BACKOFF_INITIAL_SEC = 5
DEFAULT_TELEGRAM_POLL_BACKOFF_MAX_SEC = 60
DEFAULT_ARTICLE_TIMEOUT_SEC = 300
DEFAULT_CODEX_RETRY_DELAYS = (60, 120, 300)
DEFAULT_RATE_LIMIT_PAUSE_SEC = 1800
DESTRUCTIVE_ROLLBACK_REVIEWED = "reviewed"
DESTRUCTIVE_ROLLBACK_ENV = "RALPH_DESTRUCTIVE_ROLLBACK"
DESTRUCTIVE_ROLLBACK_POLICY_NOTICE = (
    f"Set {DESTRUCTIVE_ROLLBACK_ENV}={DESTRUCTIVE_ROLLBACK_REVIEWED} after review to allow destructive rollback."
)
CRASH_ROLLBACK_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("reset", "HEAD", "--", "."),
    ("checkout", "--", "."),
)


def env_int(name: str, default: int) -> int:
    """Return integer env override or a safe default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def get_telegram_timeout_sec() -> int:
    """Shared Telegram transport timeout for bot sends and notifications."""
    return env_int("RALPH_TELEGRAM_TIMEOUT_SEC", DEFAULT_TELEGRAM_TIMEOUT_SEC)


def get_telegram_poll_timeout_sec() -> int:
    """Shared Telegram long-poll timeout."""
    return env_int("RALPH_TELEGRAM_POLL_TIMEOUT_SEC", DEFAULT_TELEGRAM_POLL_TIMEOUT_SEC)


def get_telegram_poll_request_timeout_sec() -> int:
    """Shared HTTP timeout for Telegram long-poll requests."""
    return env_int(
        "RALPH_TELEGRAM_POLL_REQUEST_TIMEOUT_SEC",
        DEFAULT_TELEGRAM_POLL_REQUEST_TIMEOUT_SEC,
    )


def get_telegram_poll_backoff_initial_sec() -> int:
    """Shared initial backoff after Telegram poll failures."""
    return env_int(
        "RALPH_TELEGRAM_POLL_BACKOFF_INITIAL_SEC",
        DEFAULT_TELEGRAM_POLL_BACKOFF_INITIAL_SEC,
    )


def get_telegram_poll_backoff_max_sec() -> int:
    """Shared max backoff after Telegram poll failures."""
    return env_int(
        "RALPH_TELEGRAM_POLL_BACKOFF_MAX_SEC",
        DEFAULT_TELEGRAM_POLL_BACKOFF_MAX_SEC,
    )


def get_article_generation_timeout_sec() -> int:
    """Shared timeout for article generation subprocesses."""
    return env_int("RALPH_ARTICLE_TIMEOUT_SEC", DEFAULT_ARTICLE_TIMEOUT_SEC)


def destructive_rollback_enabled() -> bool:
    """Allow destructive crash rollback only when explicitly reviewed."""
    return os.environ.get(DESTRUCTIVE_ROLLBACK_ENV, "").strip().lower() == DESTRUCTIVE_ROLLBACK_REVIEWED


def resolve_project_dir(explicit: str | None = None, *, script_path: str | Path | None = None) -> Path:
    """Resolve Ralph project dir from explicit arg, cwd, env, then script location."""
    if explicit:
        return Path(explicit).resolve()

    cwd = Path.cwd().resolve()
    if (cwd / "tasks.json").exists():
        return cwd

    env = os.environ.get("RALPH_PROJECT_DIR")
    if env:
        return Path(env).resolve()

    if script_path is not None:
        return Path(script_path).resolve().parent.parent

    return cwd


def tasks_file_path(project_dir: Path) -> Path:
    return project_dir / "tasks.json"


def control_file_path(project_dir: Path) -> Path:
    return project_dir / "ralph_control.json"


def format_tasks_data_error(path: Path, exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        detail = "file not found"
    elif isinstance(exc, json.JSONDecodeError):
        detail = f"malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    elif isinstance(exc, ValueError):
        detail = str(exc)
    else:
        detail = str(exc) or exc.__class__.__name__
    return f"tasks.json error [{path}]: {detail}"


def load_tasks_data(project_dir: Path) -> dict[str, Any]:
    """Load tasks.json through one validated code path."""
    path = tasks_file_path(project_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("tasks.json must contain a JSON object")
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("tasks.json must contain a top-level 'tasks' list")
        return data
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(format_tasks_data_error(path, exc)) from exc


def save_tasks_data(project_dir: Path, data: dict[str, Any]) -> None:
    """Persist tasks.json through one validated code path."""
    if not isinstance(data, dict):
        raise ValueError("tasks payload must be a dict")
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("tasks payload must contain a top-level 'tasks' list")
    tasks_file_path(project_dir).write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _normalize_control_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    normalized = dict(data)
    action = normalized.get("action", DEFAULT_CONTROL_ACTION)
    if not isinstance(action, str) or not action.strip():
        action = DEFAULT_CONTROL_ACTION
    comment = normalized.get("comment")
    if comment is None:
        comment = normalized.get("value", "")
    if not isinstance(comment, str):
        comment = str(comment)
    normalized["action"] = action
    normalized["comment"] = comment
    normalized.pop("value", None)
    return normalized


def read_control_data(project_dir: Path) -> dict[str, Any]:
    """Load and normalize ralph_control.json."""
    path = control_file_path(project_dir)
    if not path.exists():
        return {"action": DEFAULT_CONTROL_ACTION, "comment": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"ralph_control.json warning [{path}]: "
            f"{'malformed JSON' if isinstance(exc, json.JSONDecodeError) else 'read failed'}: {exc}",
            file=sys.stderr,
        )
        data = {}
    return _normalize_control_data(data)


def write_control_data(project_dir: Path, action: str, comment: str = "") -> None:
    """Persist normalized control-file schema."""
    path = control_file_path(project_dir)
    payload = read_control_data(project_dir) if path.exists() else {}
    payload.update(
        {
            "action": action or DEFAULT_CONTROL_ACTION,
            "comment": comment or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    path.write_text(json.dumps(_normalize_control_data(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def clear_control_action(project_dir: Path) -> None:
    """Reset control action while preserving file ownership to shared IO."""
    path = control_file_path(project_dir)
    if not path.exists():
        return
    write_control_data(project_dir, DEFAULT_CONTROL_ACTION, "")


def consume_control_comment(project_dir: Path) -> str:
    """Return and clear operator comment payload."""
    path = control_file_path(project_dir)
    data = read_control_data(project_dir)
    comment = str(data.get("comment", "")).strip()
    if path.exists() and comment:
        data["comment"] = ""
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(_normalize_control_data(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return comment


def completed_task_ids(tasks: list[dict[str, Any]]) -> set[str]:
    return {str(task.get("id")) for task in tasks if task.get("status") in COMPLETED_STATUSES}


def runnable_reason(task: dict[str, Any], tasks: list[dict[str, Any]]) -> tuple[bool, str]:
    status = str(task.get("status", ""))
    if status != "pending":
        return False, f"status={status}"

    done_ids = completed_task_ids(tasks)
    unmet = [dep for dep in task.get("dependencies", []) if dep not in done_ids]
    if unmet:
        return False, "unmet dependencies: " + ", ".join(unmet)
    return True, "pending and dependencies satisfied"


def pick_next_task(
    tasks: list[dict[str, Any]],
    *,
    task_id: str | None = None,
    phase: str | None = None,
) -> dict[str, Any] | None:
    done_ids = completed_task_ids(tasks)
    candidates = [
        task
        for task in tasks
        if task.get("status") == "pending"
        and all(dep in done_ids for dep in task.get("dependencies", []))
    ]
    if task_id:
        return next((task for task in candidates if task.get("id") == task_id), None)
    if phase is not None:
        candidates = [task for task in candidates if str(task.get("phase")) == str(phase)]
    if not candidates:
        return None
    candidates.sort(key=lambda task: PRIORITY_ORDER.get(str(task.get("priority", "low")), 9))
    return candidates[0]


def explain_non_runnable(tasks: list[dict[str, Any]], *, phase: str | None = None) -> dict[str, Any]:
    done_ids = completed_task_ids(tasks)
    unresolved = [task for task in tasks if task.get("status") not in COMPLETED_STATUSES]
    if phase is not None:
        unresolved = [task for task in unresolved if str(task.get("phase")) == str(phase)]
    pending = [task for task in unresolved if task.get("status") == "pending"]
    blocked_pending = []
    for task in pending:
        unmet = [dep for dep in task.get("dependencies", []) if dep not in done_ids]
        if unmet:
            blocked_pending.append(
                {
                    "id": task.get("id", ""),
                    "title": task.get("title", ""),
                    "unmet_dependencies": unmet,
                }
            )
    blocked_by_status = [
        {
            "id": task.get("id", ""),
            "title": task.get("title", ""),
            "status": task.get("status", ""),
        }
        for task in unresolved
        if task.get("status") != "pending"
    ]
    reason = "no_pending"
    if blocked_pending:
        reason = "blocked_dependencies"
    elif blocked_by_status:
        reason = "blocked_statuses"
    return {
        "has_pending": bool(pending),
        "has_unresolved": bool(unresolved),
        "blocked_pending": blocked_pending,
        "blocked_by_status": blocked_by_status,
        "reason": reason,
    }


def normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/").lstrip("./")


def is_bookkeeping_file(path: str) -> bool:
    normalized = normalize_path(path)
    if normalized in BOOKKEEPING_EXACT:
        return True
    return any(normalized.startswith(prefix) for prefix in BOOKKEEPING_PREFIXES)


def is_bookkeeping(path: str) -> bool:
    return is_bookkeeping_file(path)


def extract_path_candidates(task: dict[str, Any]) -> list[str]:
    texts: list[str] = [task.get("title", ""), task.get("description", "")]
    texts.extend(task.get("acceptance_criteria", []) or [])
    texts.extend(task.get("test_steps", []) or [])
    combined = "\n".join(texts)
    matches = re.findall(
        r"((?:scripts|templates|tests|docs)/[A-Za-z0-9_./-]+\.(?:py|md|json|sh|ts|tsx|js)|(?:README|PROMPT_CHANGELOG|AGENTS(?:_[A-Z]+)?|BLOG_DRAFTS|progress)\.md)",
        combined,
    )
    seen: set[str] = set()
    result: list[str] = []
    for match in matches:
        path = normalize_path(match)
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def extract_command_tokens(task: dict[str, Any]) -> list[str]:
    texts: list[str] = [task.get("title", ""), task.get("description", "")]
    texts.extend(task.get("acceptance_criteria", []) or [])
    tokens = re.findall(r"/([a-z][a-z0-9_]*)", "\n".join(texts).lower())
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def extract_expected_test_names(task: dict[str, Any]) -> list[str]:
    texts = [task.get("title", ""), task.get("description", "")]
    texts.extend(task.get("acceptance_criteria", []) or [])
    texts.extend(task.get("test_steps", []) or [])
    names = re.findall(r"\b(test_[a-zA-Z0-9_]+)\b", "\n".join(texts))
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def detect_task_class(
    task: dict[str, Any],
    expected_paths: list[str],
    command_tokens: list[str],
    expected_tests: list[str],
) -> str:
    title = task.get("title", "").lower()
    description = task.get("description", "").lower()
    combined = "\n".join(
        [title, description, *[item.lower() for item in task.get("acceptance_criteria", []) or []]]
    )
    if any(path.startswith("templates/") for path in expected_paths):
        return "template"
    if any(path.startswith("scripts/") for path in expected_paths):
        return "script"
    if command_tokens and ("bot" in title or "команда" in title or "telegram" in combined):
        return "command"
    if title.startswith("tests:") or expected_tests or "pytest" in combined:
        return "tests-only"
    if (
        "re-audit" in combined
        and "report" in combined
        and any(keyword in combined for keyword in ("verified", "partial", "false positive", "unclear"))
    ):
        return "reaudit-report"
    if any(path.startswith("docs/") for path in expected_paths) or any(path.endswith(".md") for path in expected_paths):
        return "docs-only"
    if any(keyword in combined for keyword in DOC_KEYWORDS):
        return "docs-only"
    return "implementation"


def infer_task_context(task: dict[str, Any]) -> tuple[str, list[str], list[str], list[str]]:
    expected_paths = extract_path_candidates(task)
    command_tokens = extract_command_tokens(task)
    expected_tests = extract_expected_test_names(task)
    task_class = detect_task_class(task, expected_paths, command_tokens, expected_tests)
    return task_class, expected_paths, command_tokens, expected_tests


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shared Ralph control-file helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("control-read")
    read_parser.add_argument("--project-dir", default=None)

    write_parser = subparsers.add_parser("control-write")
    write_parser.add_argument("action")
    write_parser.add_argument("comment", nargs="?", default="")
    write_parser.add_argument("--project-dir", default=None)

    clear_parser = subparsers.add_parser("control-clear")
    clear_parser.add_argument("--project-dir", default=None)

    consume_parser = subparsers.add_parser("control-consume-comment")
    consume_parser.add_argument("--project-dir", default=None)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    project_dir = resolve_project_dir(getattr(args, "project_dir", None))

    if args.command == "control-read":
        data = read_control_data(project_dir)
        print(data.get("action", DEFAULT_CONTROL_ACTION))
        print(data.get("comment", ""))
        return 0

    if args.command == "control-write":
        write_control_data(project_dir, args.action, args.comment)
        return 0

    if args.command == "control-clear":
        clear_control_action(project_dir)
        return 0

    if args.command == "control-consume-comment":
        comment = consume_control_comment(project_dir)
        if comment:
            print(comment)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
