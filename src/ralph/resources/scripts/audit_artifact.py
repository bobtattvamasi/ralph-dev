#!/usr/bin/env python3
"""Write and inspect Ralph task audit artifacts."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PROJECT_DIR = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
AUDIT_DIR = PROJECT_DIR / ".ralph" / "audit"


def ensure_dir() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def write_artifact() -> int:
    raw = sys.stdin.read().strip() or "{}"
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("audit payload must be a JSON object")
    except Exception as exc:
        payload = {
            "task_id": os.environ.get("RALPH_TASK_ID", "unknown"),
            "title": os.environ.get("RALPH_TASK_TITLE", ""),
            "status": os.environ.get("RALPH_AUDIT_STATUS", "failed"),
            "verification": {
                "result": "needs_human_review",
                "reason": f"Audit payload parse error: {exc}",
                "task_class": "unknown",
                "evidence_files": [],
            },
            "changes": {"all": [], "non_bookkeeping": []},
            "review": {"raw": "", "parsed": {}},
            "attempts": 0,
            "duration_sec": 0,
            "timestamp": os.environ.get("RALPH_AUDIT_TIMESTAMP", ""),
            "runtime_success": False,
            "verified_success": False,
            "error": True,
        }

    task_id = str(payload.get("task_id") or os.environ.get("RALPH_TASK_ID", "unknown")).strip() or "unknown"
    payload["task_id"] = task_id

    try:
        ensure_dir()
        path = AUDIT_DIR / f"{task_id}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(str(path))
        return 0
    except Exception as exc:
        try:
            ensure_dir()
            fallback = dict(payload)
            fallback["error"] = True
            fallback["error_message"] = str(exc)
            path = AUDIT_DIR / f"{task_id}.json"
            path.write_text(json.dumps(fallback, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(str(path))
            return 0
        except Exception as fallback_exc:
            print(f"Failed to write audit artifact: {fallback_exc}", file=sys.stderr)
            return 1


def load_artifact(task_id: str) -> dict:
    path = AUDIT_DIR / f"{task_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def show_artifact(task_id: str) -> int:
    path = AUDIT_DIR / f"{task_id}.json"
    if not path.exists():
        print(f"Audit artifact not found for {task_id}")
        return 1
    data = load_artifact(task_id)
    verification = data.get("verification", {})
    changes = data.get("changes", {})
    non_bookkeeping = changes.get("non_bookkeeping", []) or []
    all_changes = changes.get("all", []) or []

    lines = [
        f"Audit: {data.get('task_id', task_id)} — {data.get('status', 'unknown')}",
        f"Runtime success: {data.get('runtime_success', False)}",
        f"Verified success: {data.get('verified_success', False)}",
        f"Verification: {verification.get('result', 'unknown')} ({verification.get('task_class', 'unknown')})",
        f"Reason: {verification.get('reason', 'n/a')}",
        f"Attempts: {data.get('attempts', '?')}",
        f"Duration: {data.get('duration_sec', '?')}s",
        f"Timestamp: {data.get('timestamp', 'n/a')}",
        "Changed files: " + (", ".join(all_changes) if all_changes else "none"),
        "Evidence files: " + (", ".join(non_bookkeeping) if non_bookkeeping else "none"),
    ]
    print("\n".join(lines))
    return 0


def trust_report() -> int:
    ensure_dir()
    files = sorted(AUDIT_DIR.glob("*.json"))
    records: list[dict] = []
    for path in files:
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue

    total = len(records)
    verified_success = sum(1 for item in records if item.get("verified_success") is True)
    runtime_success_only = sum(
        1
        for item in records
        if item.get("runtime_success") is True and item.get("verified_success") is not True
    )
    failed_or_blocked = sum(
        1 for item in records if str(item.get("status", "")) in {"failed", "blocked"}
    )
    pct = round((verified_success / total) * 100, 1) if total else 0.0

    lines = [
        "=== Trust Report ===",
        f"Total tasks: {total}",
        f"Verified success: {verified_success}",
        f"Runtime success only: {runtime_success_only}",
        f"Failed/blocked: {failed_or_blocked}",
        f"Verified %: {pct}%",
    ]
    if records:
        lines.append("")
        lines.append("Last tasks:")
        recent = sorted(records, key=lambda item: str(item.get("timestamp", "")), reverse=True)[:5]
        for item in recent:
            lines.append(
                f"  {item.get('task_id', '?')}: {item.get('status', 'unknown')} "
                f"(runtime={item.get('runtime_success', False)}, verified={item.get('verified_success', False)})"
            )
    print("\n".join(lines))
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: audit_artifact.py {write|show|report} [task_id]")
        return 1
    cmd = sys.argv[1]
    if cmd == "write":
        return write_artifact()
    if cmd == "show":
        if len(sys.argv) < 3:
            print("Usage: audit_artifact.py show <task_id>")
            return 1
        return show_artifact(sys.argv[2])
    if cmd == "report":
        return trust_report()
    print("Usage: audit_artifact.py {write|show|report} [task_id]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
