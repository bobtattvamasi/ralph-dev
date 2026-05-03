#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

try:
    from ralph_common import load_tasks_data, resolve_project_dir, task_hygiene_warnings
except ImportError:
    from scripts.ralph_common import load_tasks_data, resolve_project_dir, task_hygiene_warnings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--include-non-pending", action="store_true")
    parser.add_argument("--fail-on-warn", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    project_dir = resolve_project_dir(script_path=__file__)
    try:
        data = load_tasks_data(project_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    tasks = data.get("tasks", [])
    warn_count = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id", "")).strip()
        if args.task_id and task_id != args.task_id:
            continue
        if not args.include_non_pending and str(task.get("status", "")).strip() != "pending":
            continue
        for code, reason in task_hygiene_warnings(task):
            print(f"TASK_HYGIENE_WARN {task_id} {code} {reason}")
            warn_count += 1

    if args.fail_on_warn and warn_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
