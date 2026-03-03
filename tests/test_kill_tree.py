from __future__ import annotations

import os
import subprocess
import time

import pytest

psutil = pytest.importorskip("psutil")


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.1) -> bool:
    """Wait until predicate() becomes True or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _alive(pid: int) -> bool:
    return psutil.pid_exists(pid) and psutil.Process(pid).is_running()


def test_bash_kill_tree_kills_parent_and_children() -> None:
    # Start a bash parent that spawns two long-running children.
    # Parent waits for children, so the process tree stays alive for inspection.
    parent = subprocess.Popen(
        ["bash", "-lc", "sleep 300 & sleep 300 & wait"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        parent_proc = psutil.Process(parent.pid)

        # Wait until both child sleep processes appear.
        assert _wait_until(
            lambda: len([c for c in parent_proc.children(recursive=False) if c.is_running()]) >= 2
        ), "Expected at least 2 child processes"

        children = parent_proc.children(recursive=False)
        child_pids = [c.pid for c in children]

        # Precondition: parent and children are alive.
        assert _alive(parent.pid), "Parent process should be alive before kill_tree"
        assert all(_alive(pid) for pid in child_pids), "All child processes should be alive before kill_tree"

        # Define kill_tree in bash and execute it for the parent PID.
        # The function recursively kills descendants via pgrep -P, then the parent.
        kill_script = r"""
kill_tree() {
    local pid="$1"
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill -9 "$pid" 2>/dev/null || true
}
kill_tree "$TARGET_PID"
"""
        subprocess.run(
            ["bash", "-lc", kill_script],
            env={**os.environ, "TARGET_PID": str(parent.pid)},
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Verify the whole tree is gone.
        assert _wait_until(lambda: not _alive(parent.pid)), "Parent process should be terminated"
        assert all(not _alive(pid) for pid in child_pids), "Child processes should be terminated"
    finally:
        # Final defensive cleanup in case the test fails mid-way.
        if _alive(parent.pid):
            try:
                for child in psutil.Process(parent.pid).children(recursive=True):
                    child.kill()
                psutil.Process(parent.pid).kill()
            except psutil.Error:
                pass
