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
1. `python3 scripts/explain_task.py <TASK_ID>`
2. `ralph.sh audit <TASK_ID>`
3. `python3 scripts/re_audit_tasks.py --task <TASK_ID>`
4. if needed, `python3 scripts/reopen_tasks.py --task <TASK_ID> --to-status pending|needs_human_review|partial --note "..."`

## Minimal Audit Questions
- What did verification decide?
- What non-bookkeeping evidence exists?
- Does current repo truth support `verified_done`, `partial`, or `false_positive`?
- Is manual review safer than automatic migration?
