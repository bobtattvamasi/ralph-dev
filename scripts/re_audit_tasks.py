#!/usr/bin/env python3
"""Conservative re-audit of completed tasks using current repo truth."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verify_task_closure import (
    detect_task_class,
    extract_command_tokens,
    extract_expected_test_names,
    extract_path_candidates,
    file_contains_required_content,
    normalize_path,
    read_text,
)


PROJECT_DIR = Path(os.environ.get("RALPH_PROJECT_DIR", Path(__file__).resolve().parent.parent))
TASKS_FILE = PROJECT_DIR / "tasks.json"
AUDIT_DIR = PROJECT_DIR / ".ralph" / "audit"
BOT_FILE = PROJECT_DIR / "scripts" / "ralph_bot.py"
COMPLETE_STATUSES = {"done", "verified_done"}
APPLYABLE_VERDICTS = {"verified_done", "false_positive", "partial"}


def load_tasks() -> dict[str, Any]:
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def load_audit(task_id: str) -> dict | None:
    path = AUDIT_DIR / f"{task_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def infer_task_class(task: dict[str, Any]) -> tuple[str, list[str], list[str], list[str]]:
    expected_paths = extract_path_candidates(task)
    command_tokens = extract_command_tokens(task)
    expected_tests = extract_expected_test_names(task)
    task_class = detect_task_class(task, expected_paths, command_tokens, expected_tests)
    return task_class, expected_paths, command_tokens, expected_tests


def classify_command(task: dict[str, Any], command_tokens: list[str]) -> tuple[str, str]:
    if not command_tokens:
        return "needs_human_review", "No explicit /command token found in task text."
    bot_text = read_text(BOT_FILE)
    if not bot_text:
        return "false_positive", "scripts/ralph_bot.py is missing."

    missing_handler = []
    missing_routing = []
    for token in command_tokens:
        if f"cmd_{token}" not in bot_text:
            missing_handler.append(token)
        if f'"/{token}"' not in bot_text and f"'/ {token}'" not in bot_text:
            if f"/{token}" not in bot_text:
                missing_routing.append(token)

    tests_present = False
    for test_file in PROJECT_DIR.glob("tests/test_*.py"):
        text = read_text(test_file)
        if any(f"/{token}" in text or f"cmd_{token}" in text for token in command_tokens):
            tests_present = True
            break

    if len(missing_handler) == len(command_tokens) and len(missing_routing) == len(command_tokens):
        return "false_positive", f"Command implementation missing: {', '.join('/' + token for token in command_tokens)}."
    if missing_handler or missing_routing or not tests_present:
        parts = []
        if missing_handler:
            parts.append("missing handlers: " + ", ".join(f"cmd_{token}" for token in missing_handler))
        if missing_routing:
            parts.append("missing routing: " + ", ".join(f"/{token}" for token in missing_routing))
        if not tests_present:
            parts.append("missing command test evidence")
        return "partial", "; ".join(parts)
    return "verified_done", "Command handler, routing, and test evidence exist."


def classify_script(task: dict[str, Any], expected_paths: list[str]) -> tuple[str, str]:
    script_paths = [path for path in expected_paths if path.startswith("scripts/")]
    if not script_paths:
        return "needs_human_review", "No explicit script path found in task text."

    existing = [path for path in script_paths if (PROJECT_DIR / path).exists()]
    if not existing:
        return "false_positive", "Expected script is missing: " + ", ".join(script_paths)
    if len(existing) != len(script_paths):
        missing = [path for path in script_paths if path not in existing]
        return "partial", "Some expected scripts are missing: " + ", ".join(missing)

    return "verified_done", "Expected script paths exist in repository."


def classify_template(task: dict[str, Any], expected_paths: list[str]) -> tuple[str, str]:
    template_paths = [path for path in expected_paths if path.startswith("templates/")]
    if not template_paths:
        return "needs_human_review", "No explicit template path found in task text."

    existing = [path for path in template_paths if (PROJECT_DIR / path).exists()]
    if not existing:
        return "false_positive", "Expected template is missing: " + ", ".join(template_paths)
    if len(existing) != len(template_paths):
        missing = [path for path in template_paths if path not in existing]
        return "partial", "Some expected templates are missing: " + ", ".join(missing)

    incomplete = []
    for template_path in template_paths:
        full_path = PROJECT_DIR / template_path
        if not file_contains_required_content(task, full_path):
            incomplete.append(template_path)
    if incomplete:
        return "partial", "Template exists but required content is incomplete: " + ", ".join(incomplete)
    return "verified_done", "Expected template paths exist and match required content checks."


def classify_docs(task: dict[str, Any], expected_paths: list[str], audit: dict | None) -> tuple[str, str]:
    doc_paths = [path for path in expected_paths if path.startswith("docs/") or path.endswith(".md")]
    if not doc_paths:
        if audit and audit.get("verified_success") is True:
            return "verified_done", "Audit artifact shows verified success for docs task."
        return "needs_human_review", "No explicit docs path found in task text."

    existing = [path for path in doc_paths if (PROJECT_DIR / path).exists()]
    if not existing:
        return "false_positive", "Expected document is missing: " + ", ".join(doc_paths)
    if len(existing) != len(doc_paths):
        missing = [path for path in doc_paths if path not in existing]
        return "partial", "Some expected documents are missing: " + ", ".join(missing)
    for doc_path in doc_paths:
        if not file_contains_required_content(task, PROJECT_DIR / doc_path):
            return "partial", f"Document exists but required content looks incomplete: {doc_path}"
    return "verified_done", "Expected documentation exists and matches required content checks."


def classify_tests(task: dict[str, Any], expected_paths: list[str], expected_tests: list[str]) -> tuple[str, str]:
    test_files = [path for path in expected_paths if path.startswith("tests/")]
    existing_test_files = [path for path in test_files if (PROJECT_DIR / path).exists()]

    found_tests = []
    for test_name in expected_tests:
        for test_file in PROJECT_DIR.glob("tests/test_*.py"):
            if test_name in read_text(test_file):
                found_tests.append(test_name)
                break

    if not existing_test_files and not found_tests:
        return "false_positive", "Expected test files or named tests are missing."
    if expected_tests and len(found_tests) != len(expected_tests):
        missing = [name for name in expected_tests if name not in found_tests]
        return "partial", "Some expected tests are missing: " + ", ".join(missing)
    return "verified_done", "Expected test files and named tests exist."


def classify_implementation(task: dict[str, Any], audit: dict | None) -> tuple[str, str]:
    if audit and audit.get("verified_success") is True:
        return "verified_done", "Audit artifact shows verified success."
    if audit and audit.get("runtime_success") is True and audit.get("verified_success") is False:
        verification = audit.get("verification", {})
        reason = str(verification.get("reason", "")).strip()
        if reason:
            return "needs_human_review", f"Runtime succeeded but verification failed: {reason}"
        return "needs_human_review", "Runtime succeeded but verification did not pass."
    return "needs_human_review", "Generic implementation task needs human review: repo truth is not strong enough."


def classify_task(task: dict[str, Any]) -> dict[str, Any]:
    task_class, expected_paths, command_tokens, expected_tests = infer_task_class(task)
    audit = load_audit(task["id"])

    if task_class == "command":
        verdict, reason = classify_command(task, command_tokens)
    elif task_class == "script":
        verdict, reason = classify_script(task, expected_paths)
    elif task_class == "template":
        verdict, reason = classify_template(task, expected_paths)
    elif task_class == "docs-only":
        verdict, reason = classify_docs(task, expected_paths, audit)
    elif task_class == "tests-only":
        verdict, reason = classify_tests(task, expected_paths, expected_tests)
    else:
        verdict, reason = classify_implementation(task, audit)

    return {
        "task_id": task["id"],
        "current_status": task.get("status", ""),
        "task_class": task_class,
        "verdict": verdict,
        "reason": reason,
        "expected_paths": [normalize_path(path) for path in expected_paths],
        "has_audit": audit is not None,
    }


def select_tasks(data: dict[str, Any], last: int | None, task_id: str | None) -> list[dict[str, Any]]:
    tasks = data.get("tasks", [])
    if task_id:
        return [task for task in tasks if task.get("id") == task_id]
    completed = [task for task in tasks if task.get("status") in COMPLETE_STATUSES]
    if last is None:
        return completed
    return completed[-last:]


def apply_verdicts(data: dict[str, Any], results: list[dict[str, Any]]) -> int:
    applied = 0
    by_id = {item["task_id"]: item for item in results}
    now = datetime.now(timezone.utc).isoformat()
    for task in data.get("tasks", []):
        result = by_id.get(task.get("id"))
        if not result:
            continue
        verdict = result["verdict"]
        if verdict not in APPLYABLE_VERDICTS:
            continue
        task["status"] = verdict
        if verdict == "verified_done":
            task["completed_at"] = task.get("completed_at") or now
        else:
            task["completed_at"] = None
        task["revision_notes"] = (
            f"Re-audit {now}: {verdict} — {result['reason']}"
        )
        applied += 1
    return applied


def format_results(results: list[dict[str, Any]], apply: bool) -> str:
    lines = ["=== Re-audit Report ===", f"Mode: {'apply' if apply else 'dry-run'}"]
    if not results:
        lines.append("No tasks selected.")
        return "\n".join(lines)
    for item in results:
        lines.append(
            f"{item['task_id']} | {item['current_status']} -> {item['verdict']} | "
            f"{item['task_class']} | {item['reason']}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Conservative re-audit for completed tasks.")
    parser.add_argument("--last", type=int, default=None)
    parser.add_argument("--task", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    data = load_tasks()
    selected = select_tasks(data, args.last, args.task)
    results = [classify_task(task) for task in selected]

    if args.apply:
        applied = apply_verdicts(data, results)
        TASKS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(format_results(results, apply=True))
        print(f"Applied changes: {applied}")
    else:
        print(format_results(results, apply=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
