#!/usr/bin/env python3
"""Append entry to progress.md."""
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
PROGRESS_FILE = PROJECT_DIR / "progress.md"


def main():
    if len(sys.argv) < 3:
        print("Usage: update_progress.py <task_id> <note>")
        sys.exit(1)
    task_id = sys.argv[1]
    note = " ".join(sys.argv[2:])
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"- **{task_id}** ({ts}): {note}\n"
    content = PROGRESS_FILE.read_text(encoding="utf-8") if PROGRESS_FILE.exists() else ""
    content += entry
    PROGRESS_FILE.write_text(content, encoding="utf-8")
    print(f"Progress updated: {task_id}")


if __name__ == "__main__":
    main()
