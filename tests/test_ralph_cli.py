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


def test_execute_groom_returns_nonzero_when_active_backlog_is_missing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = ralph_cli.execute_groom(Namespace(command="groom", project_dir=str(tmp_path)))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Missing active backlog report:" in captured.err
