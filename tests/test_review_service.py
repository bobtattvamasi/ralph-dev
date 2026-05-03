from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import review_service


FIXTURE_REVIEW_TEXTS = [
    '{"decision":"approve","task_id":"FX-01","summary":"Looks good.","issues":[]}',
    '{"decision":"fix","task_id":"FX-02","summary":"Needs one correction.","issues":["missing test"]}',
    '{"decision":"alert","task_id":"FX-03","summary":"Requires human attention.","issues":[]}',
    'BEGIN_RALPH_REVIEW_JSON\n{"decision":"approve","task_id":"FX-04","summary":"Ship it.","issues":[]}\nEND_RALPH_REVIEW_JSON',
    'BEGIN_RALPH_REVIEW_JSON\n{"decision":"fix","task_id":"FX-05","summary":"Guard is missing.","issues":["retry path"]}\nEND_RALPH_REVIEW_JSON',
    '{"decision":"approve","task_id":"FX-06","summary":"Stable parser output.","issues":[]}',
    '{"decision":"alert","task_id":"FX-07","summary":"Dependency conflict.","issues":["blocked dependency"]}',
    '{"decision":"fix","task_id":"FX-08","summary":"Scope mismatch.","issues":["target_files incomplete"]}',
    '{"decision":"approve","task_id":"FX-09","summary":"Archived review fallback fixture.","issues":[]}',
    '{"decision":"fix","task_id":"FX-10","summary":"Needs narrower patch.","issues":["broad scope"]}',
]


def load_replay_review_texts(audit_dir: Path, limit: int = 10) -> list[str]:
    review_texts: list[str] = []

    for path in sorted(audit_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        review = data.get("review")
        raw = review.get("raw", "") if isinstance(review, dict) else ""
        if not isinstance(raw, str) or not raw.strip():
            continue
        candidate = review_service.extract_review(raw)
        if candidate is None:
            continue
        normalized, error = review_service.normalize_review(candidate)
        if normalized is None or error is not None:
            continue
        review_texts.append(raw)
        if len(review_texts) >= limit:
            return review_texts

    for raw in FIXTURE_REVIEW_TEXTS:
        if len(review_texts) >= limit:
            break
        review_texts.append(raw)

    return review_texts


def test_review_service_replays_up_to_ten_archived_lead_outputs_without_spurious_fix_fallback() -> None:
    review_texts = load_replay_review_texts(REPO_ROOT / ".ralph" / "audit", limit=10)

    assert len(review_texts) == 10

    for raw in review_texts:
        first = review_service.parse_review_inputs("", raw)
        second = review_service.parse_review_inputs("", raw)
        validated = review_service.validate_review_text(raw)

        assert first == second
        assert first["status"] == "ok"
        assert first["source"] == "lead_output"
        assert first["reason"] == ""
        assert first["review"]["decision"] in {"approve", "fix", "alert"}
        assert validated["decision"] == first["review"]["decision"]
        assert validated.get("fix_instructions") != review_service.FAIL_CLOSED_REASON


def test_review_service_uses_deterministic_fixture_reviews_when_archive_set_is_too_small(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    (audit_dir / "single.json").write_text(
        json.dumps(
            {
                "review": {
                    "raw": 'BEGIN_RALPH_REVIEW_JSON\n{"decision":"approve","task_id":"ARCH-01","summary":"Archive sample.","issues":[]}\nEND_RALPH_REVIEW_JSON'
                }
            }
        ),
        encoding="utf-8",
    )

    review_texts = load_replay_review_texts(audit_dir, limit=10)

    assert len(review_texts) == 10
    assert review_texts[0].startswith("BEGIN_RALPH_REVIEW_JSON")
    assert review_texts[1:] == FIXTURE_REVIEW_TEXTS[:9]

