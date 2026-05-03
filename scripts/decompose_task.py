#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

try:
    from ralph_common import load_tasks_data, resolve_project_dir, save_tasks_data
except ImportError:
    from scripts.ralph_common import load_tasks_data, resolve_project_dir, save_tasks_data


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


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def lower_text(value: object) -> str:
    return normalize_text(value).lower()


def title_description_text(task: dict[str, Any]) -> str:
    return " ".join(filter(None, (lower_text(task.get("title")), lower_text(task.get("description")))))


def acceptance_items(task: dict[str, Any]) -> list[str]:
    raw = task.get("acceptance_criteria") or []
    if isinstance(raw, list):
        return [normalize_text(item) for item in raw if normalize_text(item)]
    text = normalize_text(raw)
    return [text] if text else []


def acceptance_text(task: dict[str, Any]) -> str:
    return " ".join(item.lower() for item in acceptance_items(task))


def target_files(task: dict[str, Any]) -> list[str]:
    raw = task.get("target_files") or []
    if not isinstance(raw, list):
        return []
    return [normalize_text(item) for item in raw if normalize_text(item)]


def has_test_target(task: dict[str, Any]) -> bool:
    for item in target_files(task):
        normalized = item.replace("\\", "/")
        if normalized.startswith("tests/") or "/tests/" in normalized:
            return True
    return False


def has_bootstrap_risk(task: dict[str, Any]) -> bool:
    text = title_description_text(task)
    return any(re.search(pattern, text) for pattern in BOOTSTRAP_PATTERNS)


def acceptance_implies_tests(task: dict[str, Any]) -> bool:
    text = acceptance_text(task)
    return any(re.search(pattern, text) for pattern in TEST_IMPLYING_PATTERNS)


def target_scope_too_narrow(task: dict[str, Any]) -> bool:
    files = target_files(task)
    if not files:
        return True
    if acceptance_implies_tests(task) and not has_test_target(task):
        return True
    if has_bootstrap_risk(task) and not any(item.endswith("ralph-init.sh") for item in files):
        return True
    return False


def child_task(
    parent: dict[str, Any],
    suffix: str,
    title: str,
    description: str,
    files: list[str],
    criteria: list[str],
    complexity: str,
    rationale: str,
) -> dict[str, Any]:
    parent_id = normalize_text(parent.get("id"))
    return {
        "id": f"{parent_id}{suffix}",
        "parent_id": parent_id,
        "phase": normalize_text(parent.get("phase")) or "R20",
        "status": "pending",
        "title": title,
        "description": description,
        "target_files": files,
        "acceptance_criteria": criteria,
        "priority": normalize_text(parent.get("priority")) or "high",
        "complexity": complexity,
        "role": "coder",
        "rationale": rationale,
    }


def kickoff_children(task: dict[str, Any]) -> list[dict[str, Any]]:
    parent_id = normalize_text(task.get("id"))
    return [
        child_task(
            task,
            "A",
            "kickoff CLI argument and mode parsing",
            f"Split {parent_id} so the kickoff command path is introduced in the shell runner without mixing init generation concerns.",
            ["ralph.sh", "src/ralph/resources/ralph.sh"],
            [
                "kickoff <path> <description> is parsed and routed correctly",
                "invalid kickoff invocation returns clear usage output",
            ],
            "simple",
            "Separate CLI/mode parsing from scaffold generation to keep the first change narrow and shell-local.",
        ),
        child_task(
            task,
            "B",
            "kickoff init and scaffold wiring",
            f"Wire kickoff description into init/scaffold generation for {parent_id} so the description is consumed during project creation.",
            ["ralph.sh", "ralph-init.sh", "src/ralph/resources/ralph.sh"],
            [
                "kickoff passes description into the init/scaffold generation path",
                "generated scaffold reflects the provided description during initialization",
            ],
            "moderate",
            "The current target_files are too narrow because acceptance depends on init/scaffold behavior outside ralph.sh alone.",
        ),
        child_task(
            task,
            "C",
            "kickoff focused test coverage",
            f"Add focused regression coverage for the kickoff command introduced by {parent_id}.",
            ["tests/test_ralph_shell_helpers.py"],
            [
                "focused test covers kickoff path",
                "test verifies directory and .ralph scaffold creation",
            ],
            "simple",
            "Acceptance implies focused tests, so test work should be explicit instead of hidden as out-of-scope diff.",
        ),
    ]


def generic_children(task: dict[str, Any]) -> list[dict[str, Any]]:
    files = target_files(task)
    criteria = acceptance_items(task) or [f"{normalize_text(task.get('id'))} behavior is implemented"]
    title = normalize_text(task.get("title")) or normalize_text(task.get("id")) or "task"
    children = [
        child_task(
            task,
            "A",
            f"{title} — implementation slice",
            f"Narrow implementation slice for {normalize_text(task.get('id'))}.",
            files or ["<fill target_files>"],
            criteria[:2],
            "moderate" if lower_text(task.get("complexity")) == "complex" else "simple",
            "Split the primary implementation work out of the oversized parent task.",
        )
    ]
    if target_scope_too_narrow(task):
        children.append(
            child_task(
                task,
                "B",
                f"{title} — focused tests",
                f"Add focused tests needed to make {normalize_text(task.get('id'))} approvable.",
                ["tests/test_placeholder.py"],
                ["focused tests cover the changed behavior"],
                "simple",
                "Acceptance implies tests or the original scope is too narrow, so test work should be explicit.",
            )
        )
    if lower_text(task.get("complexity")) == "complex" or task.get("scope_too_wide") is True:
        children.append(
            child_task(
                task,
                "C",
                f"{title} — helper or wiring split",
                f"Extract supporting helper or wiring work from {normalize_text(task.get('id'))}.",
                files[:1] or ["<fill helper target_files>"],
                ["helper/wiring work is isolated from the main implementation slice"],
                "simple",
                "A separate helper/wiring slice reduces retry blast radius for unattended execution.",
            )
        )
    return children


def build_proposal(task: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if has_bootstrap_risk(task):
        reasons.append("bootstrap_risk")
    if target_scope_too_narrow(task):
        reasons.append("target_scope_too_narrow")
    if acceptance_implies_tests(task) and not has_test_target(task):
        reasons.append("missing_test_target")
    if lower_text(task.get("complexity")) == "complex":
        reasons.append("complex_task")
    if task.get("scope_too_wide") is True or (task.get("selection_warnings") or []):
        reasons.append("broad_scope")

    if has_bootstrap_risk(task):
        children = kickoff_children(task)
    else:
        children = generic_children(task)

    return {
        "parent_id": normalize_text(task.get("id")),
        "rationale": reasons,
        "children": children,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--apply", action="store_true")
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
    task = next((item for item in tasks if isinstance(item, dict) and normalize_text(item.get("id")) == args.task_id), None)
    if task is None:
        print(f"ERROR: task not found: {args.task_id}", file=sys.stderr)
        return 1

    proposal = build_proposal(task)

    if args.apply:
        existing_ids = {normalize_text(item.get("id")) for item in tasks if isinstance(item, dict)}
        additions = [child for child in proposal["children"] if normalize_text(child.get("id")) not in existing_ids]
        if additions:
            data["tasks"].extend(additions)
            save_tasks_data(project_dir, data)

    print(json.dumps(proposal, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
