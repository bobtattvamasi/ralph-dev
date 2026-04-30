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


def test_extract_json_accepts_json_in_markdown_fence_with_wrapper_text() -> None:
    text = """
Lead review complete.

```json
{"decision":"approve","task_id":"R10-02","summary":"Looks good","quality_score":8,"issues":[],"fix_instructions":"","alert_reason":"","progress_note":""}
```

Ship it.
"""

    parsed = extract_json_object(text)

    assert parsed is not None
    assert parsed["decision"] == "approve"
    assert parsed["task_id"] == "R10-02"


def test_extract_json_accepts_wrapped_payload_with_smart_quotes() -> None:
    text = """
Final answer below:
{
  “decision”: “fix”,
  “task_id”: “R10-03”,
  “summary”: “Need one more pass”,
  “quality_score”: 4,
  “issues”: [“parser drift”],
  “fix_instructions”: “Return one final JSON object only.”,
  “alert_reason”: “”, 
  “progress_note”: “”
}
Thanks.
"""

    parsed = extract_json_object(text)

    assert parsed is not None
    assert parsed["decision"] == "fix"
    assert parsed["task_id"] == "R10-03"


def test_extract_json_returns_none_for_empty_payload() -> None:
    assert extract_json_object("") is None


def test_extract_json_returns_none_for_unrecoverable_broken_payload() -> None:
    text = """
```json
{"decision":"approve","task_id":"R10-02"
```
"""

    assert extract_json_object(text) is None


def test_extract_json_accepts_valid_direct_payload() -> None:
    text = '{"decision":"alert","task_id":"R10-05","summary":"Need human review","quality_score":2,"issues":["risk"],"fix_instructions":"Escalate.","alert_reason":"Human needed","progress_note":"blocked"}'

    parsed = extract_json_object(text)

    assert parsed is not None
    assert parsed["decision"] == "alert"
