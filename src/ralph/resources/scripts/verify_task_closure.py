#!/usr/bin/env python3
"""Minimal trust-layer verification before task closure."""

from __future__ import annotations

import json
import os
import py_compile
import re
import sys
from pathlib import Path

try:
    from ralph_common import (
        detect_task_class,
        extract_command_tokens,
        extract_expected_test_names,
        extract_path_candidates,
        infer_task_context,
        is_bookkeeping,
        is_bookkeeping_file,
        normalize_path,
        resolve_project_dir,
    )
except ImportError:
    from scripts.ralph_common import (
        detect_task_class,
        extract_command_tokens,
        extract_expected_test_names,
        extract_path_candidates,
        infer_task_context,
        is_bookkeeping,
        is_bookkeeping_file,
        normalize_path,
        resolve_project_dir,
    )


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def command_candidate_handlers(token: str) -> set[str]:
    return {f"cmd_{token}", f"cmd_start_{token}"}


def command_routed_handlers(bot_text: str, token: str) -> set[str]:
    pattern = re.compile(
        rf'(?:if|elif)\s+cmd\s*==\s*["\']/{re.escape(token)}["\']\s*:\s*\n\s*await\s+([a-zA-Z_][a-zA-Z0-9_]*)\(',
        re.MULTILINE,
    )
    return set(pattern.findall(bot_text))


def file_contains_required_content(task: dict, path: Path) -> bool:
    content = read_text(path).lower()
    if not content:
        return False
    for criterion in task.get("acceptance_criteria", []) or []:
        crit = criterion.strip()
        if crit.lower().startswith("содержит "):
            phrase = crit[9:].strip().lower()
            if phrase and phrase not in content:
                return False
        if crit.lower().startswith("contains "):
            phrase = crit[9:].strip().lower()
            if phrase and phrase not in content:
                return False
    return True


def result(result: str, task_class: str, reason: str, changed_files: list[str], non_bookkeeping: list[str]) -> dict:
    return {
        "result": result,
        "task_class": task_class,
        "reason": reason,
        "changed_files": changed_files,
        "changed_files_non_bookkeeping": non_bookkeeping,
        "bookkeeping_only": bool(changed_files) and not non_bookkeeping,
    }


