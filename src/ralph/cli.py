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
    completed = subprocess.run(command, cwd=cwd)
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project_dir = Path(getattr(args, "project_dir", ".")).resolve()

    if args.command == "init":
        command = ["bash", str(resource_path("ralph-init.sh"))]
        if args.project_name:
            command.append(args.project_name)
        return run_command(command, cwd=project_dir)

    if args.command == "auto":
        return run_command(["bash", str(resource_path("ralph.sh")), "auto"], cwd=project_dir)

    if args.command == "status":
        return run_command(["bash", str(resource_path("ralph.sh")), "status"], cwd=project_dir)

    if args.command == "bot":
        command = [
            sys.executable,
            str(resource_path("scripts", "ralph_bot.py")),
            "--project-dir",
            str(project_dir),
        ]
        return run_command(command, cwd=project_dir)

    parser.error(f"Unknown command: {args.command}")
    return 2
