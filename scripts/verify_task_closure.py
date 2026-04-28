#!/usr/bin/env python3
"""Minimal trust-layer verification before task closure."""

from __future__ import annotations

import json
import os
import py_compile
import re
import sys
from difflib import SequenceMatcher
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


def build_target_file_debug(task: dict, project_dir: Path, changed_files: list[str], non_bookkeeping: list[str]) -> dict:
    expected_files = [normalize_path(str(item).strip()) for item in (task.get("target_files") or []) if str(item).strip()]
    expected_files = [path for path in expected_files if path]
    actual_files = list(non_bookkeeping)
    expected_set = set(expected_files)
    actual_set = set(actual_files)

    debug: dict[str, object] = {
        "expected_files": expected_files,
        "actual_files": actual_files,
        "missing_expected_files": sorted(expected_set - actual_set),
        "unexpected_files": sorted(actual_set - expected_set),
        "existing_expected_files": [],
        "missing_on_disk_files": [],
        "content_hints": [],
    }

    for rel_path in expected_files:
        full_path = project_dir / rel_path
        if not full_path.exists():
            debug["missing_on_disk_files"].append(rel_path)
            continue

        debug["existing_expected_files"].append(rel_path)
        content = read_text(full_path)
        lines = content.splitlines()
        required_phrases: list[str] = []
        missing_phrases: list[str] = []
        for criterion in task.get("acceptance_criteria", []) or []:
            crit = str(criterion).strip()
            lower_crit = crit.lower()
            phrase = ""
            if lower_crit.startswith("contains "):
                phrase = crit[9:].strip()
            elif lower_crit.startswith("содержит "):
                phrase = crit[9:].strip()
            if phrase:
                required_phrases.append(phrase)
                if phrase.lower() not in content.lower():
                    missing_phrases.append(phrase)

        similarity = 1.0
        if actual_files:
            similarity = max(SequenceMatcher(a=rel_path, b=actual_path).ratio() for actual_path in actual_files)

        debug["content_hints"].append(
            {
                "path": rel_path,
                "exists": True,
                "bytes": len(content.encode("utf-8")),
                "lines": len(lines),
                "required_phrases": required_phrases,
                "missing_phrases": missing_phrases,
                "closest_actual_path_similarity": round(similarity, 3),
            }
        )

    return debug


def format_target_file_debug(debug: dict) -> list[str]:
    if not debug.get("expected_files"):
        return []

    lines = [
        f"DEBUG: Expected files: {debug['expected_files']}",
        f"DEBUG: Actual files found: {debug['actual_files']}",
    ]
    if debug.get("missing_expected_files"):
        lines.append(f"DEBUG: Missing expected files in changed set: {debug['missing_expected_files']}")
    if debug.get("unexpected_files"):
        lines.append(f"DEBUG: Unexpected changed files outside target_files: {debug['unexpected_files']}")
    if debug.get("missing_on_disk_files"):
        lines.append(f"DEBUG: Expected files missing on disk: {debug['missing_on_disk_files']}")
    for hint in debug.get("content_hints", []):
        lines.append(
            "DEBUG: File state: "
            f"{hint['path']} exists={hint['exists']} bytes={hint['bytes']} lines={hint['lines']} "
            f"missing_phrases={hint['missing_phrases']} closest_actual_path_similarity={hint['closest_actual_path_similarity']}"
        )
    return lines


