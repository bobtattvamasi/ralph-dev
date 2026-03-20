#!/usr/bin/env python3
"""Minimal offline eval runner for JSON fixture files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MAX_CASES = 20


def load_fixture(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        cases = data
        fixture_name = path.stem
    elif isinstance(data, dict):
        cases = data.get("cases")
        fixture_name = data.get("name") or path.stem
    else:
        raise ValueError("Eval fixture must be a JSON object or array.")

    if not isinstance(cases, list) or not cases:
        raise ValueError("Eval fixture must contain a non-empty cases list.")

    normalized_cases: list[dict] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Eval case #{index} must be an object.")
        normalized_cases.append(case)

    return {"name": fixture_name, "cases": normalized_cases}


def case_passed(case: dict) -> bool:
    if "passed" in case:
        return bool(case["passed"])
    return case.get("actual") == case.get("expected")


def evaluate_fixture(path: Path, max_cases: int = DEFAULT_MAX_CASES) -> dict:
    if max_cases < 1:
        raise ValueError("max_cases must be at least 1.")

    fixture = load_fixture(path)
    cases = fixture["cases"][:max_cases]
    passed = sum(1 for case in cases if case_passed(case))
    total = len(cases)
    failed = total - passed

    return {
        "fixture": fixture["name"],
        "source": str(path),
        "mode": "offline",
        "processed_cases": total,
        "total_cases": len(fixture["cases"]),
        "pass_count": passed,
        "fail_count": failed,
        "score": passed / total if total else 0.0,
        "bounded": total < len(fixture["cases"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a minimal offline eval from a JSON fixture.")
    parser.add_argument("fixture", help="Path to a JSON eval fixture.")
    parser.add_argument(
        "--max-cases",
        type=int,
        default=DEFAULT_MAX_CASES,
        help=f"Maximum number of cases to process. Defaults to {DEFAULT_MAX_CASES}.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = evaluate_fixture(Path(args.fixture), max_cases=args.max_cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
