#!/usr/bin/env python3
"""Pick next pending task from tasks.json."""
import argparse
from datetime import datetime
import json
import sys
from pathlib import Path
try:
    from ralph_common import explain_non_runnable, load_tasks_data, pick_next_task, resolve_project_dir
except ImportError:
    from scripts.ralph_common import explain_non_runnable, load_tasks_data, pick_next_task, resolve_project_dir


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default=None)
    parser.add_argument("--phase", default=None)
    parser.add_argument("--explain", action="store_true")
    args = parser.parse_args()
    project_dir = resolve_project_dir(script_path=__file__)
    try:
        data = load_tasks_data(project_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    if args.explain:
        print(json.dumps(explain_non_runnable(data["tasks"], phase=args.phase), indent=2, ensure_ascii=False))
        sys.exit(0)
    task = pick_next_task(data["tasks"], task_id=args.task, phase=args.phase)
    if task is None:
        print("null")
        sys.exit(0)
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
