#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


THRESHOLD_RATIO = 5.0
SAMPLE_SIZE = 3


@dataclass
class TaskBenchmark:
    task_id: str
    auto_time_s: float
    estimated_manual_time_s: float
    ratio: float
    where_time_spent: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare Ralph auto-mode task duration against an estimated manual coder-only baseline."
    )
    parser.add_argument("--project-dir", default=".", help="Project directory containing tasks.json and logs/")
    parser.add_argument("--limit", type=int, default=SAMPLE_SIZE, help="Number of simple verified_done tasks to sample")
    parser.add_argument(
        "--threshold",
        type=float,
        default=THRESHOLD_RATIO,
        help="Maximum allowed auto/manual ratio before the script exits with failure",
    )
    return parser


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_tasks(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("tasks", []))


def select_tasks(tasks: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    candidates = [
        task
        for task in tasks
        if task.get("status") == "verified_done" and task.get("complexity") == "simple"
    ]
    candidates.sort(
        key=lambda task: (
            str(task.get("completed_at") or ""),
            str(task.get("id") or ""),
        ),
        reverse=True,
    )
    return candidates[:limit]


def last_metrics_by_task(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        task_id = row.get("task_id") or ""
        if not task_id:
            continue
        latest[task_id] = row
    return latest


def phase_totals_by_task(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for row in rows:
        if (row.get("mode") or "") == "benchmark_manual":
            continue
        task_id = row.get("task_id") or ""
        phase = row.get("phase") or "unknown"
        if not task_id:
            continue
        task_totals = totals.setdefault(task_id, {})
        task_totals[phase] = task_totals.get(phase, 0.0) + float(row.get("duration_s") or 0.0)
    return totals


def parse_duration_from_logs(log_dir: Path, task_id: str) -> float:
    patterns = [
        re.compile(rf"Task\s+{re.escape(task_id)}\s+completed\s+in\s+([0-9]+(?:\.[0-9]+)?)s"),
        re.compile(rf"Task\s+{re.escape(task_id)}\s+.*?\s+in\s+([0-9]+(?:\.[0-9]+)?)s"),
    ]
    durations: list[float] = []
    for path in sorted(log_dir.glob("ralph_*.log")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            for match in pattern.finditer(text):
                durations.append(float(match.group(1)))
    return durations[-1] if durations else 0.0


def estimate_manual_time(auto_time_s: float, attempts: int, phases: dict[str, float]) -> tuple[float, str]:
    coder = round(phases.get("coder", 0.0), 3)
    test = round(phases.get("test", 0.0), 3)
    lead = round(phases.get("lead", 0.0), 3)
    known = coder + test + lead
    other = round(max(auto_time_s - known, 0.0), 3)
    if coder > 0:
        manual = coder
    else:
        manual = round(max(auto_time_s / max(attempts + 2, 2), 0.001), 3)
    where = f"coder={coder:.3f}s, test={test:.3f}s, lead={lead:.3f}s, other={other:.3f}s"
    return manual, where


def benchmark_project(project_dir: Path, limit: int = SAMPLE_SIZE, threshold: float = THRESHOLD_RATIO) -> tuple[list[TaskBenchmark], float]:
    tasks = load_tasks(project_dir / "tasks.json")
    selected = select_tasks(tasks, limit)
    if len(selected) != limit:
        raise SystemExit(f"Need exactly {limit} verified_done simple tasks in tasks.json, found {len(selected)}")

    log_dir = project_dir / "logs"
    metrics_rows = read_csv_rows(log_dir / "metrics.csv")
    phase_rows = read_csv_rows(log_dir / "task_phase_timings.csv")
    metrics_map = last_metrics_by_task(metrics_rows)
    phase_map = phase_totals_by_task(phase_rows)

    results: list[TaskBenchmark] = []
    total_auto = 0.0
    total_manual = 0.0

    for task in selected:
        task_id = str(task.get("id") or "")
        metric_row = metrics_map.get(task_id, {})
        auto_time_s = float(metric_row.get("duration_s") or 0.0)
        if auto_time_s <= 0:
            auto_time_s = parse_duration_from_logs(log_dir, task_id)
        if auto_time_s <= 0:
            raise SystemExit(f"Could not determine auto duration for task {task_id}")
        attempts = int(metric_row.get("attempts") or 0)
        phases = phase_map.get(task_id, {})
        manual_time_s, where_time_spent = estimate_manual_time(auto_time_s, attempts, phases)
        ratio = auto_time_s / manual_time_s if manual_time_s > 0 else float("inf")
        total_auto += auto_time_s
        total_manual += manual_time_s
        results.append(
            TaskBenchmark(
                task_id=task_id,
                auto_time_s=auto_time_s,
                estimated_manual_time_s=manual_time_s,
                ratio=ratio,
                where_time_spent=where_time_spent,
            )
        )

    overall_ratio = total_auto / total_manual if total_manual > 0 else float("inf")
    return results, overall_ratio


def format_table(results: list[TaskBenchmark], overall_ratio: float, threshold: float) -> str:
    lines = [
        "Ralph benchmark: auto vs estimated manual",
        "",
        "task_id | auto_time_s | estimated_manual_time_s | ratio | where_time_spent",
        "--- | ---: | ---: | ---: | ---",
    ]
    for result in results:
        lines.append(
            f"{result.task_id} | {result.auto_time_s:.3f} | {result.estimated_manual_time_s:.3f} | "
            f"{result.ratio:.3f}x | {result.where_time_spent}"
        )
    status = "PASS" if overall_ratio < threshold else "FAIL"
    lines.extend(
        [
            "",
            f"overall_ratio: {overall_ratio:.3f}x",
            f"threshold: {threshold:.3f}x",
            f"assertion: {status}",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    project_dir = Path(args.project_dir).resolve()
    results, overall_ratio = benchmark_project(project_dir, limit=args.limit, threshold=args.threshold)
    output = format_table(results, overall_ratio, args.threshold)
    print(output)
    return 0 if overall_ratio < args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
