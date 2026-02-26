#!/usr/bin/env python3
"""Append entry to progress.md."""
import sys
from datetime import datetime, timezone
from pathlib import Path

PROGRESS_FILE = Path(__file__).parent.parent / "progress.md"


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
