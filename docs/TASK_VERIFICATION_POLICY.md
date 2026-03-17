# Task Verification Policy

## Purpose
Define the minimum evidence required before Ralph can trust task completion.

## Current Implemented Scope
This policy is now partially enforced before task closure.

## Task Classes
- Code feature
- Command
- Script
- Template
- Docs-only
- Tests-only
- Config-only

## Planned Verification Rules
- Code feature: non-bookkeeping code diff plus relevant test signal
- Command: handler exists, command is wired, basic test or smoke path
- Script: file exists and runs/imports safely
- Template: file exists with required sections
- Docs-only: expected docs changed with required content
- Tests-only: target tests exist and pass
- Config-only: config exists and is actually consumed

## Bookkeeping-Only Files
Current bookkeeping-only set includes:
- `tasks.json`
- `progress.md`
- `.ralph/memory/recent.md`
- `.ralph/memory/decisions.md`
- `.ralph/memory/patterns.md`
- `ralph_state.json`
- `ralph_control.json`
- PID files and log artifacts

## Blocking Rule
If a task claims implementation work but only bookkeeping evidence exists, auto-close should fail.

## Implemented Minimal Checks
- Command: handler/routing evidence plus test evidence
- Script: expected script exists and compiles if Python
- Template: expected template exists
- Docs-only: documentation file evidence exists
- Tests-only: real test-file evidence exists

## Deferred
- deeper code-feature verification
- audit artifact linkage
- richer status outcomes beyond fail-fix / block
