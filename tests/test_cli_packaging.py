from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.test_integration import create_test_project


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_entrypoint_install_and_core_commands(tmp_path: Path) -> None:
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    python_bin = bin_dir / ("python.exe" if os.name == "nt" else "python")
    ralph_bin = bin_dir / ("ralph.exe" if os.name == "nt" else "ralph")

    subprocess.run([str(python_bin), "-m", "pip", "install", str(REPO_ROOT)], check=True)

    help_result = run([str(ralph_bin), "--help"])
    assert help_result.returncode == 0
    assert "init" in help_result.stdout
    assert "auto" in help_result.stdout
    assert "status" in help_result.stdout
    assert "bot" in help_result.stdout

    init_dir = tmp_path / "initialized-project"
    init_dir.mkdir()
    init_result = run([str(ralph_bin), "init", "demo-project"], cwd=init_dir)
    assert init_result.returncode == 0
    assert (init_dir / "tasks.json").exists()
    assert (init_dir / "AGENTS.md").exists()
    assert (init_dir / ".ralph" / "memory" / "core.md").exists()

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    project_dir, env = create_test_project(runtime_root)
    runtime_env = env.copy()
    runtime_env["PATH"] = f"{bin_dir}:{runtime_env['PATH']}"

    status_result = run([str(ralph_bin), "status", "--project-dir", str(project_dir)], env=runtime_env)
    assert status_result.returncode == 0
    assert "Task Progress" in status_result.stdout

    auto_result = run([str(ralph_bin), "auto", "--project-dir", str(project_dir)], env=runtime_env)
    assert auto_result.returncode == 0
    assert "No more pending tasks" in auto_result.stdout

    bot_help_result = run([str(ralph_bin), "bot", "--help"])
    assert bot_help_result.returncode == 0
    assert "project-dir" in bot_help_result.stdout
