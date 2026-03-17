# Task Verification Policy

## Purpose
Define the minimum evidence required before Ralph can trust task completion.

## Milestone 1 Status
This policy is partially documented now, but not fully enforced yet.
Current implementation only hardens the review boundary.

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
Planned bookkeeping-only set includes:
- `tasks.json`
- `progress.md`
- `.ralph/memory/recent.md`
- runner state/control/log artifacts

## Blocking Rule
If a task claims implementation work but only bookkeeping evidence exists, auto-close should fail.

## Deferred
Full runtime enforcement lands in later R10 tasks.
