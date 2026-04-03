from scripts.models import LeadReview, RalphState, TaskRecord


def test_ralph_state_defaults():
    s = RalphState.model_validate({})
    assert s.status == "idle"
    assert s.current_task == ""


def test_ralph_state_full():
    s = RalphState.model_validate(
        {
            "status": "stopped",
            "current_task": "",
            "current_phase_step": "",
            "last_update": "2026-03-15T14:26:22.626483+00:00",
            "message": "Interrupted by signal",
        }
    )
    assert s.status == "stopped"
    assert s.message == "Interrupted by signal"


def test_ralph_state_extra_fields():
    s = RalphState.model_validate({"status": "idle", "unknown_field": "foo"})
    assert s.status == "idle"


def test_task_record_minimal():
    t = TaskRecord.model_validate({"id": "R5-03", "phase": "R5", "title": "Test"})
    assert t.role == "coder"
    assert t.dependencies == []


def test_task_record_full():
    t = TaskRecord.model_validate(
        {
            "id": "R6-01",
            "phase": "R6",
            "title": "Bot: /ask",
            "priority": "high",
            "complexity": "moderate",
            "risk": "low",
            "role": "coder",
            "status": "pending",
            "dependencies": ["R5-03"],
            "acceptance_criteria": ["make test passes"],
            "target_files": ["test_file.py"],
            "revision_notes": "",
            "completed_at": None,
        }
    )
    assert t.role == "coder"
    assert t.complexity == "moderate"


def test_task_record_accepts_reaudit_statuses():
    for status in ("verified_done", "partial", "needs_human_review", "false_positive"):
        t = TaskRecord.model_validate({"id": f"X-{status}", "phase": "X", "title": "Status test", "status": status})
        assert t.status == status


def test_task_record_extra_fields():
    t = TaskRecord.model_validate(
        {
            "id": "X-01",
            "phase": "X",
            "title": "X",
            "unknown_future_field": "bar",
        }
    )
    assert t.id == "X-01"


def test_lead_review_approve():
    r = LeadReview.model_validate(
        {
            "decision": "approve",
            "task_id": "R5-03",
            "summary": "looks good",
            "quality_score": 9,
            "issues": [],
            "fix_instructions": "",
            "alert_reason": "",
            "progress_note": "done",
        }
    )
    assert r.decision == "approve"
    assert r.quality_score == 9


def test_lead_review_fix():
    r = LeadReview.model_validate(
        {
            "decision": "fix",
            "issues": ["missing test"],
            "fix_instructions": "add test for edge case",
        }
    )
    assert r.decision == "fix"
    assert len(r.issues) == 1


def test_lead_review_extra_fields():
    r = LeadReview.model_validate(
        {
            "decision": "approve",
            "new_field_from_future": "ignored",
        }
    )
    assert r.decision == "approve"
