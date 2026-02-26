#!/usr/bin/env python3
"""Pick next pending task from tasks.json."""
import argparse
import json
import os
import sys
from pathlib import Path


def get_project_dir() -> Path:
    """Get project directory from env or default to script parent."""
    env = os.environ.get("RALPH_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).parent.parent


PROJECT_DIR = get_project_dir()
TASKS_FILE = PROJECT_DIR / "tasks.json"
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_tasks():
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def pick_next(tasks, *, task_id=None, phase=None):
    done = {t["id"] for t in tasks if t["status"] == "done"}
    candidates = [
        t for t in tasks
        if t["status"] == "pending"
        and all(d in done for d in t.get("dependencies", []))
    ]
    if task_id:
        return next((t for t in candidates if t["id"] == task_id), None)
    if phase:
        candidates = [t for t in candidates if str(t["phase"]) == str(phase)]
    if not candidates:
        return None
    candidates.sort(key=lambda t: PRIORITY_ORDER.get(t.get("priority", "low"), 9))
    return candidates[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default=None)
    parser.add_argument("--phase", default=None)
    args = parser.parse_args()
    data = load_tasks()
    task = pick_next(data["tasks"], task_id=args.task, phase=args.phase)
    if task is None:
        print("null")
        sys.exit(0)
    print(json.dumps(task, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
