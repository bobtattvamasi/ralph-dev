from __future__ import annotations

from pathlib import Path

import pytest

import scripts.check_prompt_budgets as prompt_budgets


@pytest.mark.parametrize(
    ("profile", "minimum_limit"),
    [
        ("narrow", 15000),
        ("broad", 25000),
    ],
)
def test_prompt_budget_runner_cases_stay_under_expected_limit(tmp_path: Path, profile: str, minimum_limit: int) -> None:
    runner_path = prompt_budgets.build_prompt_runner_script()
    try:
        tokens, expected_limit = prompt_budgets.run_case(runner_path, tmp_path, profile)
    finally:
        runner_path.unlink(missing_ok=True)

    assert expected_limit == minimum_limit
    assert tokens > 0
    assert tokens < expected_limit


def test_create_test_project_copies_required_prompt_context(tmp_path: Path) -> None:
    project_dir = prompt_budgets.create_test_project(tmp_path)

    for relative_path in (
        "AGENTS.md",
        "ARCHITECTURE.md",
        "MEMORY_SYSTEM.md",
        "AGENTS_CODER.md",
        "AGENTS_LEAD.md",
        ".ralph/memory/core.md",
        ".ralph/memory/recent.md",
    ):
        assert (project_dir / relative_path).exists(), relative_path

    assert (project_dir / "src" / "prompt_builder.ts").read_text(encoding="utf-8")
    assert (project_dir / "scripts" / "narrow_target.py").read_text(encoding="utf-8") == "TARGET = False\n"
