from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path


RESOURCE_ROOT = Path(__file__).resolve().parent / "resources"


def resource_path(*parts: str) -> Path:
    path = RESOURCE_ROOT.joinpath(*parts)
    if not path.exists():
        joined = "/".join(parts)
        raise FileNotFoundError(f"Missing packaged Ralph resource: {joined}")
    return path


def run_command(command: list[str], cwd: Path) -> int:
    completed = subprocess.run(command, cwd=cwd, check=False)
    return completed.returncode


def run_command_capture(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ralph",
        description="Project-agnostic AI execution layer CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize Ralph files in a target project directory.",
    )
    init_parser.add_argument(
        "project_name",
        nargs="?",
        help="Optional project name used when rendering templates.",
    )
    init_parser.add_argument(
        "--project-dir",
        default=".",
        help="Directory to initialize. Defaults to the current directory.",
    )

    auto_parser = subparsers.add_parser(
        "auto",
        help="Run Ralph in auto mode for the target project.",
    )
    auto_parser.add_argument(
        "--safe",
        action="store_true",
        help="Required for the unattended safe lane.",
    )
    auto_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    next_parser = subparsers.add_parser(
        "next",
        help="Show the next task candidate using the existing selector.",
    )
    next_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    explain_parser = subparsers.add_parser(
        "explain",
        help="Explain the current auto-safe queue state.",
    )
    explain_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run lightweight operator health checks.",
    )
    doctor_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    groom_parser = subparsers.add_parser(
        "groom",
        help="Show the current active backlog view.",
    )
    groom_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    tail_parser = subparsers.add_parser(
        "tail",
        help="Show the tail of the latest Ralph log file.",
    )
    tail_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )
    tail_parser.add_argument(
        "--lines",
        type=int,
        default=80,
        help="Number of lines to print from the end of the latest log. Defaults to 80.",
    )

    log_parser = subparsers.add_parser(
        "log",
        help="List available Ralph log files newest first.",
    )
    log_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    task_parser = subparsers.add_parser(
        "task",
        help="Run one explicitly selected task.",
    )
    task_parser.add_argument("task_id", help="Task id to run.")
    task_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Show Ralph status for the target project.",
    )
    status_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    bot_parser = subparsers.add_parser(
        "bot",
        help="Start the Ralph Telegram bot for the target project.",
    )
    bot_parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory that contains tasks.json.",
    )

    return parser


def build_command(args: argparse.Namespace) -> list[str]:
    ralph_shell = resource_path("ralph.sh")
    next_task_script = resource_path("scripts", "next_task.py")

    if args.command == "init":
        command = ["bash", str(resource_path("ralph-init.sh"))]
        if args.project_name:
            command.append(args.project_name)
        return command

    if args.command == "auto":
        return ["bash", str(ralph_shell), "auto"]

    if args.command == "next":
        return [sys.executable, str(next_task_script)]

    if args.command == "explain":
        return [sys.executable, str(next_task_script), "--auto-safe", "--explain"]

    if args.command == "task":
        return ["bash", str(ralph_shell), "task", args.task_id]

    if args.command == "status":
        return ["bash", str(ralph_shell), "status"]

    if args.command == "bot":
        return [
            sys.executable,
            str(resource_path("scripts", "ralph_bot.py")),
            "--project-dir",
            str(Path(getattr(args, "project_dir", ".")).resolve()),
        ]

    raise ValueError(f"Unknown command: {args.command}")


def build_doctor_commands() -> list[tuple[str, list[str]]]:
    next_task_script = resource_path("scripts", "next_task.py")
    return [
        ("git status --short", ["git", "status", "--short"]),
        ("python -m json.tool tasks.json", [sys.executable, "-m", "json.tool", "tasks.json"]),
        ("python -m pytest tests/test_shell_parity.py -q", [sys.executable, "-m", "pytest", "tests/test_shell_parity.py", "-q"]),
        ("python scripts/next_task.py --auto-safe --explain", [sys.executable, str(next_task_script), "--auto-safe", "--explain"]),
    ]


def duplicate_task_ids(tasks: list[dict[str, object]]) -> list[str]:
    counts = collections.Counter(
        str(task.get("id", "")).strip()
        for task in tasks
        if isinstance(task, dict) and str(task.get("id", "")).strip()
    )
    return sorted(task_id for task_id, count in counts.items() if count > 1)


