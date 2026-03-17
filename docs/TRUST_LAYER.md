# Trust Layer

## Purpose
Ralph must not mark a task as complete unless repository evidence supports that claim.

## Current Repair Scope
R10 starts with Milestone 1:
- harden Tech Lead output format
- harden review extraction/parsing
- fail closed on ambiguous review output

## Closure Principle
Runtime success is not the same as implementation success.
An `approve` decision is necessary, but not sufficient, for trusted completion.

## Repaired Review Boundary
Current expected flow:
1. Tech Lead returns one final review block
2. Ralph parses that block from an authoritative source
3. Ambiguous or placeholder review output fails closed
4. Only then can later trust checks run

## Out of Scope For This Iteration
- full evidence gate
- bookkeeping-only diff blocking
- audit bot commands
- status model rollout

## Related Docs
- [TASK_VERIFICATION_POLICY.md](./TASK_VERIFICATION_POLICY.md)
- [AUDIT_WORKFLOW.md](./AUDIT_WORKFLOW.md)
- [STATUS_MODEL.md](./STATUS_MODEL.md)
- [POSTMORTEMS/2026-03-trust-layer-failure.md](./POSTMORTEMS/2026-03-trust-layer-failure.md)
