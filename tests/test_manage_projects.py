from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "manage_projects.py"


def run_manage_projects(*args: str, home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def load_registry(home: Path) -> dict[str, object]:
    return json.loads((home / ".ralph" / "projects.json").read_text(encoding="utf-8"))


def test_list_creates_registry_with_active_ralph_dev_entry(tmp_path: Path) -> None:
    result = run_manage_projects("list", home=tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["active_project"] == "ralph-dev"
    assert payload["projects"]["ralph-dev"]["path"] == str(REPO_ROOT)
    assert payload["projects"]["ralph-dev"]["test_cmd"] == "make test"

    persisted = load_registry(tmp_path)
    assert persisted == payload


def test_add_and_switch_project_updates_registry(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo-project"
    project_dir.mkdir()

    add_result = run_manage_projects(
        "add",
        "demo",
        str(project_dir),
        "--test-cmd",
        "pnpm test",
        "--activate",
        home=tmp_path,
    )

    assert add_result.returncode == 0, add_result.stdout + add_result.stderr
    add_payload = json.loads(add_result.stdout)
    assert add_payload["project"]["name"] == "demo"
    assert add_payload["project"]["path"] == str(project_dir.resolve())
    assert add_payload["project"]["test_cmd"] == "pnpm test"

    active_result = run_manage_projects("active", home=tmp_path)
    assert active_result.returncode == 0, active_result.stdout + active_result.stderr
    active_payload = json.loads(active_result.stdout)
    assert active_payload["name"] == "demo"
    assert active_payload["test_cmd"] == "pnpm test"

    switch_result = run_manage_projects("switch", "ralph-dev", home=tmp_path)
    assert switch_result.returncode == 0, switch_result.stdout + switch_result.stderr
    switch_payload = json.loads(switch_result.stdout)
    assert switch_payload["active_project"] == "ralph-dev"

    persisted = load_registry(tmp_path)
    assert persisted["active_project"] == "ralph-dev"
    assert persisted["projects"]["demo"]["path"] == str(project_dir.resolve())


def test_remove_deletes_project_and_falls_back_from_active_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "scratch"
    project_dir.mkdir()

    add_result = run_manage_projects("add", "scratch", str(project_dir), "--activate", home=tmp_path)
    assert add_result.returncode == 0, add_result.stdout + add_result.stderr

    remove_result = run_manage_projects("remove", "scratch", home=tmp_path)
    assert remove_result.returncode == 0, remove_result.stdout + remove_result.stderr
    remove_payload = json.loads(remove_result.stdout)
    assert remove_payload["ok"] is True
    assert remove_payload["removed"] == "scratch"

    persisted = load_registry(tmp_path)
    assert persisted["active_project"] == "ralph-dev"
    assert "scratch" not in persisted["projects"]


def test_remove_rejects_builtin_ralph_dev_entry(tmp_path: Path) -> None:
    result = run_manage_projects("remove", "ralph-dev", home=tmp_path)

    assert result.returncode == 1
    assert "Cannot remove the built-in ralph-dev project." in result.stderr
