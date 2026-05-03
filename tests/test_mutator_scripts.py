from __future__ import annotations

import json
import os
import shutil
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
AUTO_COMMIT = ROOT / "scripts" / "auto_commit.sh"


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


def init_git_repo(project_dir: Path) -> None:
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_dir, check=True, capture_output=True, text=True)


def write_codex_shim(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "out = None\n"
        "for i, arg in enumerate(args):\n"
        "    if arg == '-o' and i + 1 < len(args):\n"
        "        out = args[i + 1]\n"
        "        break\n"
        "if out is None:\n"
        "    raise SystemExit(2)\n"
        "with open(out, 'w', encoding='utf-8') as fh:\n"
        "    json.dump({'summary': 'Scoped auto-commit test summary', 'commit_message': 'chore(auto-commit): scoped stage'}, fh)\n"
        "print('ok')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


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


def test_auto_commit_scopes_staging_to_current_task_files_and_ignores_runtime_artifacts(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    init_git_repo(project_dir)
    (project_dir / "scripts").mkdir(exist_ok=True)
    shutil.copy2(AUTO_COMMIT, project_dir / "scripts" / "auto_commit.sh")
    (project_dir / "src").mkdir()
    (project_dir / "tests").mkdir(exist_ok=True)
    (project_dir / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    (project_dir / "tests" / "test_app.py").write_text("def test_base():\n    assert True\n", encoding="utf-8")
    (project_dir / "README.md").write_text("# Notes\n", encoding="utf-8")
    (project_dir / ".gitignore").write_text("ralph_state.json\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)

    tasks = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    tasks["tasks"][0]["target_files"] = ["src/app.py", "tests/test_app.py"]
    (project_dir / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    (project_dir / "ralph_state.json").write_text(
        json.dumps({"status": "running", "current_task": "T01"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (project_dir / "tests" / "test_app.py").write_text("def test_base():\n    assert 1 == 1\n", encoding="utf-8")
    (project_dir / "README.md").write_text("# Notes\nunrelated change\n", encoding="utf-8")
    (project_dir / "ralph_state.json").write_text(
        json.dumps({"status": "running", "current_task": "T01", "pid": 123}, indent=2) + "\n",
        encoding="utf-8",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_codex_shim(bin_dir / "codex")

    result = subprocess.run(
        ["bash", str(project_dir / "scripts" / "auto_commit.sh")],
        cwd=project_dir,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Staging files:" in result.stdout
    assert " - src/app.py" in result.stdout
    assert " - tests/test_app.py" in result.stdout
    assert "README.md" not in result.stdout
    assert "ralph_state.json" not in result.stdout

    committed_files = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert "src/app.py" in committed_files
    assert "tests/test_app.py" in committed_files
    assert "SESSION_NOTES.md" in committed_files
    assert "README.md" not in committed_files
    assert "ralph_state.json" not in committed_files

    status_lines = subprocess.run(
        ["git", "status", "--short"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert " M README.md" in status_lines
    assert "!! ralph_state.json" in status_lines


def test_auto_commit_refuses_untracked_files_outside_task_scope(tmp_path: Path) -> None:
    project_dir = make_project(tmp_path)
    init_git_repo(project_dir)
    (project_dir / "scripts").mkdir(exist_ok=True)
    shutil.copy2(AUTO_COMMIT, project_dir / "scripts" / "auto_commit.sh")
    (project_dir / "src").mkdir()
    (project_dir / "tests").mkdir(exist_ok=True)
    (project_dir / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    (project_dir / "tests" / "test_app.py").write_text("def test_base():\n    assert True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_dir, check=True, capture_output=True, text=True)

    tasks = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    tasks["tasks"][0]["target_files"] = ["src/app.py", "tests/test_app.py"]
    (project_dir / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    (project_dir / "ralph_state.json").write_text(
        json.dumps({"status": "running", "current_task": "T01"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (project_dir / "tests" / "test_app.py").write_text("def test_base():\n    assert 1 == 1\n", encoding="utf-8")
    (project_dir / "temp.tmp").write_text("temporary\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_codex_shim(bin_dir / "codex")

    result = subprocess.run(
        ["bash", str(project_dir / "scripts" / "auto_commit.sh")],
        cwd=project_dir,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Refusing auto-commit: unrelated untracked file detected: temp.tmp" in result.stderr
    assert subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "1"
