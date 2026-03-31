#!/usr/bin/env python3
"""Update task status in tasks.json."""
import sys
from datetime import datetime, timezone

try:
    from ralph_common import load_tasks_data, resolve_project_dir, save_tasks_data
except ImportError:
    from scripts.ralph_common import load_tasks_data, resolve_project_dir, save_tasks_data


COMPLETED_STATUSES = {"done", "verified_done"}


def main():
    if len(sys.argv) < 3:
        print("Usage: update_task.py <task_id> <status> [revision_notes]")
        sys.exit(1)
    project_dir = resolve_project_dir(script_path=__file__)
    task_id, status = sys.argv[1], sys.argv[2]
    notes = sys.argv[3] if len(sys.argv) > 3 else None
    try:
        data = load_tasks_data(project_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["status"] = status
            if status in COMPLETED_STATUSES:
                task["completed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                task["completed_at"] = None
            if notes:
                task["revision_notes"] = notes
            break
    else:
        print(f"Task {task_id} not found")
        sys.exit(1)
    save_tasks_data(project_dir, data)
    print(f"Updated {task_id} -> {status}")


if __name__ == "__main__":
    main()
