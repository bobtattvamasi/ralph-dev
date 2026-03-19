# Audit Workflow

## Purpose
Provide a repeatable way to inspect whether Ralph really completed a task and decide what an operator should do next.

## Audit Artifact
Each task attempt produces a repo-local audit record with:
- task snapshot
- raw review
- parsed review
- changed files
- verification result
- closure reason

## Truth Layers
- `tasks.json` is backlog truth: it tells Ralph and the operator what status the task currently has.
- `.ralph/audit/<TASK_ID>.json` is latest run truth: it describes the most recent runtime attempt for that task.
- `python3 scripts/re_audit_tasks.py` is repo-truth reassessment: it inspects current repository evidence and may disagree with the latest runtime attempt.

Do not treat `audit_report.md` as authoritative backlog state. It is a human-readable report of a re-audit run.

## Inspection Paths
- CLI: `ralph.sh audit <TASK_ID>`
- CLI: `ralph.sh audit-last [N]`
- CLI: `ralph.sh trust-report`
- CLI: `python3 scripts/explain_task.py <TASK_ID>`
- CLI: `python3 scripts/re_audit_tasks.py --task <TASK_ID>` or `--last N`
- Telegram: `/audit <TASK_ID>`
- Telegram: `/audit_last [N]`
- Telegram: `/trust_report`

## Manual Review Cases
Use `needs_human_review` when repo truth is mixed or ambiguous.
Use `partial` when some expected artifact exists but completion is incomplete.
Use `false_positive` when claimed completion is strongly contradicted by current repo truth.

## Recommended Operator Sequence
1. inspect current backlog truth with `python3 scripts/explain_task.py <TASK_ID>`
2. inspect latest run truth with `ralph.sh audit <TASK_ID>`
3. inspect current repo truth with `python3 scripts/re_audit_tasks.py --task <TASK_ID>`
4. if these layers disagree, decide from the combination of backlog truth + latest run truth + repo truth whether to rerun, reopen, downgrade, or leave the task as-is
5. if needed, `python3 scripts/reopen_tasks.py --task <TASK_ID> --to-status pending|needs_human_review|partial --note "..."`

## Minimal Audit Questions
- What did verification decide?
- What non-bookkeeping evidence exists?
- Does current repo truth support `verified_done`, `partial`, or `false_positive`?
- Is manual review safer than automatic migration?
