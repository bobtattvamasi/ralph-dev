#!/usr/bin/env python3
"""Manage the Ralph project registry stored in ~/.ralph/projects.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from ralph_common import atomic_write_json, locked_path
except ImportError:
    from scripts.ralph_common import atomic_write_json, locked_path


RALPH_DIR = Path(__file__).resolve().parent.parent
REGISTRY_DIR = Path.home() / ".ralph"
REGISTRY_FILE = REGISTRY_DIR / "projects.json"
DEFAULT_PROJECT_NAME = "ralph-dev"
DEFAULT_TEST_CMD = "make test"


def default_project_entry() -> dict[str, str]:
    return {
        "path": str(RALPH_DIR),
        "test_cmd": DEFAULT_TEST_CMD,
    }


def default_registry() -> dict[str, Any]:
    return {
        "version": 1,
        "active_project": DEFAULT_PROJECT_NAME,
        "projects": {
            DEFAULT_PROJECT_NAME: default_project_entry(),
        },
    }


def load_registry() -> dict[str, Any]:
    if not REGISTRY_FILE.exists():
        data = default_registry()
        save_registry(data)
        return data

    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed registry JSON: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError("Registry must contain a JSON object.")

    projects = data.get("projects")
    if not isinstance(projects, dict):
        raise ValueError("Registry must contain a top-level 'projects' object.")

    data.setdefault("version", 1)
    data.setdefault("active_project", DEFAULT_PROJECT_NAME)
    if DEFAULT_PROJECT_NAME not in projects:
        projects[DEFAULT_PROJECT_NAME] = default_project_entry()
    if data.get("active_project") not in projects:
        data["active_project"] = DEFAULT_PROJECT_NAME

    save_registry(data)
    return data


def save_registry(data: dict[str, Any]) -> None:
    with locked_path(REGISTRY_FILE):
        atomic_write_json(REGISTRY_FILE, data)


def add_project(name: str, path: str, test_cmd: str, *, activate: bool = False) -> dict[str, Any]:
    data = load_registry()
    projects = data["projects"]
    projects[name] = {
        "path": str(Path(path).expanduser().resolve()),
        "test_cmd": test_cmd,
    }
    if activate:
        data["active_project"] = name
    save_registry(data)
    return projects[name]


def remove_project(name: str) -> bool:
    if name == DEFAULT_PROJECT_NAME:
        raise ValueError("Cannot remove the built-in ralph-dev project.")

    data = load_registry()
    projects = data["projects"]
    removed = projects.pop(name, None)
    if removed is None:
        return False
    if data.get("active_project") == name:
        data["active_project"] = DEFAULT_PROJECT_NAME
    save_registry(data)
    return True


def list_projects() -> dict[str, Any]:
    return load_registry()


def switch_project(name: str) -> dict[str, Any]:
    data = load_registry()
    projects = data["projects"]
    if name not in projects:
        raise ValueError(f"Unknown project: {name}")
    data["active_project"] = name
    save_registry(data)
    return projects[name]


def active_project() -> dict[str, Any]:
    data = load_registry()
    name = data["active_project"]
    return {"name": name, **data["projects"][name]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add or update a project.")
    add_parser.add_argument("name")
    add_parser.add_argument("path")
    add_parser.add_argument("--test-cmd", default=DEFAULT_TEST_CMD)
    add_parser.add_argument("--activate", action="store_true")

    remove_parser = subparsers.add_parser("remove", help="Remove a project.")
    remove_parser.add_argument("name")

    list_parser = subparsers.add_parser("list", help="List registered projects.")
    list_parser.add_argument("--active-only", action="store_true")

    switch_parser = subparsers.add_parser("switch", help="Switch active project.")
    switch_parser.add_argument("name")

    subparsers.add_parser("active", help="Show the active project.")
    return parser


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "add":
            project = add_project(args.name, args.path, args.test_cmd, activate=args.activate)
            return emit({"ok": True, "project": {"name": args.name, **project}})

        if args.command == "remove":
            removed = remove_project(args.name)
            return emit({"ok": removed, "removed": args.name if removed else None})

        if args.command == "list":
            data = list_projects()
            if args.active_only:
                name = data["active_project"]
                return emit({"active_project": name, "projects": {name: data["projects"][name]}})
            return emit(data)

        if args.command == "switch":
            project = switch_project(args.name)
            return emit({"ok": True, "active_project": args.name, "project": {"name": args.name, **project}})

        if args.command == "active":
            return emit(active_project())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
