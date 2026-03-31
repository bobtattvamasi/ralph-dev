from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_benchmark.py"


def write_project_fixture(tmp_path: Path, *, failing: bool) -> Path:
    project_dir = tmp_path / "project"
    logs_dir = project_dir / "logs"
    logs_dir.mkdir(parents=True)
    tasks = {
        "version": 1,
        "project": "benchmark-test",
        "tasks": [
            {
                "id": "T01",
                "phase": "OPS",
                "title": "Task one",
                "description": "Task one",
                "status": "verified_done",
                "complexity": "simple",
                "completed_at": "2026-03-30T10:00:00+00:00",
            },
            {
                "id": "T02",
                "phase": "OPS",
                "title": "Task two",
                "description": "Task two",
                "status": "verified_done",
                "complexity": "simple",
                "completed_at": "2026-03-30T11:00:00+00:00",
            },
            {
                "id": "T03",
                "phase": "OPS",
                "title": "Task three",
                "description": "Task three",
                "status": "verified_done",
                "complexity": "simple",
                "completed_at": "2026-03-30T12:00:00+00:00",
            },
            {
                "id": "T04",
                "phase": "OPS",
                "title": "Ignored task",
                "description": "Ignored task",
                "status": "pending",
                "complexity": "simple",
            },
        ],
    }
    (project_dir / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    (logs_dir / "metrics.csv").write_text(
        "\n".join(
            [
                "timestamp,task_id,status,duration_s,attempts,files_changed,quality,cost_est,runtime_success,verified_success",
                "2026-03-30T10:05:00Z,T01,success,120,1,2,good,0.10,yes,yes",
                "2026-03-30T11:05:00Z,T02,success,150,1,1,good,0.10,yes,yes",
                "2026-03-30T12:05:00Z,T03,success,180,2,3,good,0.10,yes,yes",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    coder_rows = ["20", "25", "30"] if failing else ["40", "50", "60"]
    (logs_dir / "task_phase_timings.csv").write_text(
        "\n".join(
            [
                "timestamp,task_id,attempt,mode,phase,duration_s",
                f"2026-03-30T10:00:10Z,T01,1,auto,coder,{coder_rows[0]}",
                "2026-03-30T10:02:10Z,T01,1,auto,test,50",
                "2026-03-30T10:03:10Z,T01,1,auto,lead,10",
                f"2026-03-30T11:00:10Z,T02,1,auto,coder,{coder_rows[1]}",
                "2026-03-30T11:02:10Z,T02,1,auto,test,60",
                "2026-03-30T11:03:10Z,T02,1,auto,lead,10",
                f"2026-03-30T12:00:10Z,T03,1,auto,coder,{coder_rows[2]}",
                "2026-03-30T12:02:10Z,T03,1,auto,test,70",
                "2026-03-30T12:03:10Z,T03,1,auto,lead,20",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return project_dir


def run_benchmark(project_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--project-dir", str(project_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_run_benchmark_reports_breakdown_and_passes(tmp_path: Path) -> None:
    project_dir = write_project_fixture(tmp_path, failing=False)

    result = run_benchmark(project_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "task_id | auto_time_s | estimated_manual_time_s | ratio | where_time_spent" in result.stdout
    assert "T01" in result.stdout
    assert "T02" in result.stdout
    assert "T03" in result.stdout
    assert "overall_ratio: 3.000x" in result.stdout
    assert "assertion: PASS" in result.stdout


def test_run_benchmark_exits_nonzero_when_ratio_exceeds_threshold(tmp_path: Path) -> None:
    project_dir = write_project_fixture(tmp_path, failing=True)

    result = run_benchmark(project_dir)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "overall_ratio: 6.000x" in result.stdout
    assert "assertion: FAIL" in result.stdout
