from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(os.environ.get("RALPH_PROJECT_DIR", Path(__file__).resolve().parent.parent))
CHANGED_FILES_JSON = os.environ.get("RALPH_CHANGED_FILES_JSON", "[]")

BOOKKEEPING_EXACT = {
    "tasks.json",
    "progress.md",
    "audit_report.md",
    "ralph_state.json",
    "ralph_control.json",
    "ralph_alerts.log",
    "logs/metrics.csv",
    "ralph_main.pid",
    "ralph_codex.pid",
    ".ralph/memory/recent.md",
    ".ralph/memory/patterns.md",
    ".ralph/memory/decisions.md",
}

BOOKKEEPING_PREFIXES = (
    "logs/",
    ".pytest_cache/",
    "__pycache__/",
    ".ralph/audit/",
    "ralph/audit/",
)


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def load_changed_files() -> list[str]:
    try:
        raw = json.loads(CHANGED_FILES_JSON)
        if isinstance(raw, list):
            return [normalize_path(str(item)) for item in raw]
    except Exception:
        pass
    return []


def extract_path_candidates(task: dict[str, Any]) -> list[str]:
    text_parts = [
        str(task.get("title", "")),
        str(task.get("description", "")),
        *[str(item) for item in task.get("acceptance_criteria", [])],
        *[str(item) for item in task.get("test_steps", [])],
    ]
    combined = "\n".join(text_parts)
    matches = re.findall(r"([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)", combined)
    paths = []
    for match in matches:
        normalized = normalize_path(match)
        if "/" in normalized or normalized.endswith(".md") or normalized.endswith(".py"):
            paths.append(normalized)
    seen = []
    for path in paths:
        if path not in seen:
            seen.append(path)
    return seen


def extract_command_tokens(task: dict[str, Any]) -> list[str]:
    text_parts = [
        str(task.get("title", "")),
        str(task.get("description", "")),
        *[str(item) for item in task.get("acceptance_criteria", [])],
        *[str(item) for item in task.get("test_steps", [])],
    ]
    combined = "\n".join(text_parts)
    tokens = re.findall(r"/([a-zA-Z0-9_]+)", combined)
    seen = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return seen


def extract_expected_test_names(task: dict[str, Any]) -> list[str]:
    text_parts = [*[str(item) for item in task.get("acceptance_criteria", [])], *[str(item) for item in task.get("test_steps", [])]]
    combined = "\n".join(text_parts)
    names = re.findall(r"\b(test_[A-Za-z0-9_]+)\b", combined)
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def detect_task_class(
    task: dict[str, Any],
    expected_paths: list[str],
    command_tokens: list[str],
    expected_tests: list[str],
) -> str:
    task_id = str(task.get("id", ""))
    title = str(task.get("title", "")).lower()
    description = str(task.get("description", "")).lower()
    acceptance = " ".join(str(item) for item in task.get("acceptance_criteria", [])).lower()
    combined = " ".join([task_id.lower(), title, description, acceptance])

    if any(path.startswith("templates/") for path in expected_paths):
        return "template"
    if any(path.startswith("scripts/") for path in expected_paths):
        return "script"
    if command_tokens and ("bot" in combined or "telegram" in combined or "/" in combined):
        return "command"
    if expected_tests and "tests" in combined:
        return "tests-only"
    if "re-audit" in combined and "report" in combined and any(
        keyword in combined for keyword in ("verified", "partial", "false positive", "unclear")
    ):
        return "reaudit-report"
    if any(path.startswith("docs/") for path in expected_paths) or "docs:" in title or title.startswith("docs"):
        return "docs-only"
    return "implementation"


def is_bookkeeping(path: str) -> bool:
    normalized = normalize_path(path)
    if normalized in BOOKKEEPING_EXACT:
        return True
    return any(normalized.startswith(prefix) for prefix in BOOKKEEPING_PREFIXES)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def file_contains_required_content(task: dict[str, Any], path: Path) -> bool:
    text = read_text(path)
    if not text:
        return False

    checks = {
        "AGENTS_COORDINATOR.md": ["question", "PROJECT_BRIEF"],
        "AGENTS_ARCHITECT.md": ["stack", "ARCHITECTURE"],
        "AGENTS_JOURNALIST.md": ["telegram", "post"],
        "TRUST_LAYER.md": ["trust", "audit"],
    }
    for key, required_terms in checks.items():
        if key in path.name:
            return all(term.lower() in text.lower() for term in required_terms)
    return True


