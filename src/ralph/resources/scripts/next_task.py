#!/usr/bin/env python3
"""Pick next pending task from tasks.json."""
import argparse
import json
import sys
try:
    from ralph_common import explain_non_runnable, load_tasks_data, pick_next_task, resolve_project_dir
except ImportError:
    from scripts.ralph_common import explain_non_runnable, load_tasks_data, pick_next_task, resolve_project_dir


pick_next = pick_next_task


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
    print(json.dumps(task, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
