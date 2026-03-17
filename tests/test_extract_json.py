from __future__ import annotations

from scripts.extract_json import extract_json_object


def test_extract_json_prefers_marked_final_review_over_template() -> None:
    text = """
```json
{"decision":"approve","task_id":"TASK-ID","summary":"one line summary","quality_score":8,"issues":[],"fix_instructions":"","alert_reason":"","progress_note":""}
```

BEGIN_RALPH_REVIEW_JSON
{"decision":"fix","task_id":"R10-02","summary":"Need another pass","quality_score":3,"issues":["parser drift"],"fix_instructions":"Return one authoritative JSON review only.","alert_reason":"","progress_note":"Fail closed"}
END_RALPH_REVIEW_JSON
"""

    parsed = extract_json_object(text)

    assert parsed is not None
    assert parsed["decision"] == "fix"
    assert parsed["task_id"] == "R10-02"


def test_extract_json_rejects_placeholder_template_json() -> None:
    text = """
BEGIN_RALPH_REVIEW_JSON
{"decision":"approve","task_id":"TASK-ID","summary":"one line summary","quality_score":8,"issues":[],"fix_instructions":"","alert_reason":"","progress_note":""}
END_RALPH_REVIEW_JSON
"""

    assert extract_json_object(text) is None


def test_extract_json_rejects_ambiguous_multiple_reviews_without_markers() -> None:
    text = """
{"decision":"fix","task_id":"R10-02","summary":"First review","quality_score":4,"issues":["a"],"fix_instructions":"Fix it.","alert_reason":"","progress_note":""}
{"decision":"approve","task_id":"R10-02","summary":"Second review","quality_score":8,"issues":[],"fix_instructions":"","alert_reason":"","progress_note":""}
"""

    assert extract_json_object(text) is None
