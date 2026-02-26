"""Shared fixtures for ralph-dev tests."""
import json
import pytest
from pathlib import Path


@pytest.fixture
def sample_tasks_full():
    """Tasks with all fields (ralph-dev style)."""
    return {
        "tasks": [
            {
                "id": "T01",
                "phase": "P1",
                "title": "Test task",
                "prompt": "Do something",
                "priority": "high",
                "timeout": 120,
                "status": "pending",
                "dependencies": []
            },
            {
                "id": "T02",
                "phase": "P1",
                "title": "Second task",
                "prompt": "Do more",
                "priority": "medium",
                "timeout": 180,
                "status": "done",
                "completed_at": "2025-01-01",
                "dependencies": ["T01"]
            }
        ]
    }


@pytest.fixture
def sample_tasks_minimal():
    """Tasks with minimal fields (like test-ralph-app)."""
    return {
        "tasks": [
            {
                "id": "T01",
                "phase": "P1",
                "title": "Add subtract",
                "prompt": "Add subtract function",
                "timeout": 120,
                "status": "pending"
            },
            {
                "id": "T02",
                "phase": "P1",
                "title": "Add power",
                "prompt": "Add power function",
                "dependencies": ["T01"],
                "timeout": 120,
                "status": "pending"
            }
        ]
    }


@pytest.fixture
def tmp_project(tmp_path, sample_tasks_minimal):
    """Create a temporary project directory with tasks.json."""
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(sample_tasks_minimal, indent=2))
    progress_file = tmp_path / "progress.md"
    progress_file.write_text("# Progress\n")
    (tmp_path / "logs").mkdir()
    return tmp_path
