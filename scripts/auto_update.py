#!/usr/bin/env python3
"""Auto-update task status in tasks.json and append progress entry."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COMPLETED_STATUSES = {"done", "verified_done"}


def atomic_write(path: Path, content: str) -> None:
    """Write file atomically to avoid partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_name = tmp.name
    Path(tmp_name).replace(path)


def run_git(project_dir: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run git command in project root."""
    return subprocess.run(
        ["git", *args],
        cwd=project_dir,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Update tasks.json and progress.md, then commit.")
    parser.add_argument("task_id", help="Task id, e.g. R1-09")
    parser.add_argument("status", help="New task status, e.g. done/pending")
    parser.add_argument("comment", nargs="*", help="Optional comment")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent
    tasks_path = project_dir / "tasks.json"
    progress_path = project_dir / "progress.md"

    if not tasks_path.exists():
        print(f"tasks.json not found: {tasks_path}", file=sys.stderr)
        return 1

    try:
        data: dict[str, Any] = json.loads(tasks_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to parse tasks.json: {exc}", file=sys.stderr)
        return 1

    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        print("Invalid tasks.json: 'tasks' must be a list", file=sys.stderr)
        return 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    comment = " ".join(args.comment).strip()

    target: dict[str, Any] | None = None
    for task in tasks:
        if task.get("id") == args.task_id:
            target = task
            break

    if target is None:
        print(f"Task not found: {args.task_id}", file=sys.stderr)
        return 1

    target["status"] = args.status
    if args.status in COMPLETED_STATUSES:
        target["completed_at"] = today
    else:
        target.pop("completed_at", None)

    # Set dependent tasks to pending (tasks that list task_id in dependencies).
    for task in tasks:
        deps = task.get("dependencies", [])
        if isinstance(deps, list) and args.task_id in deps:
            task["status"] = "pending"
            task.pop("completed_at", None)

    # Persist tasks.json preserving structure (stable JSON formatting).
    atomic_write(tasks_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    # Append progress entry.
    title = target.get("title", args.task_id)
    lines = [
        f"### {today} — Завершена задача {args.task_id} — {title}",
        f"- Статус: {args.status}",
    ]
    if comment:
        lines.append(f"- Комментарий: {comment}")
    entry = "\n".join(lines) + "\n\n"

    existing = progress_path.read_text(encoding="utf-8") if progress_path.exists() else ""
    atomic_write(progress_path, existing + entry)

    # Commit updates.
    add_res = run_git(project_dir, ["add", "tasks.json", "progress.md"])
    if add_res.returncode != 0:
        print(add_res.stderr.strip() or "git add failed", file=sys.stderr)
        return 1

    commit_msg = f"feat({args.task_id}): auto update status and progress"
    commit_res = run_git(project_dir, ["commit", "-m", commit_msg])
    if commit_res.returncode != 0:
        stderr = commit_res.stderr.strip()
        stdout = commit_res.stdout.strip()
        msg = stderr or stdout or "git commit failed"
        print(msg, file=sys.stderr)
        return 1

    print(f"Updated {args.task_id} -> {args.status} and committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
