# Status Model

## Problem
`done` alone is too weak for a semi-autonomous AI workflow.

## Planned Extended Statuses
- `pending`
- `verified_done`
- `claimed`
- `partial`
- `blocked`
- `failed`
- `needs_human_review`
- `false_positive`
- `unverified`

## Milestone 1
This iteration does not roll out the new status model.
It only reduces false positives at the review boundary.

## Direction
- runtime path result and task truth should become separate signals
- suspicious closures should not silently remain `done`
- later R10 tasks will define migration rules and backlog behavior
