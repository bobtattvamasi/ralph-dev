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
    assert "next" in help_result.stdout
    assert "explain" in help_result.stdout
    assert "task" in help_result.stdout
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

    next_result = run([str(ralph_bin), "next", "--project-dir", str(project_dir)], env=runtime_env)
    assert next_result.returncode == 0
    assert '"id": "T01"' in next_result.stdout

    explain_result = run([str(ralph_bin), "explain", "--project-dir", str(project_dir)], env=runtime_env)
    assert explain_result.returncode == 0
    assert explain_result.stdout.strip()

    task_help_result = run([str(ralph_bin), "task", "--help"], cwd=tmp_path)
    assert task_help_result.returncode == 0
    assert "task id to run" in task_help_result.stdout.lower()

    auto_result = run([str(ralph_bin), "auto", "--safe", "--project-dir", str(project_dir)], env=runtime_env)
    assert auto_result.returncode == 0
    assert "AUTO_TASK_RESULT T01 status=skipped reason=INTEGRATION_EVIDENCE_REQUIRED" in auto_result.stdout

    bot_help_result = run([str(ralph_bin), "bot", "--help"], cwd=tmp_path)
    assert bot_help_result.returncode == 0
    assert "project-dir" in bot_help_result.stdout


def test_packaged_trust_resources_exist_and_verify_script_executes(tmp_path: Path) -> None:
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    python_bin = bin_dir / ("python.exe" if os.name == "nt" else "python")

    subprocess.run([str(python_bin), "-m", "pip", "install", str(REPO_ROOT)], check=True)

    resource_probe = run(
        [
            str(python_bin),
            "-c",
            (
                "from ralph.cli import resource_path\n"
                "for parts in [('scripts','verify_task_closure.py'), ('scripts','models.py'), ('scripts','re_audit_tasks.py'), ('scripts','audit_artifact.py')]:\n"
                "    p = resource_path(*parts)\n"
                "    print('/'.join(parts), p.exists())\n"
            ),
        ],
        cwd=tmp_path,
    )
    assert resource_probe.returncode == 0, resource_probe.stdout + resource_probe.stderr
    assert "scripts/verify_task_closure.py True" in resource_probe.stdout
    assert "scripts/models.py True" in resource_probe.stdout
    assert "scripts/re_audit_tasks.py True" in resource_probe.stdout
    assert "scripts/audit_artifact.py True" in resource_probe.stdout

    project_dir = tmp_path / "project"
    (project_dir / "docs").mkdir(parents=True)
    (project_dir / "docs" / "TRUST_LAYER.md").write_text("# Trust Layer\n", encoding="utf-8")

    verify_result = run(
        [
            str(python_bin),
            "-c",
            (
                "import json, os, subprocess\n"
                "from pathlib import Path\n"
                "from ralph.cli import resource_path\n"
                "project_dir = Path(os.environ['RALPH_PROJECT_DIR'])\n"
                "task = {\n"
                "  'id': 'R10-PKG',\n"
                "  'title': 'Docs: trust layer note',\n"
                "  'description': 'Update the trust layer documentation with a short note.',\n"
                "  'acceptance_criteria': ['Trust layer documentation exists']\n"
                "}\n"
                "env = os.environ.copy()\n"
                "env['RALPH_CHANGED_FILES_JSON'] = json.dumps(['docs/TRUST_LAYER.md'])\n"
                "proc = subprocess.run([\n"
                "  os.environ['PYTHON_BIN'], str(resource_path('scripts', 'verify_task_closure.py'))\n"
                "], input=json.dumps(task), text=True, capture_output=True, env=env, cwd=str(project_dir))\n"
                "print(proc.stdout)\n"
                "raise SystemExit(proc.returncode)\n"
            ),
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "RALPH_PROJECT_DIR": str(project_dir),
            "PYTHON_BIN": str(python_bin),
        },
    )
    assert verify_result.returncode == 0, verify_result.stdout + verify_result.stderr
    assert '"result": "pass"' in verify_result.stdout
    assert '"task_class": "docs-only"' in verify_result.stdout


def test_packaged_trust_and_runtime_resources_match_root_sources() -> None:
    resource_pairs = [
        ("scripts/extract_json.py", "src/ralph/resources/scripts/extract_json.py"),
        ("scripts/verify_task_closure.py", "src/ralph/resources/scripts/verify_task_closure.py"),
        ("scripts/models.py", "src/ralph/resources/scripts/models.py"),
        ("scripts/ralph_common.py", "src/ralph/resources/scripts/ralph_common.py"),
        ("scripts/ralph_bot.py", "src/ralph/resources/scripts/ralph_bot.py"),
        ("scripts/update_progress.py", "src/ralph/resources/scripts/update_progress.py"),
        ("scripts/update_task.py", "src/ralph/resources/scripts/update_task.py"),
        ("templates/AGENTS_CODER.md", "src/ralph/resources/templates/AGENTS_CODER.md"),
    ]

    for root_rel, packaged_rel in resource_pairs:
        root_path = REPO_ROOT / root_rel
        packaged_path = REPO_ROOT / packaged_rel
        assert packaged_path.read_text(encoding="utf-8") == root_path.read_text(encoding="utf-8"), (
            f"Packaged resource drifted from root source: {root_rel} != {packaged_rel}"
        )
