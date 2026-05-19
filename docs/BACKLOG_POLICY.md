# Backlog Policy

## Purpose
This document defines the practical backlog policy for Ralph while Stage 1 is focused on Auto-safe runner v1.

`tasks.json` remains the single machine-readable source of truth for runtime selection and task history. This policy explains how to interpret its statuses and how to keep the active backlog small and legible without changing runtime behavior.

## Status Semantics
### `pending`
Task is planned work that has not been completed yet.

Use `pending` only when:
- the task is still intended work
- acceptance criteria are still current
- the task could reasonably be selected again, either by explicit task id or as part of a stage backlog

### `done`
Task is believed to be completed, but the repo truth or evidence trail was not checked to the stricter standard used for `verified_done`.

`done` is acceptable for older historical work, but new closure should prefer `verified_done` whenever the implementation and acceptance evidence were actually checked.

### `verified_done`
Task is complete and repo truth or execution evidence has been checked.

This is the preferred closure status when:
- implementation exists in the repo
- the acceptance criteria were validated directly or via focused evidence
- stale-spec resolution was confirmed and documented in `revision_notes`

### `blocked`
Task cannot proceed safely without dependency resolution, policy clarification, or a human decision.

Common reasons:
- unmet dependency
- stale or contradictory acceptance criteria
- task is too broad and needs decomposition
- implementation path is unclear enough that human direction is required

`blocked` should not be used as a long-term parking lot when the real meaning is “not part of the current stage.”

### `false_positive`
Legacy status used for tasks that are not active work.

Current pragmatic reality:
- `false_positive` is also being used as a parking-lot or deferred backlog bucket for historical future-feature tasks
- this is non-ideal but currently documented behavior
- do not assume literal bug-triage semantics from the name alone

Until runtime and backlog tooling gain a dedicated archive or parking-lot status, `false_positive` is the existing non-active bucket.

### `partial`
Task produced useful implementation, but acceptance is not fully met.

Use `partial` sparingly. Prefer a narrower follow-up task when the remaining work is concrete and bounded.

### `needs_human_review`
Task or evidence path reached a state where automation should stop and require explicit human inspection.

This status is appropriate when:
- verification cannot decide safely
- runtime evidence is contradictory
- the automation path would otherwise guess about correctness

## Pragmatic Current Use
The current `tasks.json` mixes:
- active reliability work
- historical completed work
- blocked dependency chains
- stale specs
- manual-only or supervised tasks
- future product and platform features

That is acceptable for now as long as policy stays explicit:
- active work should remain a small stage-scoped subset
- historical or deferred work should not be confused with the active auto-safe lane
- legacy `false_positive` entries should be treated as parked backlog unless explicitly revived

## Stale-Spec Policy
If implementation exists but the old task text no longer matches the architecture:
- close as `verified_done`
- explain the stale-spec resolution in `revision_notes`
- record what changed: implementation exists, acceptance became obsolete, and what evidence was used

If implementation is only partial:
- do not pretend the task is done
- rewrite or decompose into narrower follow-up tasks
- keep only the unresolved gap active

If the architecture changed:
- update docs first
- then decide whether code work is still missing
- avoid reopening broad legacy tasks before the documented model matches reality

## Parking And Manual-Only Policy
For Stage 1 Auto-safe runner v1, the following task families should stay out of the unattended auto-safe lane unless explicitly selected:
- bootstrap and kickoff tasks
- external service tasks
- memory or Qdrant tasks
- integration or full-suite evidence tasks
- product-factory and future-feature tasks

These tasks are usually:
- supervised/manual
- stage-inappropriate
- too broad for unattended overnight execution
- dependent on human product decisions or heavier evidence than overnight-smoke can provide

“Manual-only” in current policy means:
- explicit task selection is allowed
- unattended auto should not treat the task as routine active work

## Active Backlog Policy
The active auto-safe backlog should be:
- small
- stage-scoped
- dominated by simple or moderate tasks
- explicit about `target_files`
- explicit about `acceptance_criteria`

Rules for active tasks:
- tasks that require tests should include test `target_files`
- tasks requiring full integration evidence should be supervised or manual
- tasks that depend on external services should stay out of unattended auto
- stale blocked umbrellas should be rewritten into narrow executable tasks instead of left ambiguous

The active backlog is a planning concept, not a separate runtime file yet.

## Recommended Operating Model
Safest minimal practice:
- keep all history in `tasks.json`
- avoid changing runtime semantics just to improve backlog readability
- document stage scope and parking decisions in docs or reports
- treat `verified_done` as the preferred closure state
- use `revision_notes` to explain stale-spec resolution or policy-based closure

## What To Avoid
- do not overload `blocked` with long-term parking
- do not reopen broad tasks when only one narrow gap remains
- do not leave integration-evidence or product-factory work in the apparent active overnight lane
- do not invent new status semantics ad hoc without documenting them first

## Active Backlog Reporting
When the backlog becomes hard to triage, prefer:
- an `active backlog` report
- a stage-scoped planning doc
- explicit notes about parked/manual-only work

This is safer than physically splitting `tasks.json` or adding new runtime-visible statuses before tooling is ready.
