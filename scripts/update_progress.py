#!/usr/bin/env python3
"""Append entry to progress.md."""
import sys
from datetime import datetime, timezone

try:
    from ralph_common import resolve_project_dir
except ImportError:
    from scripts.ralph_common import resolve_project_dir


def main():
    if len(sys.argv) < 3:
        print("Usage: update_progress.py <task_id> <note>")
        sys.exit(1)
    project_dir = resolve_project_dir(script_path=__file__)
    progress_file = project_dir / "progress.md"
    task_id = sys.argv[1]
    note = " ".join(sys.argv[2:])
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"- **{task_id}** ({ts}): {note}\n"
    content = progress_file.read_text(encoding="utf-8") if progress_file.exists() else ""
    content += entry
    progress_file.write_text(content, encoding="utf-8")
    print(f"Progress updated: {task_id}")


if __name__ == "__main__":
    main()
