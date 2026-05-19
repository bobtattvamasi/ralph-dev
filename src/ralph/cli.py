from __future__ import annotations

import argparse
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


def execute_doctor(args: argparse.Namespace) -> int:
    project_dir = Path(getattr(args, "project_dir", ".")).resolve()
    exit_code = 0

    for label, command in build_doctor_commands():
        print(f"==> {label}")
        step_code = run_command(command, cwd=project_dir)
        if exit_code == 0 and step_code != 0:
            exit_code = step_code

    return exit_code


def execute(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        return execute_doctor(args)
    project_dir = Path(getattr(args, "project_dir", ".")).resolve()
    return run_command(build_command(args), cwd=project_dir)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "auto" and not args.safe:
        parser.error("ralph auto requires --safe")

    return execute(args)