def verify_task_completion(task: dict, project_dir: Path, changed_files: list[str]) -> dict:
    changed_files = [normalize_path(path) for path in changed_files if normalize_path(path)]
    non_bookkeeping = [path for path in changed_files if not is_bookkeeping_file(path)]
    task_class, expected_paths, command_tokens, expected_tests = infer_task_context(task)

    if task_class == "reaudit-report":
        script_path = project_dir / "scripts" / "re_audit_tasks.py"
        test_path = project_dir / "tests" / "test_re_audit_tasks.py"
        report_path = project_dir / "audit_report.md"

        missing_parts: list[str] = []
        script_text = read_text(script_path)
        tests_text = read_text(test_path)
        report_text = read_text(report_path)

        if not script_text:
            missing_parts.append("scripts/re_audit_tasks.py is missing")
        if not tests_text:
            missing_parts.append("tests/test_re_audit_tasks.py is missing")
        if not report_text:
            missing_parts.append("audit_report.md is missing")
        if script_text:
            if "audit_report.md" not in script_text or "Human-readable report saved to" not in script_text:
                missing_parts.append("re-audit script does not persist human-readable report")
            if "false positive" not in script_text or "unclear" not in script_text:
                missing_parts.append("re-audit script does not expose human-readable classifications")
        if tests_text:
            if "audit_report.md" not in tests_text or "Classification: unclear" not in tests_text:
                missing_parts.append("re-audit report path is not covered by targeted tests")
        if report_text:
            if "# Re-audit Report" not in report_text or "## Results" not in report_text:
                missing_parts.append("audit_report.md does not contain saved re-audit report output")

        if missing_parts:
            return result("fail_fix", task_class, "Verification failed: " + "; ".join(missing_parts), changed_files, non_bookkeeping)
        return result(
            "pass",
            task_class,
            "Re-audit reporting verification passed.",
            changed_files,
            non_bookkeeping,
        )

    if task_class not in {"docs-only", "template"} and not non_bookkeeping:
        reason = "Verification failed: only bookkeeping/state/report files changed; no implementation evidence found."
        return result("fail_fix", task_class, reason, changed_files, non_bookkeeping)

    if task_class == "command":
        bot_path = project_dir / "scripts" / "ralph_bot.py"
        bot_text = read_text(bot_path)
        missing_handler: list[str] = []
        missing_routing: list[str] = []
        missing_help: list[str] = []
        resolved_handlers: dict[str, set[str]] = {}
        if not any(path == "scripts/ralph_bot.py" or path.startswith("tests/") for path in non_bookkeeping):
            return result("fail_fix", task_class, "Verification failed: command task changed no bot or test files.", changed_files, non_bookkeeping)
        for token in command_tokens:
            handlers = command_candidate_handlers(token) | command_routed_handlers(bot_text, token)
            resolved_handlers[token] = handlers
            if not any(f"def {handler}(" in bot_text for handler in handlers):
                missing_handler.append(token)
            if not re.search(rf'(?:if|elif)\s+cmd\s*==\s*["\']/{re.escape(token)}["\']', bot_text):
                missing_routing.append(token)
            if f"/{token}" not in bot_text:
                missing_help.append(token)
        tests_have_evidence = any(path.startswith("tests/") for path in non_bookkeeping)
        if not tests_have_evidence:
            for test_file in project_dir.glob("tests/test_*.py"):
                test_text = read_text(test_file)
                if any(
                    f"/{token}" in test_text or any(handler in test_text for handler in resolved_handlers.get(token, set()))
                    for token in command_tokens
                ):
                    tests_have_evidence = True
                    break
        missing_parts: list[str] = []
        if missing_handler:
            missing_parts.append("missing handlers: " + ", ".join("/" + token for token in missing_handler))
        if missing_routing:
            missing_parts.append("missing routing: " + ", ".join("/" + token for token in missing_routing))
        if missing_help:
            missing_parts.append("missing command/help evidence: " + ", ".join("/" + token for token in missing_help))
        if missing_parts:
            return result("fail_fix", task_class, "Verification failed: " + "; ".join(missing_parts), changed_files, non_bookkeeping)
        if not tests_have_evidence:
            return result("fail_fix", task_class, "Verification failed: command task has no test or smoke evidence.", changed_files, non_bookkeeping)
        return result("pass", task_class, "Command verification passed.", changed_files, non_bookkeeping)

    if task_class == "script":
        script_paths = [path for path in expected_paths if path.startswith("scripts/")]
        if not script_paths:
            return result("needs_human_review", task_class, "Verification is uncertain: no explicit script path found in task text.", changed_files, non_bookkeeping)
        if not any(path in non_bookkeeping for path in script_paths) and not any(
            path in non_bookkeeping for path in ("ralph.sh", "scripts/ralph_bot.py")
        ):
            return result("fail_fix", task_class, "Verification failed: script task changed no script or integration files.", changed_files, non_bookkeeping)
        for script_path in script_paths:
            full_path = project_dir / script_path
            if not full_path.exists():
                return result("fail_fix", task_class, f"Verification failed: expected script missing: {script_path}", changed_files, non_bookkeeping)
            if full_path.suffix == ".py":
                try:
                    py_compile.compile(str(full_path), doraise=True)
                except Exception as exc:
                    return result("fail_fix", task_class, f"Verification failed: script does not compile: {script_path} ({exc})", changed_files, non_bookkeeping)
        text_blob = "\n".join([task.get("description", ""), *task.get("acceptance_criteria", [])])
        if ("ralph.sh" in text_blob or "ralph_bot.py" in text_blob) and not any(
            path in non_bookkeeping for path in ("ralph.sh", "scripts/ralph_bot.py")
        ):
            return result("fail_fix", task_class, "Verification failed: task requires integration hook but no integration file changed.", changed_files, non_bookkeeping)
        return result("pass", task_class, "Script verification passed.", changed_files, non_bookkeeping)

    if task_class == "template":
        template_paths = [path for path in expected_paths if path.startswith("templates/")]
        if not template_paths:
            return result("needs_human_review", task_class, "Verification is uncertain: no explicit template path found in task text.", changed_files, non_bookkeeping)
        if not any(path in non_bookkeeping for path in template_paths):
            return result("fail_fix", task_class, "Verification failed: template task changed no target template files.", changed_files, non_bookkeeping)
        for template_path in template_paths:
            full_path = project_dir / template_path
            if not full_path.exists():
                return result("fail_fix", task_class, f"Verification failed: expected template missing: {template_path}", changed_files, non_bookkeeping)
            if not file_contains_required_content(task, full_path):
                return result("fail_fix", task_class, f"Verification failed: required template content missing in {template_path}", changed_files, non_bookkeeping)
        return result("pass", task_class, "Template verification passed.", changed_files, non_bookkeeping)

    if task_class == "docs-only":
        doc_paths = expected_paths or [path for path in non_bookkeeping if path.endswith(".md")]
        if not doc_paths:
            return result("fail_fix", task_class, "Verification failed: docs-only task has no documentation evidence.", changed_files, non_bookkeeping)
        if not any(path in non_bookkeeping for path in doc_paths) and not any(path.endswith(".md") for path in non_bookkeeping):
            return result("fail_fix", task_class, "Verification failed: docs-only task changed no documentation files.", changed_files, non_bookkeeping)
        for doc_path in doc_paths:
            full_path = project_dir / doc_path
            if not full_path.exists():
                return result("fail_fix", task_class, f"Verification failed: expected document missing: {doc_path}", changed_files, non_bookkeeping)
            if not file_contains_required_content(task, full_path):
                return result("fail_fix", task_class, f"Verification failed: required document content missing in {doc_path}", changed_files, non_bookkeeping)
        return result("pass", task_class, "Docs verification passed.", changed_files, non_bookkeeping)

    if task_class == "tests-only":
        test_files = [path for path in non_bookkeeping if path.startswith("tests/")]
        if not test_files:
            return result("fail_fix", task_class, "Verification failed: tests-only task has no changed test files.", changed_files, non_bookkeeping)
        for test_name in expected_tests:
            found = False
            for test_file in project_dir.glob("tests/test_*.py"):
                if test_name in read_text(test_file):
                    found = True
                    break
            if not found:
                return result("fail_fix", task_class, f"Verification failed: expected test not found: {test_name}", changed_files, non_bookkeeping)
        return result("pass", task_class, "Tests verification passed.", changed_files, non_bookkeeping)

    return result("pass", task_class, "Generic implementation verification passed.", changed_files, non_bookkeeping)


def main() -> None:
    raw_task = sys.stdin.read().strip() or "{}"
    task = json.loads(raw_task)
    project_dir = resolve_project_dir(os.environ.get("RALPH_PROJECT_DIR"), script_path=__file__)
    changed_files = json.loads(os.environ.get("RALPH_CHANGED_FILES_JSON", "[]"))
    print(json.dumps(verify_task_completion(task, project_dir, changed_files), ensure_ascii=False))


if __name__ == "__main__":
    main()
