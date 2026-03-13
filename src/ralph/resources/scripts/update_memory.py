#!/usr/bin/env python3
"""Update .ralph/memory/recent.md with latest task summary."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List


def get_project_dir() -> Path:
    env = os.environ.get("RALPH_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).parent.parent


def split_entries(body: str) -> List[str]:
    lines = body.splitlines()
    entries: List[List[str]] = []
    current: List[str] = []

    for line in lines:
        if line.startswith("### "):
            if current:
                entries.append(current)
            current = [line]
        elif current:
            current.append(line)

    if current:
        entries.append(current)

    return ["\n".join(chunk).strip() for chunk in entries if chunk]


def main() -> int:
    if len(sys.argv) < 5:
        print("Usage: update_memory.py <task_id> <title> <files_changed> <result> [notes]", file=sys.stderr)
        return 1

    task_id = (sys.argv[1] or "").strip()
    title = (sys.argv[2] or "").strip()
    files_changed = (sys.argv[3] or "").strip()
    result = (sys.argv[4] or "").strip()
    notes = " ".join(sys.argv[5:]).strip() if len(sys.argv) > 5 else ""

    if not task_id or not title or not files_changed or not result:
        print("Error: empty required argument", file=sys.stderr)
        return 1

    project_dir = get_project_dir()
    memory_dir = project_dir / ".ralph" / "memory"
    recent_file = memory_dir / "recent.md"
    memory_dir.mkdir(parents=True, exist_ok=True)

    if recent_file.exists():
        existing = recent_file.read_text(encoding="utf-8")
    else:
        existing = "# Recent Task History\n\n"

    header = "# Recent Task History"
    body = existing
    if existing.startswith(header):
        body = existing[len(header) :].lstrip("\n")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_entry = "\n".join(
        [
            f"### {task_id}: {title}",
            f"- Files: {files_changed}",
            f"- Result: {result}",
            f"- Notes: {notes}",
            f"- Time: {timestamp}",
        ]
    )

    entries = split_entries(body)
    entries.insert(0, new_entry)
    entries = entries[:5]

    out = header + "\n\n" + "\n\n".join(entries).strip() + "\n"
    recent_file.write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
