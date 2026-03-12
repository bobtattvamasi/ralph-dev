#!/usr/bin/env python3
"""Extract the first valid JSON object from mixed model output."""

from __future__ import annotations

import json
import re
import sys
from json import JSONDecodeError


def try_load(candidate: str) -> dict | None:
    try:
        value = json.loads(candidate)
    except JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def extract_json_object(text: str) -> dict | None:
    fenced_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced_blocks:
        parsed = try_load(block.strip())
        if parsed is not None:
            return parsed

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[idx:])
        except JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    start_positions = [idx for idx, char in enumerate(text) if char == "{"]
    end_positions = [idx for idx, char in enumerate(text) if char == "}"]
    for start in start_positions:
        for end in reversed(end_positions):
            if end <= start:
                continue
            parsed = try_load(text[start : end + 1].strip())
            if parsed is not None:
                return parsed
    return None


def main() -> None:
    text = sys.stdin.read()
    parsed = extract_json_object(text)
    if parsed is None:
        print("{}")
        sys.exit(1)
    print(json.dumps(parsed, ensure_ascii=False))


if __name__ == "__main__":
    main()
