#!/usr/bin/env python3
"""Pick next pending task from tasks.json."""
import argparse
from datetime import datetime
import json
import sys
from pathlib import Path
try:
    from ralph_common import (
        explain_non_runnable,
        is_task_safe_for_auto,
        load_tasks_data,
        pick_next_task,
        resolve_project_dir,
        task_hygiene_warnings,
        unsafe_task_reason,
    )
except ImportError:
    from scripts.ralph_common import (
        explain_non_runnable,
        is_task_safe_for_auto,
        load_tasks_data,
        pick_next_task,
        resolve_project_dir,
        task_hygiene_warnings,
        unsafe_task_reason,
    )


pick_next = pick_next_task
TARGET_FILES_LIMIT = 3


def log_selection_warning(project_dir: Path, warning: str) -> None:
    log_dir = project_dir / "logs"
    if not log_dir.exists():
        return
    stamp = datetime.now()
    log_file = log_dir / f"ralph_{stamp:%Y-%m-%d}.log"
    message = f"[ralph] {stamp:%H:%M:%S} ⚠️ Task selection warning: {warning}\n"
    try:
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(message)
    except OSError:
        return


def build_scope_warnings(task):
    target_files = [str(item).strip() for item in (task.get("target_files") or []) if str(item).strip()]
    if len(target_files) <= TARGET_FILES_LIMIT:
        return []
    return [
        (
            "scope-too-wide: task declares "
            f"{len(target_files)} target_files (limit: {TARGET_FILES_LIMIT}). "
            "Consider splitting into narrower tasks."
        )
    ]


def pick_next_auto_safe_task(tasks):
    skipped = []
    task = pick_next_task(tasks)
    while task is not None and not is_task_safe_for_auto(task):
        skipped.append(
            {
                "id": str(task.get("id", "")).strip(),
                "reason": unsafe_task_reason(task),
                "warnings": task_hygiene_warnings(task),
            }
        )
        remaining = [item for item in tasks if item is not task]
        task = pick_next_task(remaining)
        tasks = remaining
    return task, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default=None)
    parser.add_argument("--phase", default=None)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--auto-safe", action="store_true")
    args = parser.parse_args()
    project_dir = resolve_project_dir(script_path=__file__)
    try:
        data = load_tasks_data(project_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    if args.explain:
        explained = explain_non_runnable(data["tasks"], phase=args.phase)
        if args.auto_safe and args.task is None and args.phase is None:
            safe_task, skipped = pick_next_auto_safe_task(data["tasks"])
            if safe_task is None and skipped and explained.get("reason") == "no_pending":
                explained["reason"] = "unsafe_pending"
                explained["unsafe_pending"] = skipped
        print(json.dumps(explained, indent=2, ensure_ascii=False))
        sys.exit(0)
    skipped = []
    if args.auto_safe and args.task is None and args.phase is None:
        task, skipped = pick_next_auto_safe_task(data["tasks"])
    else:
        task = pick_next_task(data["tasks"], task_id=args.task, phase=args.phase)
    if task is None:
        for item in skipped:
            print(f"TASK_SKIPPED_UNSAFE {item['id']} {item['reason']}", file=sys.stderr)
        print("null")
        sys.exit(0)
    for item in skipped:
        print(f"TASK_SKIPPED_UNSAFE {item['id']} {item['reason']}", file=sys.stderr)
    warnings = build_scope_warnings(task)
    if warnings:
        for warning in warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
            log_selection_warning(project_dir, warning)
    payload = dict(task)
    payload["scope_too_wide"] = bool(warnings)
    payload["selection_warnings"] = warnings
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