def verify_task_completion(task: dict, project_dir: Path, changed_files: list[str]) -> dict:
    changed_files = [normalize_path(path) for path in changed_files if normalize_path(path)]
    non_bookkeeping = [path for path in changed_files if not is_bookkeeping_file(path)]
    task_class, expected_paths, command_tokens, expected_tests = infer_task_context(task)
    target_file_debug = build_target_file_debug(task, project_dir, changed_files, non_bookkeeping)
    debug_lines = format_target_file_debug(target_file_debug)
    target_files_declared = bool(target_file_debug.get("expected_files"))

    if target_files_declared:
        missing_expected = target_file_debug.get("missing_expected_files", [])
        unexpected_files = target_file_debug.get("unexpected_files", [])
        missing_on_disk = target_file_debug.get("missing_on_disk_files", [])
        if missing_expected or unexpected_files or missing_on_disk:
            debug_summary: list[str] = []
            if missing_expected:
                debug_summary.append(f"missing target_files in diff: {', '.join(missing_expected)}")
            if unexpected_files:
                debug_summary.append(f"unexpected changed files: {', '.join(unexpected_files)}")
            if missing_on_disk:
                debug_summary.append(f"missing on disk: {', '.join(missing_on_disk)}")
            failure = result(
                "fail_fix",
                task_class,
                "Verification failed: target_files do not exactly match implementation evidence; " + "; ".join(debug_summary),
                changed_files,
                non_bookkeeping,
            )
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure

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
            failure = result("fail_fix", task_class, "Verification failed: " + "; ".join(missing_parts), changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        success = result(
            "pass",
            task_class,
            "Re-audit reporting verification passed.",
            changed_files,
            non_bookkeeping,
        )
        success["debug_lines"] = debug_lines
        success["target_file_debug"] = target_file_debug
        return success

    if task_class not in {"docs-only", "template"} and not non_bookkeeping:
        reason = "Verification failed: only bookkeeping/state/report files changed; no implementation evidence found."
        failure = result("fail_fix", task_class, reason, changed_files, non_bookkeeping)
        failure["debug_lines"] = debug_lines
        failure["target_file_debug"] = target_file_debug
        return failure

    if task_class == "command":
        bot_path = project_dir / "scripts" / "ralph_bot.py"
        bot_text = read_text(bot_path)
        missing_handler: list[str] = []
        missing_routing: list[str] = []
        missing_help: list[str] = []
        resolved_handlers: dict[str, set[str]] = {}
        if not any(path == "scripts/ralph_bot.py" or path.startswith("tests/") for path in non_bookkeeping):
            failure = result("fail_fix", task_class, "Verification failed: command task changed no bot or test files.", changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
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
            failure = result("fail_fix", task_class, "Verification failed: " + "; ".join(missing_parts), changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        if not tests_have_evidence:
            failure = result("fail_fix", task_class, "Verification failed: command task has no test or smoke evidence.", changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        success = result("pass", task_class, "Command verification passed.", changed_files, non_bookkeeping)
        success["debug_lines"] = debug_lines
        success["target_file_debug"] = target_file_debug
        return success

    if task_class == "script":
        script_paths = [path for path in expected_paths if path.startswith("scripts/")]
        if not script_paths:
            review = result("needs_human_review", task_class, "Verification is uncertain: no explicit script path found in task text.", changed_files, non_bookkeeping)
            review["debug_lines"] = debug_lines
            review["target_file_debug"] = target_file_debug
            return review
        if not any(path in non_bookkeeping for path in script_paths) and not any(
            path in non_bookkeeping for path in ("ralph.sh", "scripts/ralph_bot.py")
        ):
            failure = result("fail_fix", task_class, "Verification failed: script task changed no script or integration files.", changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        for script_path in script_paths:
            full_path = project_dir / script_path
            if not full_path.exists():
                failure = result("fail_fix", task_class, f"Verification failed: expected script missing: {script_path}", changed_files, non_bookkeeping)
                failure["debug_lines"] = debug_lines
                failure["target_file_debug"] = target_file_debug
                return failure
            if full_path.suffix == ".py":
                try:
                    py_compile.compile(str(full_path), doraise=True)
                except Exception as exc:
                    failure = result("fail_fix", task_class, f"Verification failed: script does not compile: {script_path} ({exc})", changed_files, non_bookkeeping)
                    failure["debug_lines"] = debug_lines
                    failure["target_file_debug"] = target_file_debug
                    return failure
        text_blob = "\n".join([task.get("description", ""), *task.get("acceptance_criteria", [])])
        if ("ralph.sh" in text_blob or "ralph_bot.py" in text_blob) and not any(
            path in non_bookkeeping for path in ("ralph.sh", "scripts/ralph_bot.py")
        ):
            failure = result("fail_fix", task_class, "Verification failed: task requires integration hook but no integration file changed.", changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        success = result("pass", task_class, "Script verification passed.", changed_files, non_bookkeeping)
        success["debug_lines"] = debug_lines
        success["target_file_debug"] = target_file_debug
        return success

    if task_class == "template":
        template_paths = [path for path in expected_paths if path.startswith("templates/")]
        if not template_paths:
            review = result("needs_human_review", task_class, "Verification is uncertain: no explicit template path found in task text.", changed_files, non_bookkeeping)
            review["debug_lines"] = debug_lines
            review["target_file_debug"] = target_file_debug
            return review
        if not any(path in non_bookkeeping for path in template_paths):
            failure = result("fail_fix", task_class, "Verification failed: template task changed no target template files.", changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        for template_path in template_paths:
            full_path = project_dir / template_path
            if not full_path.exists():
                failure = result("fail_fix", task_class, f"Verification failed: expected template missing: {template_path}", changed_files, non_bookkeeping)
                failure["debug_lines"] = debug_lines
                failure["target_file_debug"] = target_file_debug
                return failure
            if not file_contains_required_content(task, full_path):
                failure = result("fail_fix", task_class, f"Verification failed: required template content missing in {template_path}", changed_files, non_bookkeeping)
                failure["debug_lines"] = debug_lines
                failure["target_file_debug"] = target_file_debug
                return failure
        success = result("pass", task_class, "Template verification passed.", changed_files, non_bookkeeping)
        success["debug_lines"] = debug_lines
        success["target_file_debug"] = target_file_debug
        return success

    if task_class == "docs-only":
        doc_paths = expected_paths or [path for path in non_bookkeeping if path.endswith(".md")]
        if not doc_paths:
            failure = result("fail_fix", task_class, "Verification failed: docs-only task has no documentation evidence.", changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        if not any(path in non_bookkeeping for path in doc_paths) and not any(path.endswith(".md") for path in non_bookkeeping):
            failure = result("fail_fix", task_class, "Verification failed: docs-only task changed no documentation files.", changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        for doc_path in doc_paths:
            full_path = project_dir / doc_path
            if not full_path.exists():
                failure = result("fail_fix", task_class, f"Verification failed: expected document missing: {doc_path}", changed_files, non_bookkeeping)
                failure["debug_lines"] = debug_lines
                failure["target_file_debug"] = target_file_debug
                return failure
            if not file_contains_required_content(task, full_path):
                failure = result("fail_fix", task_class, f"Verification failed: required document content missing in {doc_path}", changed_files, non_bookkeeping)
                failure["debug_lines"] = debug_lines
                failure["target_file_debug"] = target_file_debug
                return failure
        success = result("pass", task_class, "Docs verification passed.", changed_files, non_bookkeeping)
        success["debug_lines"] = debug_lines
        success["target_file_debug"] = target_file_debug
        return success

    if task_class == "tests-only":
        test_files = [path for path in non_bookkeeping if path.startswith("tests/")]
        if not test_files:
            failure = result("fail_fix", task_class, "Verification failed: tests-only task has no changed test files.", changed_files, non_bookkeeping)
            failure["debug_lines"] = debug_lines
            failure["target_file_debug"] = target_file_debug
            return failure
        for test_name in expected_tests:
            found = False
            for test_file in project_dir.glob("tests/test_*.py"):
                if test_name in read_text(test_file):
                    found = True
                    break
            if not found:
                failure = result("fail_fix", task_class, f"Verification failed: expected test not found: {test_name}", changed_files, non_bookkeeping)
                failure["debug_lines"] = debug_lines
                failure["target_file_debug"] = target_file_debug
                return failure
        success = result("pass", task_class, "Tests verification passed.", changed_files, non_bookkeeping)
        success["debug_lines"] = debug_lines
        success["target_file_debug"] = target_file_debug
        return success

    success = result("pass", task_class, "Generic implementation verification passed.", changed_files, non_bookkeeping)
    success["debug_lines"] = debug_lines
    success["target_file_debug"] = target_file_debug
    return success


def main() -> None:
    raw_task = sys.stdin.read().strip() or "{}"
    changed_files: list[str] = []
    try:
        task = json.loads(raw_task)
        project_dir = resolve_project_dir(os.environ.get("RALPH_PROJECT_DIR"), script_path=__file__)
        changed_files = json.loads(os.environ.get("RALPH_CHANGED_FILES_JSON", "[]"))
        verification = verify_task_completion(task, project_dir, changed_files)
    except Exception:
        normalized_changed = [normalize_path(path) for path in changed_files if isinstance(path, str) and normalize_path(path)]
        non_bookkeeping = [path for path in normalized_changed if not is_bookkeeping_file(path)]
        verification = result(
            "needs_human_review",
            "implementation",
            "Verification script failed unexpectedly.",
            normalized_changed,
            non_bookkeeping,
        )
    for line in verification.get("debug_lines", []) or []:
        print(line, file=sys.stderr)
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == "__main__":
    main()
