from __future__ import annotations

import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ralph import cli as ralph_cli


def test_build_command_for_next_uses_existing_selector_script() -> None:
    command = ralph_cli.build_command(Namespace(command="next"))

    assert command == [
        sys.executable,
        str(ralph_cli.resource_path("scripts", "next_task.py")),
    ]


def test_build_command_for_explain_uses_auto_safe_explain_flags() -> None:
    command = ralph_cli.build_command(Namespace(command="explain"))

    assert command == [
        sys.executable,
        str(ralph_cli.resource_path("scripts", "next_task.py")),
        "--auto-safe",
        "--explain",
    ]


def test_build_command_for_auto_safe_uses_ralph_shell() -> None:
    command = ralph_cli.build_command(Namespace(command="auto", safe=True))

    assert command == [
        "bash",
        str(ralph_cli.resource_path("ralph.sh")),
        "auto",
    ]


def test_build_command_for_task_uses_ralph_shell_with_task_id() -> None:
    command = ralph_cli.build_command(Namespace(command="task", task_id="R20-22"))

    assert command == [
        "bash",
        str(ralph_cli.resource_path("ralph.sh")),
        "task",
        "R20-22",
    ]


def test_build_doctor_commands_uses_existing_lightweight_checks() -> None:
    commands = ralph_cli.build_doctor_commands()

    assert commands == [
        ("git status --short", ["git", "status", "--short"]),
        ("python -m json.tool tasks.json", [sys.executable, "-m", "json.tool", "tasks.json"]),
        (
            "python -m pytest tests/test_shell_parity.py -q",
            [sys.executable, "-m", "pytest", "tests/test_shell_parity.py", "-q"],
        ),
        (
            "python scripts/next_task.py --auto-safe --explain",
            [sys.executable, str(ralph_cli.resource_path("scripts", "next_task.py")), "--auto-safe", "--explain"],
        ),
    ]


def test_build_verify_commands_uses_expected_read_only_checks() -> None:
    commands = ralph_cli.build_verify_commands()

    assert commands == [
        ("bash -n ralph.sh", ["bash", "-n", "ralph.sh"]),
        ("bash -n src/ralph/resources/ralph.sh", ["bash", "-n", "src/ralph/resources/ralph.sh"]),
        (
            "python -m pytest tests/test_shell_parity.py -q",
            [sys.executable, "-m", "pytest", "tests/test_shell_parity.py", "-q"],
        ),
    ]


def test_duplicate_task_ids_detects_duplicates_and_sorts() -> None:
    duplicates = ralph_cli.duplicate_task_ids(
        [
            {"id": "R12-03"},
            {"id": "R12-03"},
            {"id": "R10-01"},
            {"id": "R10-01"},
            {"id": "R20-22"},
        ]
    )

    assert duplicates == ["R10-01", "R12-03"]


