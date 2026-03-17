#!/usr/bin/env python3
"""Minimal trust-layer verification before task closure."""

from __future__ import annotations

import json
import os
import py_compile
import re
import sys
from pathlib import Path


BOOKKEEPING_EXACT = {
    "tasks.json",
    "progress.md",
    "ralph_state.json",
    "ralph_control.json",
    "ralph_alerts.log",
    "ralph_main.pid",
    "ralph_codex.pid",
    "ralph_codex.pgid",
    ".ralph/memory/recent.md",
    ".ralph/memory/decisions.md",
    ".ralph/memory/patterns.md",
}
BOOKKEEPING_PREFIXES = (
    "logs/",
    ".pytest_cache/",
    "__pycache__/",
    ".ralph/audit/",
)
DOC_KEYWORDS = (
    "readme",
    "documentation",
    "docs/",
    "postmortem",
    "prompt_version",
    "changelog",
)


def normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/").lstrip("./")


def is_bookkeeping_file(path: str) -> bool:
    normalized = normalize_path(path)
    if normalized in BOOKKEEPING_EXACT:
        return True
    return any(normalized.startswith(prefix) for prefix in BOOKKEEPING_PREFIXES)


def extract_path_candidates(task: dict) -> list[str]:
    texts: list[str] = [task.get("title", ""), task.get("description", "")]
    texts.extend(task.get("acceptance_criteria", []) or [])
    texts.extend(task.get("test_steps", []) or [])
    combined = "\n".join(texts)
    matches = re.findall(
        r"((?:scripts|templates|tests|docs)/[A-Za-z0-9_./-]+\.(?:py|md|json|sh|ts|tsx|js)|(?:README|PROMPT_CHANGELOG|AGENTS(?:_[A-Z]+)?|BLOG_DRAFTS|progress)\.md)",
        combined,
    )
    seen: set[str] = set()
    result: list[str] = []
    for match in matches:
        path = normalize_path(match)
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def extract_command_tokens(task: dict) -> list[str]:
    texts: list[str] = [task.get("title", ""), task.get("description", "")]
    texts.extend(task.get("acceptance_criteria", []) or [])
    tokens = re.findall(r"/([a-z][a-z0-9_]*)", "\n".join(texts).lower())
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def extract_expected_test_names(task: dict) -> list[str]:
    texts = [task.get("title", ""), task.get("description", "")]
    texts.extend(task.get("acceptance_criteria", []) or [])
    texts.extend(task.get("test_steps", []) or [])
    names = re.findall(r"\b(test_[a-zA-Z0-9_]+)\b", "\n".join(texts))
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def detect_task_class(task: dict, expected_paths: list[str], command_tokens: list[str], expected_tests: list[str]) -> str:
    title = task.get("title", "").lower()
    description = task.get("description", "").lower()
    combined = "\n".join(
        [title, description, *[item.lower() for item in task.get("acceptance_criteria", []) or []]]
    )
    if any(path.startswith("templates/") for path in expected_paths):
        return "template"
    if any(path.startswith("scripts/") for path in expected_paths):
        return "script"
    if command_tokens and ("bot" in title or "команда" in title or "telegram" in combined):
        return "command"
    if title.startswith("tests:") or expected_tests or "pytest" in combined:
        return "tests-only"
    if any(path.startswith("docs/") for path in expected_paths) or any(path.endswith(".md") for path in expected_paths):
        return "docs-only"
    if any(keyword in combined for keyword in DOC_KEYWORDS):
        return "docs-only"
    return "implementation"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


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
    expected_paths = extract_path_candidates(task)
    command_tokens = extract_command_tokens(task)
    expected_tests = extract_expected_test_names(task)
    task_class = detect_task_class(task, expected_paths, command_tokens, expected_tests)

    if task_class not in {"docs-only", "template"} and not non_bookkeeping:
        reason = "Verification failed: only bookkeeping/state/report files changed; no implementation evidence found."
        return result("fail_fix", task_class, reason, changed_files, non_bookkeeping)

    if task_class == "command":
        bot_path = project_dir / "scripts" / "ralph_bot.py"
        bot_text = read_text(bot_path)
        missing: list[str] = []
        if not any(path == "scripts/ralph_bot.py" or path.startswith("tests/") for path in non_bookkeeping):
            return result("fail_fix", task_class, "Verification failed: command task changed no bot or test files.", changed_files, non_bookkeeping)
        for token in command_tokens:
            handler = f"cmd_{token}"
            if handler not in bot_text:
                missing.append(f"missing handler {handler}")
            if f"/{token}" not in bot_text:
                missing.append(f"missing routing for /{token}")
        tests_have_evidence = any(path.startswith("tests/") for path in non_bookkeeping)
        if not tests_have_evidence:
            for test_file in project_dir.glob("tests/test_*.py"):
                test_text = read_text(test_file)
                if any(f"/{token}" in test_text or f"cmd_{token}" in test_text for token in command_tokens):
                    tests_have_evidence = True
                    break
        if missing:
            return result("fail_fix", task_class, "Verification failed: " + ", ".join(missing), changed_files, non_bookkeeping)
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
    project_dir = Path(os.environ.get("RALPH_PROJECT_DIR", ".")).resolve()
    changed_files = json.loads(os.environ.get("RALPH_CHANGED_FILES_JSON", "[]"))
    print(json.dumps(verify_task_completion(task, project_dir, changed_files), ensure_ascii=False))


if __name__ == "__main__":
    main()
