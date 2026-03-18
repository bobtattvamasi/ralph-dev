# Trust Layer

## Purpose
Ralph must not mark a task as complete unless repository evidence supports that claim.

## Current Repair Scope
R10 now covers two implemented steps:
- Milestone 1: safe Tech Lead review boundary
- Milestone 2: minimal evidence gate before task closure

## Closure Principle
Runtime success is not the same as implementation success.
An `approve` decision is necessary, but not sufficient, for trusted completion.

## Ownership Boundary
- Coder owns implementation, tests, templates, and docs inside task scope.
- Tech Lead owns review of coder-owned gaps only.
- Ralph runtime owns `tasks.json`, `progress.md`, final status changes, audit artifacts, and final task commits.

Lead fix instructions must not ask the coder to perform runtime-owned bookkeeping.
If they do, Ralph sanitizes those demands and fails closed if no real implementation gap remains.

## Repaired Review Boundary
Current expected flow:
1. Tech Lead returns one final review block
2. Ralph parses that block from an authoritative source
3. Ambiguous or placeholder review output fails closed
4. Only then can closure verification run

## Current Closure Gate
For now, Ralph verifies:
- bookkeeping-only vs non-bookkeeping changes
- minimal task-aware checks for commands, scripts, templates, docs-only tasks, and tests-only tasks

If verification fails, Ralph does not auto-close the task as `done`.

## Audit & Inspectability Layer
Ralph now exposes two distinct outcomes:
- `runtime_success`: the agent loop finished a task run without crashing the execution path
- `verified_success`: the task passed closure verification and was allowed to become `done`

Each task run writes a compact audit artifact to `.ralph/audit/<TASK_ID>.json`.

Current inspection paths:
- `ralph.sh audit <TASK_ID>`
- `ralph.sh audit-last [N]`
- `ralph.sh trust-report`
- Telegram: `/audit <TASK_ID>`
- Telegram: `/audit_last [N]`
- Telegram: `/trust_report`

The audit artifact shows:
- final status
- verification result and reason
- task class
- changed files
- non-bookkeeping evidence
- raw and parsed review

## Conservative Backlog Truth Restoration
Inspectability is now in place, so the next trust step is controlled re-audit.

Current approach:
- dry-run first via `scripts/re_audit_tasks.py`
- apply only when evidence is strong and non-ambiguous
- no mass reopen of historical tasks

This iteration introduces minimal richer statuses for re-audit outcomes:
- `verified_done`
- `partial`
- `needs_human_review`
- `false_positive`

## Still Out Of Scope
- audit bot commands
- full status model rollout
- mass re-audit of historical tasks

## Related Docs
- [TASK_VERIFICATION_POLICY.md](./TASK_VERIFICATION_POLICY.md)
- [AUDIT_WORKFLOW.md](./AUDIT_WORKFLOW.md)
- [STATUS_MODEL.md](./STATUS_MODEL.md)
- [POSTMORTEMS/2026-03-trust-layer-failure.md](./POSTMORTEMS/2026-03-trust-layer-failure.md)
