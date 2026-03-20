from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_eval import evaluate_fixture, load_fixture


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_EVAL = REPO_ROOT / "scripts" / "run_eval.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "basic_eval_fixture.json"


def test_load_fixture_reads_basic_eval_source() -> None:
    fixture = load_fixture(FIXTURE)

    assert fixture["name"] == "basic-offline-eval"
    assert len(fixture["cases"]) == 3
    assert fixture["cases"][0]["expected"] == "4"


def test_evaluate_fixture_applies_bounded_limit() -> None:
    result = evaluate_fixture(FIXTURE, max_cases=2)

    assert result["mode"] == "offline"
    assert result["fixture"] == "basic-offline-eval"
    assert result["processed_cases"] == 2
    assert result["total_cases"] == 3
    assert result["pass_count"] == 1
    assert result["fail_count"] == 1
    assert result["bounded"] is True


def test_run_eval_cli_emits_json_result() -> None:
    completed = subprocess.run(
        [sys.executable, str(RUN_EVAL), str(FIXTURE), "--max-cases", "3"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["mode"] == "offline"
    assert payload["processed_cases"] == 3
    assert payload["pass_count"] == 2
    assert payload["fail_count"] == 1
    assert payload["bounded"] is False
