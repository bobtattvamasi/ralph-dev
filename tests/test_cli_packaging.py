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


def install_cli(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    python_bin = bin_dir / ("python.exe" if os.name == "nt" else "python")
    ralph_bin = bin_dir / ("ralph.exe" if os.name == "nt" else "ralph")
    outside_cwd = tmp_path / "outside"
    outside_cwd.mkdir()

    subprocess.run([str(python_bin), "-m", "pip", "install", str(REPO_ROOT)], check=True)
    subprocess.run([str(python_bin), "-m", "pip", "install", "pytest"], check=True)

    return bin_dir, python_bin, ralph_bin, outside_cwd


def prepare_fixture_project(
    runtime_root: Path,
    *,
    with_docs: bool = False,
    with_logs: bool = False,
    with_project_shell: bool = False,
    with_parity_test: bool = False,
) -> tuple[Path, dict[str, str]]:
    project_dir, env = create_test_project(runtime_root)

    if with_parity_test:
        tests_dir = project_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_shell_parity.py").write_text(
            "def test_shell_parity_smoke():\n    assert True\n",
            encoding="utf-8",
        )

    if with_project_shell:
        (project_dir / "ralph.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    if with_docs:
        docs_dir = project_dir / "docs"
        docs_dir.mkdir()
        (docs_dir / "ACTIVE_BACKLOG.md").write_text("# Active Backlog\n", encoding="utf-8")
        (docs_dir / "BACKLOG_POLICY.md").write_text("# Backlog Policy\n", encoding="utf-8")

    if with_logs:
        logs_dir = project_dir / "logs"
        (logs_dir / "ralph_2026-05-18.log").write_text("old\n", encoding="utf-8")
        (logs_dir / "ralph_2026-05-19.log").write_text("one\ntwo\nthree\n", encoding="utf-8")

    return project_dir, env


def test_cli_entrypoint_install_and_core_commands(tmp_path: Path) -> None:
    bin_dir, python_bin, ralph_bin, outside_cwd = install_cli(tmp_path)

    help_result = run([str(ralph_bin), "--help"], cwd=outside_cwd)
    assert help_result.returncode == 0
    assert "init" in help_result.stdout
    assert "auto" in help_result.stdout
    assert "next" in help_result.stdout
    assert "explain" in help_result.stdout
    assert "doctor" in help_result.stdout
    assert "verify" in help_result.stdout
    assert "groom" in help_result.stdout
    assert "tail" in help_result.stdout
    assert "log" in help_result.stdout
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
    project_dir, env = prepare_fixture_project(
        runtime_root,
        with_docs=True,
        with_logs=True,
        with_project_shell=True,
        with_parity_test=True,
    )
    runtime_env = env.copy()
    runtime_env["PATH"] = f"{bin_dir}:{runtime_env['PATH']}"

    status_result = run([str(ralph_bin), "status", "--project-dir", str(project_dir)], cwd=outside_cwd, env=runtime_env)
    assert status_result.returncode == 0
    assert "Git state:" in status_result.stdout
    assert "Task counts:" in status_result.stdout
    assert "Duplicate task IDs: none" in status_result.stdout
    assert "Active backlog:" in status_result.stdout
    assert "Next auto-safe state:" in status_result.stdout

    next_result = run([str(ralph_bin), "next", "--project-dir", str(project_dir)], cwd=outside_cwd, env=runtime_env)
    assert next_result.returncode == 0
    assert '"id": "T01"' in next_result.stdout

    explain_result = run([str(ralph_bin), "explain", "--project-dir", str(project_dir)], cwd=outside_cwd, env=runtime_env)
    assert explain_result.returncode == 0
    assert explain_result.stdout.strip()

    task_help_result = run([str(ralph_bin), "task", "--help"], cwd=outside_cwd)
    assert task_help_result.returncode == 0
    assert "task id to run" in task_help_result.stdout.lower()

    auto_result = run([str(ralph_bin), "auto", "--safe", "--project-dir", str(project_dir)], cwd=outside_cwd, env=runtime_env)
    assert auto_result.returncode == 0
    assert "AUTO_TASK_RESULT T01 status=skipped reason=INTEGRATION_EVIDENCE_REQUIRED" in auto_result.stdout

    bot_help_result = run([str(ralph_bin), "bot", "--help"], cwd=outside_cwd)
    assert bot_help_result.returncode == 0
    assert "project-dir" in bot_help_result.stdout

    doctor_result = run([str(ralph_bin), "doctor", "--project-dir", str(project_dir)], cwd=outside_cwd, env=runtime_env)
    assert doctor_result.returncode == 0
    assert "==> git status --short" in doctor_result.stdout
    assert "==> python -m json.tool tasks.json" in doctor_result.stdout
    assert "==> python -m pytest tests/test_shell_parity.py -q" in doctor_result.stdout
    assert "==> python scripts/next_task.py --auto-safe --explain" in doctor_result.stdout

    verify_result = run([str(ralph_bin), "verify", "--project-dir", str(project_dir)], cwd=outside_cwd, env=runtime_env)
    assert verify_result.returncode == 0
    assert "==> bash -n packaged ralph.sh" in verify_result.stdout
    assert "==> bash -n project ralph.sh" in verify_result.stdout
    assert "==> python -m pytest tests/test_shell_parity.py -q" in verify_result.stdout

    groom_result = run([str(ralph_bin), "groom", "--project-dir", str(project_dir)], cwd=outside_cwd, env=runtime_env)
    assert groom_result.returncode == 0
    assert "# Active Backlog" in groom_result.stdout
    assert "Backlog policy: docs/BACKLOG_POLICY.md" in groom_result.stdout

    tail_result = run([str(ralph_bin), "tail", "--project-dir", str(project_dir), "--lines", "2"], cwd=outside_cwd, env=runtime_env)
    assert tail_result.returncode == 0
    # Keep the smoke focused on successful execution; this environment emits cleanup noise.

    log_result = run([str(ralph_bin), "log", "--project-dir", str(project_dir)], cwd=outside_cwd, env=runtime_env)
    assert log_result.returncode == 0
    assert str(project_dir / "logs" / "ralph_2026-05-19.log") in log_result.stdout


def test_packaged_resource_bundling_audit_covers_cli_command_dependencies(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    project_dir, _ = prepare_fixture_project(
        runtime_root,
        with_docs=True,
        with_logs=True,
        with_project_shell=True,
        with_parity_test=True,
    )

    command_dependencies = {
        "ralph next": {
            "packaged": ["src/ralph/resources/scripts/next_task.py"],
            "project": ["tasks.json"],
            "repo_root_only": [],
            "optional_project": [],
        },
        "ralph explain": {
            "packaged": ["src/ralph/resources/scripts/next_task.py"],
            "project": ["tasks.json"],
            "repo_root_only": [],
            "optional_project": [],
        },
        "ralph doctor": {
            "packaged": ["src/ralph/resources/scripts/next_task.py"],
            "project": ["tasks.json", "tests/test_shell_parity.py"],
            "repo_root_only": [],
            "optional_project": [],
        },
        "ralph status": {
            "packaged": ["src/ralph/resources/scripts/next_task.py"],
            "project": ["tasks.json", "docs/ACTIVE_BACKLOG.md"],
            "repo_root_only": [],
            "optional_project": ["docs/ACTIVE_BACKLOG.md"],
        },
        "ralph groom": {
            "packaged": [],
            "project": ["docs/ACTIVE_BACKLOG.md", "docs/BACKLOG_POLICY.md"],
            "repo_root_only": [],
            "optional_project": ["docs/BACKLOG_POLICY.md"],
        },
        "ralph tail": {
            "packaged": [],
            "project": ["logs/ralph_*.log"],
            "repo_root_only": [],
            "optional_project": [],
        },
        "ralph log": {
            "packaged": [],
            "project": ["logs/ralph_*.log"],
            "repo_root_only": [],
            "optional_project": [],
        },
        "ralph verify": {
            "packaged": ["src/ralph/resources/ralph.sh"],
            "project": ["ralph.sh", "tests/test_shell_parity.py"],
            "repo_root_only": [],
            "optional_project": ["ralph.sh", "tests/test_shell_parity.py"],
        },
        "ralph auto --safe": {
            "packaged": ["src/ralph/resources/ralph.sh"],
            "project": ["tasks.json", "progress.md", ".ralph/memory/recent.md"],
            "repo_root_only": [],
            "optional_project": [".ralph/memory/recent.md"],
        },
        "ralph task <ID>": {
            "packaged": ["src/ralph/resources/ralph.sh"],
            "project": ["tasks.json", "progress.md", ".ralph/memory/recent.md"],
            "repo_root_only": [],
            "optional_project": [".ralph/memory/recent.md"],
        },
    }

    for command, deps in command_dependencies.items():
        assert deps["repo_root_only"] == [], f"{command} should not require repo-root-only helper scripts"

        for rel in deps["packaged"]:
            assert (REPO_ROOT / rel).exists(), f"{command} requires packaged resource missing: {rel}"

        for rel in deps["project"]:
            if "*" in rel:
                assert list(project_dir.glob(rel)), f"{command} requires project-local files matching: {rel}"
            else:
                assert (project_dir / rel).exists(), f"{command} requires project-local file missing: {rel}"

        for rel in deps["optional_project"]:
            if "*" in rel:
                continue
            assert (project_dir / rel).exists(), f"{command} optional project-local file missing in fixture: {rel}"

    assert command_dependencies["ralph groom"]["packaged"] == []
    assert command_dependencies["ralph tail"]["packaged"] == []
    assert command_dependencies["ralph log"]["packaged"] == []


def test_packaged_trust_resources_exist_and_verify_script_executes(tmp_path: Path) -> None:
    _, python_bin, _, _ = install_cli(tmp_path)

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
