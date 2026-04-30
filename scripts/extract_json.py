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
JSONISH_TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "’": "'",
        "‘": "'",
    }
)


def normalize_jsonish_text(text: str) -> str:
    return text.translate(JSONISH_TRANSLATION).strip()


def try_load(candidate: str) -> dict | None:
    try:
        value = json.loads(normalize_jsonish_text(candidate))
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
    normalized_text = normalize_jsonish_text(text)
    for idx, char in enumerate(normalized_text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(normalized_text[idx:])
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
    normalized_text = normalize_jsonish_text(text)
    marker_reviews = [
        candidate
        for candidate in collect_marker_reviews(normalized_text)
        if is_review_candidate(candidate) and not is_placeholder_review(candidate)
    ]
    if marker_reviews:
        return marker_reviews[-1]

    direct = try_load(normalized_text)
    if direct is not None and is_review_candidate(direct) and not is_placeholder_review(direct):
        return direct

    fenced_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", normalized_text, flags=re.DOTALL | re.IGNORECASE)
    candidates: list[dict] = []
    for block in fenced_blocks:
        parsed = try_load(block.strip())
        if parsed is not None:
            candidates.append(parsed)
    candidates.extend(collect_json_objects(normalized_text))

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