def load_tasks_payload(project_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    tasks_path = project_dir / "tasks.json"
    try:
        tasks_payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Missing tasks.json: {tasks_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid tasks.json: {exc}") from exc

    tasks = tasks_payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("Invalid tasks.json: top-level 'tasks' must be a list")

    normalized_tasks = [task for task in tasks if isinstance(task, dict)]
    return tasks_payload, normalized_tasks


def execute_doctor(args: argparse.Namespace) -> int:
    project_dir = Path(getattr(args, "project_dir", ".")).resolve()
    exit_code = 0

    for label, command in build_doctor_commands():
        print(f"==> {label}")
        step_code = run_command(command, cwd=project_dir)
        if exit_code == 0 and step_code != 0:
            exit_code = step_code

    try:
        _, tasks = load_tasks_payload(project_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1 if exit_code == 0 else exit_code

    duplicates = duplicate_task_ids(tasks)
    if duplicates:
        print(f"Duplicate task IDs: {', '.join(duplicates)}")
        if exit_code == 0:
            exit_code = 1

    return exit_code


def execute_groom(args: argparse.Namespace) -> int:
    project_dir = Path(getattr(args, "project_dir", ".")).resolve()
    active_backlog_path = project_dir / "docs" / "ACTIVE_BACKLOG.md"
    backlog_policy_path = project_dir / "docs" / "BACKLOG_POLICY.md"
    active_backlog_text = ""

    if not active_backlog_path.exists():
        print(f"Missing active backlog report: {active_backlog_path}", file=sys.stderr)
        return 1

    active_backlog_text = active_backlog_path.read_text(encoding="utf-8")
    print(active_backlog_text, end="")
    if backlog_policy_path.exists():
        if not active_backlog_text.endswith("\n"):
            print()
        print(f"Backlog policy: docs/BACKLOG_POLICY.md")
    return 0


def find_log_files(project_dir: Path) -> list[Path]:
    log_dir = project_dir / "logs"
    files = [path for path in log_dir.glob("ralph_*.log") if path.is_file()]
    return sorted(files, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)


def latest_log_file(project_dir: Path) -> Path | None:
    log_files = find_log_files(project_dir)
    return log_files[0] if log_files else None


def tail_lines(path: Path, line_count: int) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[-line_count:]


def execute_status(args: argparse.Namespace) -> int:
    project_dir = Path(getattr(args, "project_dir", ".")).resolve()
    active_backlog_path = project_dir / "docs" / "ACTIVE_BACKLOG.md"

    git_result = run_command_capture(["git", "status", "--short"], cwd=project_dir)
    if git_result.returncode != 0:
        if git_result.stderr:
            print(git_result.stderr, end="", file=sys.stderr)
        return git_result.returncode

    try:
        _, tasks = load_tasks_payload(project_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    counts: dict[str, int] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status", "unknown")).strip() or "unknown"
        counts[status] = counts.get(status, 0) + 1

    explain_result = run_command_capture(
        [sys.executable, str(resource_path("scripts", "next_task.py")), "--auto-safe", "--explain"],
        cwd=project_dir,
    )
    if explain_result.returncode != 0:
        if explain_result.stdout:
            print(explain_result.stdout, end="")
        if explain_result.stderr:
            print(explain_result.stderr, end="", file=sys.stderr)
        return explain_result.returncode

    git_lines = [line for line in git_result.stdout.splitlines() if line.strip()]
    print(f"Git state: {'clean' if not git_lines else 'dirty'}")
    for line in git_lines:
        print(line)

    print("Task counts:")
    for status in sorted(counts):
        print(f"- {status}: {counts[status]}")

    duplicates = duplicate_task_ids(tasks)
    print(f"Duplicate task IDs: {', '.join(duplicates) if duplicates else 'none'}")
    print(f"Active backlog: {'present' if active_backlog_path.exists() else 'missing'}")
    print("Next auto-safe state:")
    print(explain_result.stdout, end="")
    return 0


def execute_tail(args: argparse.Namespace) -> int:
    project_dir = Path(getattr(args, "project_dir", ".")).resolve()
    line_count = int(getattr(args, "lines", 80))
    if line_count <= 0:
        print("--lines must be greater than 0", file=sys.stderr)
        return 1

    log_path = latest_log_file(project_dir)
    if log_path is None:
        print(f"No Ralph logs found in {project_dir / 'logs'}", file=sys.stderr)
        return 1

    for line in tail_lines(log_path, line_count):
        print(line)
    return 0


def execute_log(args: argparse.Namespace) -> int:
    project_dir = Path(getattr(args, "project_dir", ".")).resolve()
    log_files = find_log_files(project_dir)
    if not log_files:
        print(f"No Ralph logs found in {project_dir / 'logs'}", file=sys.stderr)
        return 1

    for path in log_files:
        print(path)
    return 0


def execute(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        return execute_doctor(args)
    if args.command == "groom":
        return execute_groom(args)
    if args.command == "status":
        return execute_status(args)
    if args.command == "tail":
        return execute_tail(args)
    if args.command == "log":
        return execute_log(args)
    project_dir = Path(getattr(args, "project_dir", ".")).resolve()
    return run_command(build_command(args), cwd=project_dir)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auto" and not args.safe:
        parser.error("ralph auto requires --safe")

    return execute(args)
