#!/usr/bin/env python3
"""Compute an auto-pilot trust score from recent Ralph audit reviews."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CHECKLIST_FIELDS = (
    "scope_ok",
    "tests_ok",
    "acceptance_ok",
    "regressions_ok",
    "quality_ok",
)


def _bool_score(value: Any) -> float:
    return 1.0 if bool(value) else 0.0


def _approved_value(payload: dict[str, Any]) -> bool:
    if "approved" in payload:
        return bool(payload.get("approved"))
    if "decision" in payload:
        return str(payload.get("decision", "")).strip().lower() == "approve"
    return False


def _quality_score(payload: dict[str, Any]) -> float | None:
    raw = payload.get("quality_score")
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    value = max(0.0, min(100.0, value))
    return value / 100.0


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _review_payload(review: dict[str, Any]) -> dict[str, Any]:
    parsed_review = review.get("review", {}).get("parsed")
    if isinstance(parsed_review, dict):
        return parsed_review
    return review


def _task_score(review: dict[str, Any]) -> tuple[float, bool]:
    payload = _review_payload(review)
    approved_score = _bool_score(_approved_value(payload))
    checklist = payload.get("checklist")
    quality_score = _quality_score(payload)
    if not isinstance(checklist, dict):
        if quality_score is not None:
            return (approved_score * 0.5) + (quality_score * 0.5), False
        return approved_score, False

    checklist_values = [_bool_score(checklist.get(field)) for field in CHECKLIST_FIELDS]
    checklist_score = sum(checklist_values) / len(CHECKLIST_FIELDS)
    quality_component = quality_score if quality_score is not None else approved_score
    score = (approved_score * 0.4) + (checklist_score * 0.3) + (quality_component * 0.3)
    return score, True


def compute_trust_score(audit_dir: str, window: int) -> dict[str, Any]:
    if window <= 0:
        raise ValueError("window must be > 0")

    audit_path = Path(audit_dir)
    files = sorted(
        (path for path in audit_path.glob("*.json") if path.is_file()),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    selected_files = files[-window:]

    details: list[dict[str, Any]] = []
    total_score = 0.0

    for path in selected_files:
        review = _load_json(path)
        if review is None:
            continue

        payload = _review_payload(review)
        score, has_checklist = _task_score(review)
        total_score += score
        details.append(
            {
                "file": path.name,
                "decision": payload.get("decision"),
                "quality_score": payload.get("quality_score"),
                "approved": _approved_value(payload),
                "has_checklist": has_checklist,
                "task_score": round(score, 4),
            }
        )

    tasks_evaluated = len(details)
    trust_score = (total_score / tasks_evaluated) * 100 if tasks_evaluated else 0.0

    return {
        "trust_score": round(trust_score, 2),
        "window": window,
        "tasks_evaluated": tasks_evaluated,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Ralph auto-pilot trust score.")
    parser.add_argument(
        "--window",
        type=int,
        default=20,
        help="Number of most recent audit files to evaluate (default: 20).",
    )
    parser.add_argument(
        "--audit-dir",
        default=".ralph/audit",
        help="Directory containing audit JSON files (default: .ralph/audit).",
    )
    args = parser.parse_args()

    result = compute_trust_score(args.audit_dir, args.window)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
