#!/usr/bin/env python3
"""Update task status in tasks.json."""
import sys
from datetime import datetime, timezone

try:
    from ralph_common import mutate_tasks_data, resolve_project_dir
except ImportError:
    from scripts.ralph_common import mutate_tasks_data, resolve_project_dir


COMPLETED_STATUSES = {"done", "verified_done"}


def main():
    if len(sys.argv) < 3:
        print("Usage: update_task.py <task_id> <status> [revision_notes]")
        sys.exit(1)
    project_dir = resolve_project_dir(script_path=__file__)
    task_id, status = sys.argv[1], sys.argv[2]
    notes = sys.argv[3] if len(sys.argv) > 3 else None
    try:
        def apply_update(data):
            for task in data["tasks"]:
                if task["id"] == task_id:
                    task["status"] = status
                    if status in COMPLETED_STATUSES:
                        task["completed_at"] = datetime.now(timezone.utc).isoformat()
                    else:
                        task["completed_at"] = None
                    if notes:
                        task["revision_notes"] = notes
                    return
            raise LookupError(task_id)

        mutate_tasks_data(project_dir, apply_update)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except LookupError:
        print(f"Task {task_id} not found")
        sys.exit(1)
    print(f"Updated {task_id} -> {status}")


if __name__ == "__main__":
    main()
