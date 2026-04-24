#!/usr/bin/env python3
"""Extract one trustworthy Tech Lead review JSON object from mixed model output."""

from __future__ import annotations

import json
import re
import sys
from json import JSONDecodeError


REVIEW_MARKER_START = "BEGIN_RALPH_REVIEW_JSON"
REVIEW_MARKER_END = "END_RALPH_REVIEW_JSON"
PLACEHOLDER_TASK_ID = "TASK-ID"
PLACEHOLDER_SUMMARY = "one line summary"
VALID_DECISIONS = {"approve", "fix", "alert", "done"}


def try_load(candidate: str) -> dict | None:
    try:
        value = json.loads(candidate)
    except JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def is_review_candidate(value: dict) -> bool:
    return isinstance(value, dict) and str(value.get("decision", "")).strip() in VALID_DECISIONS


def is_placeholder_review(value: dict) -> bool:
    task_id = str(value.get("task_id", "")).strip()
    summary = str(value.get("summary", "")).strip().lower()
    return task_id == PLACEHOLDER_TASK_ID or summary == PLACEHOLDER_SUMMARY


def normalize_issues(issues: object) -> list[str]:
    if isinstance(issues, list):
        return [str(item).strip() for item in issues if str(item).strip()]
    if issues is None:
        return []
    text = str(issues).strip()
    return [text] if text else []


def canonicalize_review(value: dict) -> dict | None:
    nested_review = value.get("review")
    if isinstance(nested_review, dict):
        raw_review = nested_review.get("raw")
        if isinstance(raw_review, str) and raw_review.strip():
            parsed_raw = extract_json_object(raw_review)
            if parsed_raw is not None:
                return parsed_raw
        parsed_review = nested_review.get("parsed")
        if isinstance(parsed_review, dict):
            parsed_structured = canonicalize_review(parsed_review)
            if parsed_structured is not None:
                return parsed_structured

    if not is_review_candidate(value) or is_placeholder_review(value):
        return None

    decision = str(value.get("decision", "")).strip()
    if decision == "done":
        decision = "approve"

    return {
        "decision": decision,
        "quality_score": value.get("quality_score", "?"),
        "issues": normalize_issues(value.get("issues")),
    }


def collect_json_objects(text: str) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[idx:])
        except JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        key = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(parsed)
    return candidates


def collect_marker_reviews(text: str) -> list[dict]:
    candidates: list[dict] = []
    start = 0
    while True:
        marker_start = text.find(REVIEW_MARKER_START, start)
        if marker_start == -1:
            break
        payload_start = marker_start + len(REVIEW_MARKER_START)
        marker_end = text.find(REVIEW_MARKER_END, payload_start)
        if marker_end == -1:
            break
        parsed = try_load(text[payload_start:marker_end].strip())
        if parsed is not None:
            candidates.append(parsed)
        start = marker_end + len(REVIEW_MARKER_END)
    return candidates


def extract_json_object(text: str) -> dict | None:
    direct = try_load(text.strip())
    if direct is not None:
        direct_review = canonicalize_review(direct)
        if direct_review is not None:
            return direct_review

    marker_reviews = [
        canonicalize_review(candidate)
        for candidate in collect_marker_reviews(text)
    ]
    marker_reviews = [candidate for candidate in marker_reviews if candidate is not None]
    if marker_reviews:
        return marker_reviews[-1]

    fenced_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates: list[dict] = []
    for block in fenced_blocks:
        parsed = try_load(block.strip())
        if parsed is not None:
            candidates.append(parsed)
    candidates.extend(collect_json_objects(text))

    trusted: list[dict] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = canonicalize_review(candidate)
        if normalized is None:
            continue
        key = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        trusted.append(normalized)

    if not trusted:
        return None
    if len(trusted) > 1:
        return None
    return trusted[0]


def main() -> None:
    text = sys.stdin.read()
    parsed = extract_json_object(text)
    if parsed is None:
        print("{}")
        sys.exit(1)
    print(json.dumps(parsed, ensure_ascii=False))


if __name__ == "__main__":
    main()
