from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.auto_update as auto_update
import scripts.ralph_notify as ralph_notify
import scripts.update_memory as update_memory


ROOT = Path(__file__).resolve().parent.parent
UPDATE_PROGRESS = ROOT / "scripts" / "update_progress.py"


def make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    (project_dir / "scripts").mkdir(parents=True)
    (project_dir / ".ralph" / "memory").mkdir(parents=True)
    (project_dir / "tasks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project": "mutator-tests",
                "tasks": [
                    {
                        "id": "T01",
                        "title": "Primary task",
                        "status": "pending",
                        "target_files": ["test_file.py"],
                    },
                    {
                        "id": "T02",
                        "title": "Dependent task",
                        "status": "done",
                        "dependencies": ["T01"],
                        "completed_at": "2026-03-01",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / "progress.md").write_text("# Progress\n\n", encoding="utf-8")
    return project_dir


def test_auto_update_marks_task_complete_resets_dependents_and_appends_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = make_project(tmp_path)
    monkeypatch.setattr(auto_update, "__file__", str(project_dir / "scripts" / "auto_update.py"))

    git_calls: list[list[str]] = []

    def fake_run_git(_project_dir: Path, args: list[str]) -> SimpleNamespace:
        git_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(auto_update, "run_git", fake_run_git)
    monkeypatch.setattr(sys, "argv", ["auto_update.py", "T01", "verified_done", "Closed", "cleanly"])

    rc = auto_update.main()

    assert rc == 0
    tasks = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    task_map = {task["id"]: task for task in tasks}
    assert task_map["T01"]["status"] == "verified_done"
    assert task_map["T01"]["completed_at"]
    assert task_map["T02"]["status"] == "pending"
    assert "completed_at" not in task_map["T02"]
    progress = (project_dir / "progress.md").read_text(encoding="utf-8")
    assert "### " in progress
    assert "Завершена задача T01" in progress
    assert "- Статус: verified_done" in progress
    assert "- Комментарий: Closed cleanly" in progress
    assert git_calls == [["add", "tasks.json", "progress.md"], ["commit", "-m", "feat(T01): auto update status and progress"]]


def test_auto_update_rejects_missing_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    project_dir = make_project(tmp_path)
    monkeypatch.setattr(auto_update, "__file__", str(project_dir / "scripts" / "auto_update.py"))
    monkeypatch.setattr(sys, "argv", ["auto_update.py", "T99", "done"])

    rc = auto_update.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert "Task not found: T99" in captured.err


def test_update_memory_prepends_latest_entry_and_keeps_only_five(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = make_project(tmp_path)
    recent_path = project_dir / ".ralph" / "memory" / "recent.md"
    recent_path.write_text(
        "# Recent Task History\n\n"
        "### T05: Older 5\n- Files: e.py\n- Result: approved\n- Notes: fifth\n- Time: 2026-03-05T00:00:00Z\n\n"
        "### T04: Older 4\n- Files: d.py\n- Result: approved\n- Notes: fourth\n- Time: 2026-03-04T00:00:00Z\n\n"
        "### T03: Older 3\n- Files: c.py\n- Result: approved\n- Notes: third\n- Time: 2026-03-03T00:00:00Z\n\n"
        "### T02: Older 2\n- Files: b.py\n- Result: approved\n- Notes: second\n- Time: 2026-03-02T00:00:00Z\n\n"
        "### T01: Older 1\n- Files: a.py\n- Result: approved\n- Notes: first\n- Time: 2026-03-01T00:00:00Z\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RALPH_PROJECT_DIR", str(project_dir))
    monkeypatch.setattr(sys, "argv", ["update_memory.py", "T06", "Newest", "scripts/new.py", "approved", "Fresh", "note"])

    rc = update_memory.main()

    assert rc == 0
    recent = recent_path.read_text(encoding="utf-8")
    assert recent.startswith("# Recent Task History\n\n### T06: Newest")
    assert "- Files: scripts/new.py" in recent
    assert "- Result: approved" in recent
    assert "- Notes: Fresh note" in recent
    assert recent.count("### ") == 5
    assert "### T01: Older 1" not in recent


def test_update_progress_appends_timestamped_entry_using_project_env(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    result = subprocess.run(
        [sys.executable, str(UPDATE_PROGRESS), "T01", "Operator note"],
        cwd=project_dir,
        env={**os.environ, "RALPH_PROJECT_DIR": str(project_dir)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Progress updated: T01" in result.stdout
    progress = (project_dir / "progress.md").read_text(encoding="utf-8")
    assert "**T01**" in progress
    assert "Operator note" in progress
    assert "UTC" in progress


def test_ralph_notify_posts_html_message_with_timeout_and_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = request.full_url
        captured["payload"] = request.data.decode()
        captured["timeout"] = timeout
        return object()

    monkeypatch.setattr(ralph_notify, "TOKEN", "token")
    monkeypatch.setattr(ralph_notify, "CHAT_ID", "chat")
    monkeypatch.setattr(ralph_notify, "TELEGRAM_TIMEOUT_SEC", 17)
    monkeypatch.setattr(ralph_notify.urllib.request, "urlopen", fake_urlopen)

    ralph_notify.send("x" * 5000)
    payload = urllib.parse.parse_qs(str(captured["payload"]))

    assert captured["url"] == "https://api.telegram.org/bottoken/sendMessage"
    assert payload["chat_id"] == ["chat"]
    assert payload["parse_mode"] == ["HTML"]
    assert len(payload["text"][0]) == 4096
    assert captured["timeout"] == 17


def test_ralph_notify_logs_transport_errors(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(ralph_notify, "TOKEN", "token")
    monkeypatch.setattr(ralph_notify, "CHAT_ID", "chat")

    def fake_urlopen(_request, timeout):  # type: ignore[no-untyped-def]
        raise urllib.error.URLError(f"timeout={timeout}")

    monkeypatch.setattr(ralph_notify.urllib.request, "urlopen", fake_urlopen)

    with caplog.at_level("ERROR"):
        ralph_notify.send("ping")

    assert "Notification failed" in caplog.text