def verify_task_completion(task: dict[str, Any], project_dir: Path, changed_files: list[str]) -> dict[str, Any]:
    changed_files = [normalize_path(path) for path in changed_files]
    non_bookkeeping = [path for path in changed_files if not is_bookkeeping(path)]
    expected_paths = extract_path_candidates(task)
    command_tokens = extract_command_tokens(task)
    expected_tests = extract_expected_test_names(task)
    task_class = detect_task_class(task, expected_paths, command_tokens, expected_tests)

    if task_class == "reaudit-report":
        script_path = project_dir / "scripts" / "re_audit_tasks.py"
        test_path = project_dir / "tests" / "test_re_audit_tasks.py"
        report_path = project_dir / "audit_report.md"
        script_text = read_text(script_path)
        test_text = read_text(test_path)
        report_text = read_text(report_path)
        missing_parts: list[str] = []
        if not script_path.exists():
            missing_parts.append("scripts/re_audit_tasks.py is missing")
        if not test_path.exists():
            missing_parts.append("tests/test_re_audit_tasks.py is missing")
        if not report_path.exists():
            missing_parts.append("audit_report.md is missing")
        if script_text and "audit_report.md" not in script_text:
            missing_parts.append("re_audit_tasks.py does not save audit_report.md")
        if script_text and "Human-readable report saved to" not in script_text:
            missing_parts.append("re_audit_tasks.py does not report saved human-readable output")
        if script_text and "false positive" not in script_text:
            missing_parts.append("re_audit_tasks.py is missing false positive report labeling")
        if script_text and "unclear" not in script_text:
            missing_parts.append("re_audit_tasks.py is missing unclear report labeling")
        if test_text and "audit_report.md" not in test_text:
            missing_parts.append("re_audit tests do not assert report persistence")
        if test_text and "Classification: unclear" not in test_text:
            missing_parts.append("re_audit tests do not cover unclear classification in report")
        if report_text and "# Re-audit Report" not in report_text:
            missing_parts.append("audit_report.md is not a re-audit report")
        if report_text and "## Results" not in report_text:
            missing_parts.append("audit_report.md is missing per-task results")
        if missing_parts:
            return {
                "result": "fail_fix",
                "task_class": task_class,
                "reason": "; ".join(missing_parts),
                "changed_files": changed_files,
                "changed_files_non_bookkeeping": non_bookkeeping,
                "bookkeeping_only": not non_bookkeeping,
                "evidence_files": [path for path in ["scripts/re_audit_tasks.py", "tests/test_re_audit_tasks.py", "audit_report.md"] if (project_dir / path).exists()],
            }
        return {
            "result": "pass",
            "task_class": task_class,
            "reason": "Re-audit reporting verification passed.",
            "changed_files": changed_files,
            "changed_files_non_bookkeeping": non_bookkeeping,
            "bookkeeping_only": not non_bookkeeping,
            "evidence_files": ["scripts/re_audit_tasks.py", "tests/test_re_audit_tasks.py", "audit_report.md"],
        }

    if not non_bookkeeping and task_class not in {"docs-only", "template"}:
        return {
            "result": "fail_fix",
            "task_class": task_class,
            "reason": "Verification failed: only bookkeeping/state/report files changed; no implementation evidence found.",
            "changed_files": changed_files,
            "changed_files_non_bookkeeping": non_bookkeeping,
            "bookkeeping_only": True,
            "evidence_files": [],
        }

    if task_class == "command":
        bot_file = project_dir / "scripts" / "ralph_bot.py"
        bot_text = read_text(bot_file)
        missing_handlers = []
        missing_routes = []
        missing_help = []
        evidence_files = []

        for token in command_tokens:
            handler_candidates = {
                f"cmd_{token}",
                f"cmd_start_{token}",
            }
            route_pattern = re.compile(
                rf'(?:if|elif)\s+cmd\s*==\s*["\']/{re.escape(token)}["\']\s*:\s*\n\s*await\s+([a-zA-Z_][a-zA-Z0-9_]*)\(',
                re.MULTILINE,
            )
            routed_handlers = set(route_pattern.findall(bot_text))
            handler_names = handler_candidates | routed_handlers
            if not any(f"def {name}(" in bot_text for name in handler_names):
                missing_handlers.append(f"/{token}")
            if not re.search(rf'(?:if|elif)\s+cmd\s*==\s*["\']/{re.escape(token)}["\']', bot_text):
                missing_routes.append(f"/{token}")
            if f"/{token}" not in bot_text:
                missing_help.append(f"/{token}")

        for test_file in project_dir.glob("tests/test_*.py"):
            test_text = read_text(test_file)
            if any(f"/{token}" in test_text for token in command_tokens):
                evidence_files.append(normalize_path(str(test_file.relative_to(project_dir))))

        if bot_text:
            evidence_files.append("scripts/ralph_bot.py")

        if missing_handlers or missing_routes or missing_help:
            details = []
            if missing_handlers:
                details.append("missing handlers: " + ", ".join(missing_handlers))
            if missing_routes:
                details.append("missing routing: " + ", ".join(missing_routes))
            if missing_help:
                details.append("missing command/help evidence: " + ", ".join(missing_help))
            return {
                "result": "fail_fix",
                "task_class": task_class,
                "reason": "; ".join(details),
                "changed_files": changed_files,
                "changed_files_non_bookkeeping": non_bookkeeping,
                "bookkeeping_only": False,
                "evidence_files": evidence_files,
            }
        if not any(path.startswith("tests/") for path in evidence_files):
            return {
                "result": "fail_fix",
                "task_class": task_class,
                "reason": "Verification failed: command task is missing test evidence.",
                "changed_files": changed_files,
                "changed_files_non_bookkeeping": non_bookkeeping,
                "bookkeeping_only": False,
                "evidence_files": evidence_files,
            }
        return {
            "result": "pass",
            "task_class": task_class,
            "reason": "Command verification passed with handler, routing, help, and test evidence.",
            "changed_files": changed_files,
            "changed_files_non_bookkeeping": non_bookkeeping,
            "bookkeeping_only": False,
            "evidence_files": sorted(set(evidence_files)),
        }

    if task_class == "script":
        expected_scripts = [path for path in expected_paths if path.startswith("scripts/")]
        missing = [path for path in expected_scripts if not (project_dir / path).exists()]
        if missing:
            return {
                "result": "fail_fix",
                "task_class": task_class,
                "reason": "Verification failed: expected script missing: " + ", ".join(missing),
                "changed_files": changed_files,
                "changed_files_non_bookkeeping": non_bookkeeping,
                "bookkeeping_only": False,
                "evidence_files": [],
            }
        return {
            "result": "pass",
            "task_class": task_class,
            "reason": "Script verification passed.",
            "changed_files": changed_files,
            "changed_files_non_bookkeeping": non_bookkeeping,
            "bookkeeping_only": False,
            "evidence_files": expected_scripts,
        }

    if task_class == "template":
        expected_templates = [path for path in expected_paths if path.startswith("templates/")]
        missing = [path for path in expected_templates if not (project_dir / path).exists()]
        if missing:
            return {
                "result": "fail_fix",
                "task_class": task_class,
                "reason": "Verification failed: expected template missing: " + ", ".join(missing),
                "changed_files": changed_files,
                "changed_files_non_bookkeeping": non_bookkeeping,
                "bookkeeping_only": False,
                "evidence_files": [],
            }
        return {
            "result": "pass",
            "task_class": task_class,
            "reason": "Template verification passed.",
            "changed_files": changed_files,
            "changed_files_non_bookkeeping": non_bookkeeping,
            "bookkeeping_only": False,
            "evidence_files": expected_templates,
        }

    if task_class == "docs-only":
        expected_docs = [path for path in expected_paths if path.startswith("docs/") or path.endswith(".md")]
        if expected_docs and not any((project_dir / path).exists() for path in expected_docs):
            return {
                "result": "fail_fix",
                "task_class": task_class,
                "reason": "Verification failed: expected documentation missing.",
                "changed_files": changed_files,
                "changed_files_non_bookkeeping": non_bookkeeping,
                "bookkeeping_only": False,
                "evidence_files": [],
            }
        evidence = expected_docs or non_bookkeeping
        return {
            "result": "pass",
            "task_class": task_class,
            "reason": "Documentation verification passed.",
            "changed_files": changed_files,
            "changed_files_non_bookkeeping": non_bookkeeping,
            "bookkeeping_only": not non_bookkeeping,
            "evidence_files": evidence,
        }

    if task_class == "tests-only":
        changed_tests = [path for path in non_bookkeeping if path.startswith("tests/")]
        if not changed_tests:
            return {
                "result": "fail_fix",
                "task_class": task_class,
                "reason": "Verification failed: no changed test files found for tests-only task.",
                "changed_files": changed_files,
                "changed_files_non_bookkeeping": non_bookkeeping,
                "bookkeeping_only": not non_bookkeeping,
                "evidence_files": [],
            }
        return {
            "result": "pass",
            "task_class": task_class,
            "reason": "Tests-only verification passed.",
            "changed_files": changed_files,
            "changed_files_non_bookkeeping": non_bookkeeping,
            "bookkeeping_only": False,
            "evidence_files": changed_tests,
        }

    return {
        "result": "pass",
        "task_class": task_class,
        "reason": "Generic implementation evidence detected.",
        "changed_files": changed_files,
        "changed_files_non_bookkeeping": non_bookkeeping,
        "bookkeeping_only": not non_bookkeeping,
        "evidence_files": non_bookkeeping,
    }


def main() -> int:
    try:
        task = json.load(sys.stdin)
    except Exception:
        print(
            json.dumps(
                {
                    "result": "needs_human_review",
                    "task_class": "implementation",
                    "reason": "Verification script could not parse task payload.",
                    "changed_files": [],
                    "changed_files_non_bookkeeping": [],
                    "bookkeeping_only": False,
                    "evidence_files": [],
                },
                ensure_ascii=False,
            )
        )
        return 0

    result = verify_task_completion(task, PROJECT_DIR, load_changed_files())
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
