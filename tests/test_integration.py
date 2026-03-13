from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RALPH_SH = REPO_ROOT / "ralph.sh"


def wait_until(predicate, timeout: float = 10.0, interval: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def make_fake_binaries(bin_dir: Path) -> None:
    write_executable(
        bin_dir / "codex",
        """#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path

args = sys.argv[1:]
review_file = None
prompt = args[-1] if args else ""
i = 0
while i < len(args):
    if args[i] in {"-s", "-m"}:
        i += 2
    elif args[i] == "-o":
        review_file = args[i + 1]
        i += 2
    else:
        i += 1

sleep_s = float(os.environ.get("MOCK_CODEX_SLEEP", "0"))
mode = os.environ.get("MOCK_CODEX_MODE", "success")
marker_file = os.environ.get("MOCK_RATE_LIMIT_MARKER", "")
child_pid_file = os.environ.get("MOCK_CHILD_PID_FILE", "")
prompt_capture_file = os.environ.get("MOCK_CODEX_CAPTURE_PROMPT_FILE", "")
lead_fix_marker = os.environ.get("MOCK_LEAD_FIX_MARKER", "")
if review_file:
    if mode == "lead_fix_once":
        marker = Path(lead_fix_marker) if lead_fix_marker else None
        if marker is not None and not marker.exists():
            marker.write_text("fix-issued", encoding="utf-8")
            payload = {
                "decision": "fix",
                "quality_score": 4,
                "fix_instructions": "Address the missing acceptance criteria and rerun tests.",
                "progress_note": "Needs one more pass",
            }
        else:
            payload = {
                "decision": "approve",
                "quality_score": 8,
                "progress_note": "Integration test approve",
            }
    else:
        payload = {
            "decision": "approve",
            "quality_score": 8,
            "progress_note": "Integration test approve",
        }
    Path(review_file).write_text(json.dumps(payload), encoding="utf-8")
else:
    if prompt_capture_file:
        Path(prompt_capture_file).write_text(prompt, encoding="utf-8")
    if mode == "asset_manifest_wait":
        manifest = {
            "version": 1,
            "generated_by": "coder",
            "assets": [
                {
                    "id": "hero-image",
                    "kind": "image",
                    "request": "Create a hero image for the landing page",
                    "source_path": ".ralph/assets/inbox/hero-image.txt",
                    "target_path": "src/assets/hero-image.txt",
                }
            ],
        }
        Path("assets_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if mode == "always_fail":
        print("fatal codex failure")
        sys.exit(1)
    if mode == "rate_limit_once":
        marker = Path(marker_file) if marker_file else None
        if marker is not None and not marker.exists():
            marker.write_text("rate-limited", encoding="utf-8")
            print("429 Too Many Requests")
            sys.exit(1)
    if mode == "timeout_child":
        child = subprocess.Popen(["sleep", "30"])
        if child_pid_file:
            Path(child_pid_file).write_text(str(child.pid), encoding="utf-8")
        try:
            time.sleep(30)
        except KeyboardInterrupt:
            pass
    if sleep_s > 0:
        time.sleep(sleep_s)

print("tokens used")
print("123")
""",
    )
    write_executable(
        bin_dir / "gtimeout",
        """#!/usr/bin/env python3
from __future__ import annotations
import os
import signal
import subprocess
import sys

args = sys.argv[1:]
timeout = None
i = 0
while i < len(args):
    arg = args[i]
    if arg == "--foreground" or arg.startswith("--kill-after="):
        i += 1
        continue
    try:
        timeout = float(arg)
        i += 1
        break
    except ValueError:
        break

cmd = args[i:]
if not cmd:
    sys.exit(1)

proc = subprocess.Popen(cmd)
if timeout is None:
    sys.exit(proc.wait())

try:
    sys.exit(proc.wait(timeout=timeout))
except subprocess.TimeoutExpired:
    if os.environ.get("MOCK_GTIMEOUT_KILL_PARENT_ONLY") == "1":
        proc.kill()
        proc.wait()
    else:
        proc.kill()
        proc.wait()
    sys.exit(124)
""",
    )


def init_git_repo(project_dir: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test User",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test User",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True, text=True, env=env)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True, text=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "chore: init test project"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def create_test_project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "logs").mkdir()
    (project_dir / ".ralph" / "memory").mkdir(parents=True)

    tasks = {
        "version": 1,
        "project": "integration-test",
        "phases": {"R1": {"name": "Reliability", "description": "Integration tests"}},
        "tasks": [
            {
                "id": "T01",
                "phase": "R1",
                "title": "Integration test task",
                "description": "Exercise prompt builder for context injection and keyword snippets",
                "status": "pending",
                "priority": "high",
                "dependencies": [],
                "timeout": 5,
            }
        ],
    }
    (project_dir / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    (project_dir / "progress.md").write_text("# Progress\n", encoding="utf-8")
    (project_dir / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (project_dir / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
    (project_dir / "MEMORY_SYSTEM.md").write_text("# Memory\n", encoding="utf-8")
    (project_dir / "AGENTS_CODER.md").write_text("# Coder\n", encoding="utf-8")
    (project_dir / "AGENTS_LEAD.md").write_text("# Lead\n", encoding="utf-8")
    (project_dir / ".ralph" / "memory" / "core.md").write_text("# Core\n", encoding="utf-8")
    (project_dir / ".ralph" / "memory" / "recent.md").write_text("# Recent\n", encoding="utf-8")
    (project_dir / "Makefile").write_text(".PHONY: test\n\ntest:\n\t@true\n", encoding="utf-8")
    (project_dir / "src").mkdir()
    (project_dir / "src" / "prompt_builder.ts").write_text(
        "export function buildKeywordPrompt() {\n"
        "  return 'context injection keyword matching prompt builder "
        + ("alpha " * 120)
        + "';\n"
        "}\n",
        encoding="utf-8",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make_fake_binaries(bin_dir)

    init_git_repo(project_dir)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PYTHONUNBUFFERED"] = "1"
    env["RALPH_PROJECT_DIR"] = str(project_dir)
    env["RALPH_TELEGRAM_TOKEN"] = ""
    env["RALPH_TELEGRAM_CHAT_ID"] = ""
    return project_dir, env


def load_task_status(project_dir: Path, task_id: str = "T01") -> str:
    data = json.loads((project_dir / "tasks.json").read_text(encoding="utf-8"))
    for task in data["tasks"]:
        if task["id"] == task_id:
            return task["status"]
    raise AssertionError(f"Task {task_id} not found")


def load_state(project_dir: Path) -> dict:
    return json.loads((project_dir / "ralph_state.json").read_text(encoding="utf-8"))


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_ralph_marks_task_done_on_success(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    prompt_file = tmp_path / "coder_prompt.txt"
    env["MOCK_CODEX_CAPTURE_PROMPT_FILE"] = str(prompt_file)
    env["RALPH_CONTEXT_MAX_CHARS"] = "320"
    env["RALPH_CODER_PROMPT_MAX_CHARS"] = "2200"

    result = subprocess.run(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert load_task_status(project_dir) == "done"
    prompt = prompt_file.read_text(encoding="utf-8")
    assert "## AGENTS.md Context" in prompt
    assert "# AGENTS" in prompt
    assert "## Relevant Source Snippets" in prompt
    assert "src/prompt_builder.ts" in prompt
    assert "export function buildKeywordPrompt()" in prompt
    assert "keyword matching prompt builder" in prompt
    assert "... [truncated" in prompt
    assert len(prompt) <= 2200 + 32


def test_ralph_blocks_duplicate_launch_with_pid_guard(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    env["MOCK_CODEX_SLEEP"] = "4"

    first = subprocess.Popen(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    assert wait_until(lambda: (project_dir / "ralph_main.pid").exists(), timeout=10)

    second = subprocess.run(
        [str(RALPH_SH), "auto"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    first.terminate()
    try:
        first.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        first.kill()
        first.communicate(timeout=10)

    assert second.returncode != 0
    assert "Ralph already running" in second.stdout


def test_ralph_uses_complexity_default_timeout_when_timeout_missing(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    tasks_path = project_dir / "tasks.json"
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks["tasks"][0].pop("timeout", None)
    tasks["tasks"][0]["complexity"] = "complex"
    tasks_path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    result = subprocess.run(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Timeout: coder=600s lead=300s" in result.stdout


def test_ralph_retries_after_fix_and_then_marks_done(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    env["MOCK_CODEX_MODE"] = "lead_fix_once"
    env["MOCK_LEAD_FIX_MARKER"] = str(tmp_path / "lead_fix.marker")

    result = subprocess.run(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert load_task_status(project_dir) == "done"
    assert "🔧 Fix 1/2:" in result.stdout
    assert result.stdout.count("🤖 CODER — Attempt") >= 2
    assert "👔 Decision: approve" in result.stdout


def test_ralph_marks_task_skipped_on_skip_control(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    env["MOCK_CODEX_SLEEP"] = "1.5"

    process = subprocess.Popen(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    state_file = project_dir / "ralph_state.json"
    assert wait_until(
        lambda: state_file.exists() and load_state(project_dir).get("current_phase_step") == "coder",
        timeout=20,
    )

    (project_dir / "ralph_control.json").write_text(
        json.dumps({"action": "skip", "comment": "T01"}, indent=2),
        encoding="utf-8",
    )

    stdout, _ = process.communicate(timeout=20)
    assert process.returncode == 0, stdout
    assert load_task_status(project_dir) == "skipped"


def test_ralph_stops_when_stop_control_is_present(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    (project_dir / "ralph_control.json").write_text(
        json.dumps({"action": "stop", "comment": ""}, indent=2),
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(RALPH_SH), "auto"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    state = load_state(project_dir)
    assert state["status"] == "stopped"
    assert load_task_status(project_dir) == "pending"


def test_ralph_watchdog_kills_stale_codex_and_retries(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    env["MOCK_CODEX_SLEEP"] = "3"
    env["RALPH_WATCHDOG_TIMEOUT"] = "1"
    env["RALPH_CODEX_RETRY_DELAYS"] = "0 0 0"

    result = subprocess.run(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert result.stdout.count("Watchdog timeout - killing stale codex process") >= 2
    assert "Codex failed after 3 retries" in result.stdout


def test_ralph_pauses_and_retries_on_rate_limit(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    env["MOCK_CODEX_MODE"] = "rate_limit_once"
    env["MOCK_RATE_LIMIT_MARKER"] = str(tmp_path / "rate_limit.marker")
    env["RALPH_RATE_LIMIT_PAUSE"] = "1"
    env["RALPH_CODEX_RETRY_DELAYS"] = "0 0 0"

    process = subprocess.Popen(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    stdout, _ = process.communicate(timeout=30)
    assert process.returncode == 0, stdout
    assert "RATE LIMIT detected" in stdout
    assert load_task_status(project_dir) == "done"


def test_ralph_timeout_cleans_up_orphan_children(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    env["MOCK_CODEX_MODE"] = "timeout_child"
    env["MOCK_CHILD_PID_FILE"] = str(tmp_path / "codex_child.pid")
    env["MOCK_GTIMEOUT_KILL_PARENT_ONLY"] = "1"
    env["RALPH_CODEX_RETRY_DELAYS"] = "0 0 0"

    tasks_path = project_dir / "tasks.json"
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks["tasks"][0]["timeout"] = 1
    tasks_path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    result = subprocess.run(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )

    assert (tmp_path / "codex_child.pid").exists(), result.stdout + result.stderr
    child_pid = int((tmp_path / "codex_child.pid").read_text(encoding="utf-8"))
    assert result.returncode != 0, result.stdout + result.stderr
    assert "TIMEOUT: codex exceeded 1s" in result.stdout
    assert "Codex timed out after 3 retries" in result.stdout
    assert not process_is_alive(child_pid)


def test_ralph_waits_for_assets_and_resumes_when_files_arrive(tmp_path: Path) -> None:
    project_dir, env = create_test_project(tmp_path)
    env["MOCK_CODEX_MODE"] = "asset_manifest_wait"
    env["RALPH_ASSET_POLL_INTERVAL"] = "1"

    process = subprocess.Popen(
        [str(RALPH_SH), "task", "T01"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    assert wait_until(lambda: (project_dir / "assets_manifest.json").exists(), timeout=20)

    inbox_file = project_dir / ".ralph" / "assets" / "inbox" / "hero-image.txt"
    inbox_file.parent.mkdir(parents=True, exist_ok=True)
    inbox_file.write_text("hero-image-binary", encoding="utf-8")

    stdout, _ = process.communicate(timeout=30)
    assert process.returncode == 0, stdout
    assert load_task_status(project_dir) == "done"
    assert "assets_manifest.json" in stdout or "Assets ready for T01" in stdout or "Required assets are ready" in stdout
    assert not inbox_file.exists()
    assert (project_dir / "src" / "assets" / "hero-image.txt").read_text(encoding="utf-8") == "hero-image-binary"
