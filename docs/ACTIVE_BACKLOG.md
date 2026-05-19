# Active Backlog

## Stage 1 Goal
Stage 1 is `Auto-safe runner v1`.

The objective is a stable unattended runner for narrow reliability work, not bootstrap, product-factory, memory-platform, or security-gate expansion.

## Completed Stage 1 Reliability, Docs, And Policy Work
- `R20-17` — explicit Tester phase documented
- `R20-23` — integration/full-suite evidence tasks excluded from overnight auto-safe by default
- `R20-24` — backlog policy and status semantics documented
- `R19-03` — target_files limit warning path verified as stale-blocked resolved
- `R19-04` — long Python heredoc scope anomaly path verified as stale-blocked resolved
- `R20-16` — overnight-safe test profile verified as stale-blocked resolved

## Remaining Stage 1 Active Task
- `R20-22` — clean or own runtime bookkeeping diffs after auto task completion

This is the only remaining active Stage 1 implementation task after parking later-stage work.

## Deferred Blocked Work
- `R22-01` remains `blocked`

Current interpretation:
- do not close it as `verified_done`
- do not treat it as active Stage 1 work
- decompose it after Stage 1 into narrower state-service migration tasks

## Parked Or Manual-Only Future Work
### Bootstrap And Kickoff
- `R16-05`
- `R17-01`
- `R17-02`
- `R17-03`
- `R17-04`
- `R17-05`
- `R17-06`
- `R17-01A`
- `R17-01B`
- `R17-01C`
- `R20-08`

### Later-Stage Platform / Product Work
- `R22-04` — memory / Qdrant
- `R22-05` — Semgrep security gate

These tasks are intentionally out of the Stage 1 unattended auto-safe lane because they are:
- bootstrap or product-factory work
- dependent on external services or broader architectural choices
- better handled by explicit supervised selection

## Auto-Safe Lane Expectation
After this cleanup:
- unattended auto-safe should no longer select non-Stage-1 feature work
- it is acceptable for auto-safe to return no safe task or a blocked/unrunnable explanation
- Stage 1 execution focus stays on `R20-22`

## Backlog Use
- `tasks.json` remains the runtime source of truth
- this document is the human-readable active backlog view
- parked work stays in `tasks.json` but should not be confused with the current stabilization lane

## Stage 2 Goal
Stage 2 is `CLI/operator UX`.

The objective is to make Ralph convenient as a terminal tool by wrapping existing runtime and script entry points into a small operator command surface.

## Stage 2 Active Task
- `R23-01` — CLI operator UX plan

This task defines the target command surface before wrapper implementation starts.
