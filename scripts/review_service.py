#!/usr/bin/env python3
"""Authoritative parser for Ralph Tech Lead review JSON."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any

try:
    from extract_json import PLACEHOLDER_SUMMARY, PLACEHOLDER_TASK_ID, extract_json_object, try_load
except ImportError:
    from scripts.extract_json import PLACEHOLDER_SUMMARY, PLACEHOLDER_TASK_ID, extract_json_object, try_load


VALID_DECISIONS = {"approve", "fix", "alert", "done"}
DEFAULT_SKIP_REASON = "Tech Lead review JSON malformed or missing; skipped to avoid spurious fix fallback."


def read_text(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def nested_raw_review_text(text: str) -> str | None:
    parsed = try_load(text)
    if not isinstance(parsed, dict):
        return None

    review = parsed.get("review")
    if isinstance(review, dict):
        raw = review.get("raw")
        if isinstance(raw, str) and raw.strip():
            return raw

    raw = parsed.get("raw")
    if isinstance(raw, str) and raw.strip():
        return raw

    return None


def extract_review(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None

    parsed = extract_json_object(text)
    if parsed is not None:
        return parsed

    nested = nested_raw_review_text(text)
    if nested and nested != text:
        return extract_json_object(nested)

    return None


def normalize_issues(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def normalize_review(review: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    task_id = str(review.get("task_id", "")).strip()
    summary = str(review.get("summary", "")).strip()
    decision = str(review.get("decision", "")).strip()

    if task_id == PLACEHOLDER_TASK_ID or summary.lower() == PLACEHOLDER_SUMMARY:
        return None, "Tech Lead returned placeholder/template JSON and could not be trusted safely."

    if decision == "done":
        decision = "approve"
    if decision not in VALID_DECISIONS - {"done"}:
        return None, "Tech Lead output could not be parsed safely."

    normalized = dict(review)
    normalized["decision"] = decision
    normalized["issues"] = normalize_issues(review.get("issues"))
    return normalized, None


def parse_review_inputs(review_text: str, lead_output_text: str) -> dict[str, Any]:
    review_present = bool(review_text.strip())
    lead_present = bool(lead_output_text.strip())

    review_candidate = extract_review(review_text)
    if review_present:
        if review_candidate is None:
            return {
                "status": "skip",
                "source": "review_file_malformed",
                "reason": DEFAULT_SKIP_REASON,
                "review": {},
            }
        normalized, error = normalize_review(review_candidate)
        if normalized is None:
            return {
                "status": "skip",
                "source": "review_file_malformed",
                "reason": error or DEFAULT_SKIP_REASON,
                "review": {},
            }
        return {
            "status": "ok",
            "source": "review_file",
            "reason": "",
            "review": normalized,
        }

    lead_candidate = extract_review(lead_output_text)
    if lead_present:
        if lead_candidate is None:
            return {
                "status": "skip",
                "source": "lead_output_malformed",
                "reason": DEFAULT_SKIP_REASON,
                "review": {},
            }
        normalized, error = normalize_review(lead_candidate)
        if normalized is None:
            return {
                "status": "skip",
                "source": "lead_output_malformed",
                "reason": error or DEFAULT_SKIP_REASON,
                "review": {},
            }
        return {
            "status": "ok",
            "source": "lead_output",
            "reason": "",
            "review": normalized,
        }

    return {
        "status": "skip",
        "source": "unparsed_skipped",
        "reason": DEFAULT_SKIP_REASON,
        "review": {},
    }


def shell_assignments(result: dict[str, Any]) -> str:
    assignments = {
        "REVIEW_SERVICE_STATUS": str(result.get("status", "skip")),
        "REVIEW_JSON_SOURCE": str(result.get("source", "unparsed_skipped")),
        "REVIEW_SERVICE_REASON": str(result.get("reason", DEFAULT_SKIP_REASON)),
        "REVIEW_JSON": json.dumps(result.get("review", {}), ensure_ascii=False),
    }
    return "\n".join(f"{key}={shlex.quote(value)}" for key, value in assignments.items())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("parse", "parse-shell"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--review-file", default=None)
        subparser.add_argument("--lead-output", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = parse_review_inputs(read_text(args.review_file), read_text(args.lead_output))

    if args.command == "parse":
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "parse-shell":
        print(shell_assignments(result))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
