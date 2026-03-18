# Status Model

## Problem
`done` alone is too weak for a semi-autonomous AI workflow.

## Active Minimal Status Set
- `pending` — runnable by scheduler
- `done` — legacy completed status kept for historical tasks
- `verified_done` — strongly verified completion under current trust rules
- `partial` — repo truth shows incomplete implementation
- `needs_human_review` — evidence is mixed or ambiguous
- `false_positive` — repository strongly contradicts earlier completion claim

## Current Rules
- historical `done` tasks stay untouched unless re-audit changes them
- new auto-verified task completion may be written as `verified_done`
- re-audit runs in dry-run by default
- apply mode updates only strong verdicts

## Scheduler Behavior
- runnable: `pending`
- non-runnable: `done`, `verified_done`, `partial`, `needs_human_review`, `false_positive`

## Re-audit Semantics
- `verified_done`:
  repo truth strongly supports completion
- `false_positive`:
  explicit claimed artifact is missing or clearly contradicted
- `partial`:
  some artifact exists, but completion is incomplete
- `needs_human_review`:
  evidence is mixed; machine should not decide alone

## Operator Actions
- `verified_done`:
  leave complete unless a new contradiction appears
- `false_positive`:
  keep non-runnable; reopen only with an explicit manual note if rerun is justified
- `partial`:
  inspect exact missing gap, then reopen manually if the remaining work is clear
- `needs_human_review`:
  do not auto-apply; inspect audit, explain-task output, and re-audit reasoning first

## Direction
- inspectability is already in place
- this iteration restores backlog truth conservatively
- dry-run first, apply second
