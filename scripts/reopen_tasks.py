#!/usr/bin/env python3
"""Safely reopen or reclassify a single task for manual review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

try:
    from ralph_common import load_tasks_data, resolve_project_dir, save_tasks_data
except ImportError:
    from scripts.ralph_common import load_tasks_data, resolve_project_dir, save_tasks_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely reopen one task")
    parser.add_argument("--project-dir", default=None, help="Project directory")
    parser.add_argument("--task", required=True, help="Task ID")
    parser.add_argument(
        "--to-status",
        required=True,
        choices=["pending", "needs_human_review", "partial"],
        help="Target status",
    )
    parser.add_argument("--note", default="", help="Operator note")
    args = parser.parse_args()

    project_dir = resolve_project_dir(args.project_dir)
    data = load_tasks_data(project_dir)
    task = next((item for item in data.get("tasks", []) if item.get("id") == args.task), None)
    if task is None:
        print(f"Task not found: {args.task}")
        return 1

    now = datetime.now(timezone.utc).isoformat()
    old_status = str(task.get("status", "unknown"))
    task["status"] = args.to_status
    task["completed_at"] = None

    note = args.note.strip() or f"Operator status change {old_status} -> {args.to_status}"
    entry = f"{now}: reopen -> {args.to_status} — {note}"
    previous = str(task.get("revision_notes", "")).strip()
    task["revision_notes"] = f"{previous}\n{entry}".strip() if previous else entry

    save_tasks_data(project_dir, data)
    print(f"Updated {args.task}: {old_status} -> {args.to_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
