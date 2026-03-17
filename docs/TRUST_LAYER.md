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

## Still Out Of Scope
- audit bot commands
- full status model rollout
- mass re-audit of historical tasks

## Related Docs
- [TASK_VERIFICATION_POLICY.md](./TASK_VERIFICATION_POLICY.md)
- [AUDIT_WORKFLOW.md](./AUDIT_WORKFLOW.md)
- [STATUS_MODEL.md](./STATUS_MODEL.md)
- [POSTMORTEMS/2026-03-trust-layer-failure.md](./POSTMORTEMS/2026-03-trust-layer-failure.md)
