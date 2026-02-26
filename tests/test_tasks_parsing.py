"""Test that task parsing handles missing fields gracefully."""
import json
import pytest
from pathlib import Path


def load_tasks(path: Path):
    """Load tasks from JSON file."""
    with open(path) as f:
        data = json.load(f)
    return data.get("tasks", [])


def get_task_field(task: dict, field: str, default=None):
    """Safely get task field — mirrors what bot should do."""
    return task.get(field, default)


class TestTaskParsing:
    """Test task field access patterns."""

    def test_load_full_tasks(self, tmp_path, sample_tasks_full):
        f = tmp_path / "tasks.json"
        f.write_text(json.dumps(sample_tasks_full))
        tasks = load_tasks(f)
        assert len(tasks) == 2
        assert tasks[0]["id"] == "T01"
        assert tasks[0]["priority"] == "high"

    def test_load_minimal_tasks(self, tmp_path, sample_tasks_minimal):
        f = tmp_path / "tasks.json"
        f.write_text(json.dumps(sample_tasks_minimal))
        tasks = load_tasks(f)
        assert len(tasks) == 2
        assert tasks[0]["id"] == "T01"

    def test_missing_priority_uses_default(self, sample_tasks_minimal):
        task = sample_tasks_minimal["tasks"][0]
        assert get_task_field(task, "priority", "medium") == "medium"

    def test_missing_dependencies_uses_default(self, sample_tasks_minimal):
        task = sample_tasks_minimal["tasks"][0]
        assert get_task_field(task, "dependencies", []) == []

    def test_missing_timeout_uses_default(self, sample_tasks_minimal):
        task = sample_tasks_minimal["tasks"][0]
        # This one HAS timeout, so it should return it
        assert get_task_field(task, "timeout", 180) == 120

    def test_missing_completed_at(self, sample_tasks_minimal):
        task = sample_tasks_minimal["tasks"][0]
        assert get_task_field(task, "completed_at", "") == ""

    def test_required_fields_exist(self, sample_tasks_minimal):
        for task in sample_tasks_minimal["tasks"]:
            assert "id" in task
            assert "title" in task
            assert "status" in task

    def test_empty_tasks_file(self, tmp_path):
        f = tmp_path / "tasks.json"
        f.write_text('{"tasks": []}')
        tasks = load_tasks(f)
        assert tasks == []

    def test_no_tasks_key(self, tmp_path):
        f = tmp_path / "tasks.json"
        f.write_text('{"project": "test"}')
        tasks = load_tasks(f)
        assert tasks == []
