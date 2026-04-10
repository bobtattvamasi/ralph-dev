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


def extract_json_object(text: str) -> dict | None:
    marker_blocks = re.findall(
        rf"{REVIEW_MARKER_START}\s*(\{{.*?\}})\s*{REVIEW_MARKER_END}",
        text,
        flags=re.DOTALL,
    )
    # R20-03: filter marker blocks — drop placeholders/unparseable, take last real one
    real_marker_reviews: list[dict] = []
    for block in marker_blocks:
        parsed = try_load(block.strip())
        if parsed is not None and is_review_candidate(parsed) and not is_placeholder_review(parsed):
            real_marker_reviews.append(parsed)
    if len(real_marker_reviews) >= 1:
        # Take last — Codex echoes template first, real review last
        return real_marker_reviews[-1]

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
        if not is_review_candidate(candidate) or is_placeholder_review(candidate):
            continue
        key = json.dumps(candidate, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        trusted.append(candidate)

    if len(trusted) != 1:
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
