from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RalphState(BaseModel):
    status: Literal["idle", "running", "paused", "waiting_human", "stopped", "blocked"] = "idle"
    current_task: str = ""
    current_phase_step: str = ""
    last_update: Optional[str] = None
    message: str = ""
    model_config = ConfigDict(extra="ignore")


class TaskRecord(BaseModel):
    id: str
    phase: str
    title: str
    description: str = ""
    status: Literal[
        "pending",
        "running",
        "done",
        "verified_done",
        "partial",
        "needs_human_review",
        "false_positive",
        "failed",
        "blocked",
    ] = "pending"

    category: str = ""
    priority: Literal["high", "medium", "low"] = "medium"
    complexity: Literal["simple", "moderate", "complex", ""] = ""
    risk: Literal["low", "medium", "high", ""] = ""

    role: str = "coder"
    timeout: Optional[int] = None
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    test_steps: list[str] = Field(default_factory=list)
    context_files: list[str] = Field(default_factory=list)

    completed_at: Optional[str] = None
    revision_notes: str = ""

    model_config = ConfigDict(extra="ignore")


class LeadReview(BaseModel):
    decision: Literal["approve", "fix", "alert"]
    task_id: str = "TASK-ID"
    summary: str = ""
    quality_score: int = 0
    issues: list[str] = Field(default_factory=list)
    fix_instructions: str = ""
    alert_reason: str = ""
    progress_note: str = ""
    model_config = ConfigDict(extra="ignore")
