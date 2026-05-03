#!/usr/bin/env python3
"""Transactional read/write service for tasks.json."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable

try:
    from ralph_common import (
        COMPLETED_STATUSES,
        _load_tasks_data_unlocked,
        _save_tasks_data_unlocked,
        locked_path,
        resolve_project_dir,
        tasks_file_path,
    )
except ImportError:
    from scripts.ralph_common import (
        COMPLETED_STATUSES,
        _load_tasks_data_unlocked,
        _save_tasks_data_unlocked,
        locked_path,
        resolve_project_dir,
        tasks_file_path,
    )


class TaskStateService:
    """Single entrypoint for transactional tasks.json access."""

    def __init__(self, project_dir):
        self.project_dir = resolve_project_dir(str(project_dir) if project_dir else None, script_path=__file__)
        self.path = tasks_file_path(self.project_dir)

    def read(self) -> dict[str, Any]:
        with locked_path(self.path):
            return _load_tasks_data_unlocked(self.path)

    def write(self, data: dict[str, Any]) -> None:
        with locked_path(self.path):
            _save_tasks_data_unlocked(self.path, data)

    def mutate(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        with locked_path(self.path):
            data = _load_tasks_data_unlocked(self.path)
            result = mutator(data)
            _save_tasks_data_unlocked(self.path, data)
            return result

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        tasks = self.read().get("tasks", [])
        return next((task for task in tasks if task.get("id") == task_id), None)

    def select_simple_pending(self, *, limit: int = 3) -> list[str]:
        return [
            str(task["id"])
            for task in self.read().get("tasks", [])
            if task.get("status") == "pending" and task.get("complexity") == "simple"
        ][:limit]

    def build_progress_report(self, *, pending_limit: int = 5) -> str:
        tasks = self.read()["tasks"]
        done = sum(1 for task in tasks if task.get("status") in COMPLETED_STATUSES)
        total = len(tasks)
        lines = [f"  Total: {done}/{total} tasks done"]
        for phase in sorted({str(task["phase"]) for task in tasks}):
            phase_tasks = [task for task in tasks if str(task["phase"]) == phase]
            phase_done = sum(1 for task in phase_tasks if task.get("status") in COMPLETED_STATUSES)
            lines.append(f"  Phase {phase}: {phase_done}/{len(phase_tasks)}")
        pending = [task for task in tasks if task.get("status") == "pending"]
        if pending:
            lines.append("")
            lines.append("Next pending:")
            for task in pending[:pending_limit]:
                lines.append(f"  {task['id']} [{task['priority']}] {task['title']}")
        return "\n".join(lines)

    def validate_requested_task(self, task_id: str) -> str:
        data = self.read()
        tasks = data.get("tasks", [])
        task = next((item for item in tasks if item.get("id") == task_id), None)
        if task is None:
            raise LookupError(f"❌ Requested task not found: {task_id}")

        status = str(task.get("status", ""))
        if status != "pending":
            raise ValueError(f"❌ Requested task {task_id} is not runnable: status={status}")

        unmet = [
            dep
            for dep in task.get("dependencies", [])
            if next(
                (
                    candidate
                    for candidate in tasks
                    if candidate.get("id") == dep and candidate.get("status") in COMPLETED_STATUSES
                ),
                None,
            )
            is None
        ]
        if unmet:
            raise ValueError(
                f"❌ Requested task {task_id} is not runnable: unmet dependencies: {', '.join(unmet)}"
            )
        return f"🎯 Requested task {task_id} is runnable and will be executed directly"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-requested")
    validate_parser.add_argument("task_id")

    select_parser = subparsers.add_parser("select-simple-pending")
    select_parser.add_argument("--limit", type=int, default=3)

    progress_parser = subparsers.add_parser("print-progress")
    progress_parser.add_argument("--pending-limit", type=int, default=5)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    service = TaskStateService(args.project)

    try:
        if args.command == "validate-requested":
            print(service.validate_requested_task(args.task_id))
            return 0
        if args.command == "select-simple-pending":
            for task_id in service.select_simple_pending(limit=args.limit):
                print(task_id)
            return 0
        if args.command == "print-progress":
            print(service.build_progress_report(pending_limit=args.pending_limit))
            return 0
    except (LookupError, ValueError) as exc:
        print(str(exc))
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
