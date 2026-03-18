#!/usr/bin/env python3
"""Explain current task truth for operator review."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


COMPLETED_STATUSES = {"done", "verified_done"}


def resolve_project_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    cwd = Path.cwd()
    if (cwd / "tasks.json").exists():
        return cwd
    env = os.environ.get("RALPH_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return cwd


def load_tasks(tasks_file: Path) -> dict:
    return json.loads(tasks_file.read_text(encoding="utf-8"))


def runnable_reason(task: dict, tasks: list[dict]) -> tuple[bool, str]:
    status = str(task.get("status", ""))
    if status != "pending":
        return False, f"status={status}"

    done_ids = {item.get("id") for item in tasks if item.get("status") in COMPLETED_STATUSES}
    unmet = [dep for dep in task.get("dependencies", []) if dep not in done_ids]
    if unmet:
        return False, "unmet dependencies: " + ", ".join(unmet)
    return True, "pending and dependencies satisfied"


def suggested_next_action(task: dict, is_runnable: bool, reason: str, re_audit: dict) -> str:
    status = str(task.get("status", ""))
    verdict = str(re_audit.get("verdict", ""))
    task_id = str(task.get("id", ""))

    if is_runnable:
        return f"Run ./ralph.sh task {task_id}"
    if status == "pending":
        return f"Do not run yet; resolve {reason}"
    if status in {"partial", "needs_human_review", "false_positive"}:
        return (
            f"Review evidence, then use scripts/reopen_tasks.py --task {task_id} "
            f"--to-status pending --note \"...\" if retry is justified"
        )
    if status in COMPLETED_STATUSES:
        return "No reopen needed; task already counts as completed"
    if verdict == "verified_done":
        return "Status can be aligned via controlled re-audit/apply"
    return "Review revision_notes and audit artifact before changing status"


def main() -> int:
    parser = argparse.ArgumentParser(description="Explain task status and operator options")
    parser.add_argument("--project-dir", default=None, help="Project directory")
    parser.add_argument("task_id", help="Task ID to explain")
    args = parser.parse_args()

    project_dir = resolve_project_dir(args.project_dir)
    os.environ["RALPH_PROJECT_DIR"] = str(project_dir)

    from audit_artifact import AUDIT_DIR, format_audit_summary, load_artifact
    from re_audit_tasks import classify_task

    tasks_file = project_dir / "tasks.json"
    data = load_tasks(tasks_file)
    tasks = data.get("tasks", [])
    task = next((item for item in tasks if item.get("id") == args.task_id), None)
    if task is None:
        print(f"Task not found: {args.task_id}")
        return 1

    is_runnable, reason = runnable_reason(task, tasks)
    re_audit = classify_task(task)

    lines = [
        f"Task: {task['id']} — {task.get('title', '')}",
        f"Status: {task.get('status', 'unknown')}",
        "Dependencies: " + (", ".join(task.get("dependencies", [])) if task.get("dependencies") else "none"),
        f"Runnable: {'yes' if is_runnable else 'no'}",
        f"Why not runnable: {reason if not is_runnable else 'n/a'}",
        f"Re-audit verdict: {re_audit['verdict']} ({re_audit['task_class']})",
        f"Re-audit reason: {re_audit['reason']}",
        "Suggested next action: " + suggested_next_action(task, is_runnable, reason, re_audit),
    ]

    audit_path = AUDIT_DIR / f"{task['id']}.json"
    if audit_path.exists():
        lines.append("")
        lines.append("Audit summary:")
        lines.append(format_audit_summary(load_artifact(task["id"]), fallback_task_id=task["id"]))
    else:
        lines.append("")
        lines.append("Audit summary: none")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
