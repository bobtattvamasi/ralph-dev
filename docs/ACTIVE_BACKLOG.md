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
- `R20-22` — clean or own runtime bookkeeping diffs after auto task completion

## Stage 1 Status
Stage 1 `Auto-safe runner v1` is closed.

The Stage 1 reliability lane is complete enough that unattended auto-safe behavior, runtime bookkeeping cleanup, and backlog hygiene are no longer the active bottleneck.

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
- Stage 1 execution no longer has an active implementation task

## Backlog Use
- `tasks.json` remains the runtime source of truth
- this document is the human-readable active backlog view
- parked work stays in `tasks.json` but should not be confused with the current stabilization lane

## Stage 2 Goal
Stage 2 is `CLI/operator UX`.

The objective is to make Ralph convenient as a terminal tool by wrapping existing runtime and script entry points into a small operator command surface.

## Stage 2 Status
Stage 2 `CLI/operator UX` core command surface is implemented.

There are no active pending Stage 2 CLI tasks after `R23-10`.

Stage 2 is now considered checkpoint-complete.

## Completed Stage 2 CLI Work
- `R23-01` — CLI operator UX plan
- `R23-02` — basic CLI wrappers
- `R23-03` — `doctor`
- `R23-04` — `groom`
- `R23-06` — `status`
- `R23-07` — `tail`
- `R23-07` — `log`
- `R23-10` — `verify`
- `ralph next`
- `ralph explain`
- `ralph auto --safe`
- `ralph task <ID>`

## Current Operator Surface
- `ralph next`
- `ralph explain`
- `ralph doctor`
- `ralph groom`
- `ralph status`
- `ralph tail`
- `ralph log`
- `ralph verify`
- `ralph auto --safe`
- `ralph task <ID>`

## Next-Stage Decision Options
- packaging polish
- project bootstrap/kickoff
- product factory

## Stage R24 Goal
Stage `R24` is `Packaging Polish`.

The objective is to make Ralph reliable as an installed terminal tool, not only as a repo-local checkout with helper scripts nearby.

## Stage R24 Status
Stage `R24` is checkpoint-complete.

## Completed R24 Work
- `R24-01` — packaging polish plan
- `R24-02` — installed CLI smoke coverage
- `R24-03` — installed-mode verify
- `R24-04` — packaging smoke matrix consolidation
- `R24-05` — packaged resource audit
- `R24-06` — resource bundling audit test
- `R24-07` — package data manifest audit
- `R24-08` — packaging test matrix split
- `R24-09` — operator install guide

## Stage R24 Focus
- installed `venv` and `pipx` flow
- packaged resources and helper script coverage
- `--project-dir` consistency
- installed-mode smoke reliability for the current operator surface
- operator-facing install and usage documentation

## Next-Stage Decision Options
- bootstrap/kickoff
- release polish
- product-factory planning

## Release Readiness Checkpoint
Current checkpoint status for the installed CLI packaging lane:
- local `pipx` install works on Python 3.11+
- installed `ralph init` no longer leaks internal package paths
- `ralph status`, `ralph doctor`, `ralph verify`, `ralph next`, and `ralph explain` work from project-local cwd
- `ralph doctor` now skips missing project-local `tests/test_shell_parity.py` the same way `verify` does
- Python build artifacts are ignored and `src/ralph_dev.egg-info` is untracked
- branch `dev/auto-pilot` has been pushed to GitHub
- GitHub Actions package smoke workflow exists, but it is currently blocked by GitHub account billing rather than a known code failure

## Remaining Blockers Before Main Merge / v0.1.0 Tag
- unblock GitHub Actions package smoke so installed CLI packaging can be verified in hosted CI
- prove the release/tag flow on top of the pushed `dev/auto-pilot` branch
- finish the release-polish pass for merge readiness notes, operator install expectations, and post-merge packaging confidence
- keep PyPI publishing deferred until CI and tag flow are stable
