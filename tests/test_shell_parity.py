from __future__ import annotations

import difflib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SHELL = REPO_ROOT / "ralph.sh"
PACKAGED_SHELL = REPO_ROOT / "src" / "ralph" / "resources" / "ralph.sh"


def test_repo_shell_matches_packaged_shell() -> None:
    runtime_bytes = RUNTIME_SHELL.read_bytes()
    packaged_bytes = PACKAGED_SHELL.read_bytes()

    if runtime_bytes != packaged_bytes:
        runtime_lines = RUNTIME_SHELL.read_text(encoding="utf-8").splitlines()
        packaged_lines = PACKAGED_SHELL.read_text(encoding="utf-8").splitlines()
        diff_lines = list(
            difflib.unified_diff(
                runtime_lines,
                packaged_lines,
                fromfile=str(RUNTIME_SHELL),
                tofile=str(PACKAGED_SHELL),
                lineterm="",
            )
        )
        preview = "\n".join(diff_lines[:20])
        raise AssertionError(
            "repo shell and packaged shell differ.\n"
            "First 20 diff lines:\n"
            f"{preview}"
        )
