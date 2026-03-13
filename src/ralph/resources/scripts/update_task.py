#!/usr/bin/env python3
"""Update task status in tasks.json."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_project_dir() -> Path:
    """Get project directory from env or default to script parent."""
    env = os.environ.get("RALPH_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).parent.parent


PROJECT_DIR = get_project_dir()
TASKS_FILE = PROJECT_DIR / "tasks.json"


def main():
    if len(sys.argv) < 3:
        print("Usage: update_task.py <task_id> <status> [revision_notes]")
        sys.exit(1)
    task_id, status = sys.argv[1], sys.argv[2]
    notes = sys.argv[3] if len(sys.argv) > 3 else None
    data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["status"] = status
            if status == "done":
                task["completed_at"] = datetime.now(timezone.utc).isoformat()
            if notes:
                task["revision_notes"] = notes
            break
    else:
        print(f"Task {task_id} not found")
        sys.exit(1)
    TASKS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {task_id} -> {status}")


if __name__ == "__main__":
    main()
