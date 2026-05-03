#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from ralph_common import load_tasks_data, resolve_project_dir
except ImportError:
    from scripts.ralph_common import load_tasks_data, resolve_project_dir


WARNING_ORDER = (
    "BOOTSTRAP_FEATURE",
    "MISSING_TEST_TARGET",
    "PREVIOUS_RETRY_FAILURE",
    "COMPLEX_TASK",
    "BROAD_SCOPE",
)

BOOTSTRAP_PATTERNS = (
    r"\bbootstrap\b",
    r"\bkickoff\b",
    r"\bscaffold\b",
    r"\binit\b",
    r"\bgeneration\b",
    r"\bgenerate\b",
    r"\bnew cli mode\b",
    r"\bnew cli\b",
    r"\bnew command\b",
)

TEST_IMPLYING_PATTERNS = (
    r"\btest\b",
    r"\btests\b",
    r"\bcoverage\b",
)

RETRY_PATTERNS = (
    r"failed after retries",
    r"failed after \d+ retries",
    r"\bretries\b",
    r"\bretry\b",
)


def normalize_text(value: object) -> str:
    return str(value or "").strip().lower()


def title_description_text(task: dict) -> str:
    return " ".join(
        filter(
            None,
            (
                normalize_text(task.get("title")),
                normalize_text(task.get("description")),
            ),
        )
    )


def acceptance_text(task: dict) -> str:
    criteria = task.get("acceptance_criteria") or []
    if not isinstance(criteria, list):
        return normalize_text(criteria)
    return " ".join(normalize_text(item) for item in criteria if normalize_text(item))


def has_test_target(task: dict) -> bool:
    items = task.get("target_files") or []
    if not isinstance(items, list):
        return False
    for item in items:
        value = str(item or "").strip().replace("\\", "/")
        if value.startswith("tests/") or "/tests/" in value:
            return True
    return False


def warn_bootstrap_feature(task: dict) -> str | None:
    text = title_description_text(task)
    for pattern in BOOTSTRAP_PATTERNS:
        if re.search(pattern, text):
            return "bootstrap/kickoff/init/generation style task is risky for unattended auto"
    return None


def warn_missing_test_target(task: dict) -> str | None:
    if has_test_target(task):
        return None
    text = acceptance_text(task)
    for pattern in TEST_IMPLYING_PATTERNS:
        if re.search(pattern, text):
            return "acceptance implies test coverage but target_files has no tests/ path"
    return None


def warn_previous_retry_failure(task: dict) -> str | None:
    notes = normalize_text(task.get("revision_notes"))
    for pattern in RETRY_PATTERNS:
        if re.search(pattern, notes):
            return "revision_notes mention previous retry failure"
    return None


def warn_complex_task(task: dict) -> str | None:
    if normalize_text(task.get("complexity")) == "complex":
        return "complex task is risky for unattended auto"
    return None


def warn_broad_scope(task: dict) -> str | None:
    if task.get("scope_too_wide") is True:
        return "task is already marked scope_too_wide"
    warnings = task.get("selection_warnings") or []
    if isinstance(warnings, list) and warnings:
        return "selection_warnings indicate broad or structurally risky scope"
    return None


def task_warnings(task: dict) -> list[tuple[str, str]]:
    checks = {
        "BOOTSTRAP_FEATURE": warn_bootstrap_feature(task),
        "MISSING_TEST_TARGET": warn_missing_test_target(task),
        "PREVIOUS_RETRY_FAILURE": warn_previous_retry_failure(task),
        "COMPLEX_TASK": warn_complex_task(task),
        "BROAD_SCOPE": warn_broad_scope(task),
    }
    return [(code, checks[code]) for code in WARNING_ORDER if checks[code]]


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
        for code, reason in task_warnings(task):
            print(f"TASK_HYGIENE_WARN {task_id} {code} {reason}")
            warn_count += 1

    if args.fail_on_warn and warn_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