def test_execute_groom_prints_active_backlog_and_policy_hint(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "ACTIVE_BACKLOG.md").write_text("# Active Backlog\n- R20-22\n", encoding="utf-8")
    (docs_dir / "BACKLOG_POLICY.md").write_text("# Policy\n", encoding="utf-8")

    exit_code = ralph_cli.execute_groom(Namespace(command="groom", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "# Active Backlog\n- R20-22\nBacklog policy: docs/BACKLOG_POLICY.md\n"
    assert captured.err == ""


def test_execute_status_prints_operator_summary(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ACTIVE_BACKLOG.md").write_text("# Active Backlog\n", encoding="utf-8")
    (tmp_path / "tasks.json").write_text(
        '{"tasks":[{"id":"T01","status":"pending"},{"id":"T02","status":"verified_done"},{"id":"T01","status":"pending"}]}',
        encoding="utf-8",
    )

    def fake_run_capture(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(command, 0, " M tasks.json\n?? notes.txt\n", "")
        return subprocess.CompletedProcess(command, 0, '{\n  "reason": "unsafe_pending"\n}\n', "")

    monkeypatch.setattr(ralph_cli, "run_command_capture", fake_run_capture)

    exit_code = ralph_cli.execute_status(Namespace(command="status", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Git state: dirty" in captured.out
    assert " M tasks.json" in captured.out
    assert "?? notes.txt" in captured.out
    assert "Task counts:" in captured.out
    assert "- pending: 2" in captured.out
    assert "- verified_done: 1" in captured.out
    assert "Duplicate task IDs: T01" in captured.out
    assert "Active backlog: present" in captured.out
    assert "Next auto-safe state:" in captured.out
    assert '"reason": "unsafe_pending"' in captured.out


def test_execute_status_prints_no_duplicates_for_clean_tasks_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ACTIVE_BACKLOG.md").write_text("# Active Backlog\n", encoding="utf-8")
    (tmp_path / "tasks.json").write_text(
        '{"tasks":[{"id":"T01","status":"pending"},{"id":"T02","status":"verified_done"}]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ralph_cli,
        "run_command_capture",
        lambda command, cwd: subprocess.CompletedProcess(command, 0, "{\n  \"reason\": \"ok\"\n}\n", ""),
    )

    exit_code = ralph_cli.execute_status(Namespace(command="status", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Duplicate task IDs: none" in captured.out


def test_find_log_files_sorts_newest_first(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    older = logs_dir / "ralph_2026-05-18.log"
    newer = logs_dir / "ralph_2026-05-19.log"
    older.write_text("old\n", encoding="utf-8")
    newer.write_text("new\n", encoding="utf-8")
    older.touch()
    newer.touch()

    files = ralph_cli.find_log_files(tmp_path)

    assert files[0] == newer
    assert files[1] == older


def test_execute_tail_prints_last_requested_lines(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "ralph_2026-05-19.log").write_text("one\ntwo\nthree\n", encoding="utf-8")

    exit_code = ralph_cli.execute_tail(Namespace(command="tail", project_dir=str(tmp_path), lines=2))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "two\nthree\n"
    assert captured.err == ""


def test_execute_log_lists_log_files_newest_first(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    older = logs_dir / "ralph_2026-05-18.log"
    newer = logs_dir / "ralph_2026-05-19.log"
    older.write_text("old\n", encoding="utf-8")
    newer.write_text("new\n", encoding="utf-8")
    older.touch()
    newer.touch()

    exit_code = ralph_cli.execute_log(Namespace(command="log", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 0
    lines = captured.out.splitlines()
    assert lines == [str(newer), str(older)]
    assert captured.err == ""


def test_main_preserves_subprocess_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert check is False
        return subprocess.CompletedProcess(command, 17)

    monkeypatch.setattr(ralph_cli.subprocess, "run", fake_run)

    exit_code = ralph_cli.main(["next"])

    assert exit_code == 17
    assert calls == [[sys.executable, str(ralph_cli.resource_path("scripts", "next_task.py"))]]


def test_main_rejects_auto_without_safe_flag() -> None:
    with pytest.raises(SystemExit) as excinfo:
        ralph_cli.main(["auto"])

    assert excinfo.value.code == 2


def test_execute_uses_project_dir_as_subprocess_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    args = Namespace(command="next", project_dir=str(tmp_path))

    def fake_run_command(command: list[str], cwd: Path) -> int:
        recorded["command"] = command
        recorded["cwd"] = cwd
        return 0

    monkeypatch.setattr(ralph_cli, "run_command", fake_run_command)

    exit_code = ralph_cli.execute(args)

    assert exit_code == 0
    assert recorded["command"] == [sys.executable, str(ralph_cli.resource_path("scripts", "next_task.py"))]
    assert recorded["cwd"] == tmp_path.resolve()


def test_execute_doctor_runs_all_checks_and_returns_first_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded: list[tuple[list[str], Path]] = []
    codes = iter([0, 7, 0, 0])
    args = Namespace(command="doctor", project_dir=str(tmp_path))

    def fake_run_command(command: list[str], cwd: Path) -> int:
        recorded.append((command, cwd))
        return next(codes)

    monkeypatch.setattr(ralph_cli, "run_command", fake_run_command)

    exit_code = ralph_cli.execute_doctor(args)

    assert exit_code == 7
    assert recorded == [
        (["git", "status", "--short"], tmp_path.resolve()),
        ([sys.executable, "-m", "json.tool", "tasks.json"], tmp_path.resolve()),
        ([sys.executable, "-m", "pytest", "tests/test_shell_parity.py", "-q"], tmp_path.resolve()),
        (
            [sys.executable, str(ralph_cli.resource_path("scripts", "next_task.py")), "--auto-safe", "--explain"],
            tmp_path.resolve(),
        ),
    ]


def test_execute_doctor_returns_nonzero_when_duplicate_task_ids_exist(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "tasks.json").write_text(
        '{"tasks":[{"id":"R12-03","status":"pending"},{"id":"R12-03","status":"done"}]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(ralph_cli, "run_command", lambda command, cwd: 0)

    exit_code = ralph_cli.execute_doctor(Namespace(command="doctor", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Duplicate task IDs: R12-03" in captured.out


def test_execute_verify_runs_all_checks_and_returns_first_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded: list[tuple[list[str], Path]] = []
    codes = iter([0, 9, 0])

    def fake_run_command(command: list[str], cwd: Path) -> int:
        recorded.append((command, cwd))
        return next(codes)

    monkeypatch.setattr(ralph_cli, "run_command", fake_run_command)

    exit_code = ralph_cli.execute_verify(Namespace(command="verify", project_dir=str(tmp_path)))

    assert exit_code == 9
    assert recorded == [
        (["bash", "-n", "ralph.sh"], tmp_path.resolve()),
        (["bash", "-n", "src/ralph/resources/ralph.sh"], tmp_path.resolve()),
        ([sys.executable, "-m", "pytest", "tests/test_shell_parity.py", "-q"], tmp_path.resolve()),
    ]


def test_execute_groom_returns_nonzero_when_active_backlog_is_missing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = ralph_cli.execute_groom(Namespace(command="groom", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Missing active backlog report:" in captured.err


def test_execute_status_returns_nonzero_for_invalid_tasks_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tasks.json").write_text("{not-json}\n", encoding="utf-8")

    monkeypatch.setattr(
        ralph_cli,
        "run_command_capture",
        lambda command, cwd: subprocess.CompletedProcess(command, 0, "", ""),
    )

    exit_code = ralph_cli.execute_status(Namespace(command="status", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Invalid tasks.json:" in captured.err


def test_execute_tail_returns_nonzero_when_logs_are_missing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = ralph_cli.execute_tail(Namespace(command="tail", project_dir=str(tmp_path), lines=2))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"No Ralph logs found in {tmp_path / 'logs'}" in captured.err


def test_execute_log_returns_nonzero_when_logs_are_missing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = ralph_cli.execute_log(Namespace(command="log", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"No Ralph logs found in {tmp_path / 'logs'}" in captured.err
