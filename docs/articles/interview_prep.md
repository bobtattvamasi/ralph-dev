# Ralph Dev: Interview Prep

## Summary
Ralph is a repo-local AI orchestration layer for software delivery. It reads tasks from `tasks.json`, runs a `Coder` agent and a `Tech Lead` agent through `codex exec`, verifies the result through a trust layer, and exposes Telegram as the operator control surface.

This article is a compact interview-prep version of the system. It focuses on the execution model, trust boundaries, task lifecycle, operator workflows, and the most important tradeoffs in the current architecture.

## What Ralph Actually Is
Ralph is not a web app and not a generic workflow engine. It is a project-attached runtime that sits inside a repository and drives task execution using local files as the main control and truth surfaces.

At a high level, Ralph combines:
- a shell orchestrator in `ralph.sh`
- Python helpers for task, audit, and verification logic
- a Telegram bot in `scripts/ralph_bot.py`
- file-based state in `tasks.json`, `ralph_state.json`, `ralph_control.json`, and `.ralph/audit/*.json`

## Core Execution Loop
The main execution flow is:
1. Read the next runnable task from `tasks.json`
2. Build a coder prompt from project docs, memory, task payload, and optional operator comment
3. Run the `Coder`
4. Collect diff and test output
5. Run the `Tech Lead`
6. Parse and validate the lead review
7. Run closure verification
8. Update status, progress, memory, metrics, and audit artifacts

The main modes exposed by `ralph.sh` are:
- `task`
- `handoff`
- `phase`
- `auto`
- `status`
- `audit`
- `audit-last`
- `trust-report`
- `re-audit-last`
- `benchmark`
- `redo`

## Main Components
| Path | Responsibility |
|---|---|
| `ralph.sh` | Main orchestrator, retry loop, prompt assembly, process control, audit integration |
| `ralph-init.sh` | Project bootstrap and template install |
| `scripts/ralph_bot.py` | Telegram bot, operator control plane, state watcher |
| `scripts/next_task.py` | Runnable task selection and deadlock explanation |
| `scripts/update_task.py` | Backlog status mutation |
| `scripts/verify_task_closure.py` | Trust gate before completion |
| `scripts/audit_artifact.py` | Audit artifact persistence and trust report |
| `scripts/re_audit_tasks.py` | Repo-truth reassessment for completed tasks |
| `scripts/explain_task.py` | Operator-facing task truth explanation |
| `scripts/reopen_tasks.py` | Controlled reopen/reclassify helper |
| `scripts/manage_assets.py` | Async asset manifest validation and sync |
| `src/ralph/cli.py` | Packaged CLI entrypoint |
| `src/ralph/resources/*` | Packaged mirror of runtime scripts and templates |

## Control Plane
The human control surface is the Telegram bot. It can:
- start task, phase, or auto execution
- pause, resume, stop, or force-kill runtime
- add, remove, redo, or mark tasks done
- show status, plan, progress, logs, cost, metrics, audits, and trust report
- inject a `/comment` for the next coder attempt
- run bounded `/ask`

The bot writes operator intent into `ralph_control.json` and watches `ralph_state.json` plus PID files. It is a control plane, not the execution engine itself.

## Task Model
Backlog truth is stored in `tasks.json`. A task is runnable only when:
- its status is `pending`
- all dependencies are in `done` or `verified_done`

The current model also uses richer states such as:
- `verified_done`
- `partial`
- `needs_human_review`
- `false_positive`
- `blocked`

This lets the runtime distinguish “agent loop finished” from “repository evidence supports completion”.

## Trust Model
Ralph explicitly separates multiple truth layers:
- `tasks.json`: backlog truth
- `.ralph/audit/<TASK>.json`: latest run truth
- `re_audit_tasks.py`: repo-truth reassessment

The intended ownership boundary is:
- `Coder` owns implementation inside task scope
- `Tech Lead` owns review of coder-owned gaps
- runtime owns final bookkeeping, status updates, audit artifacts, and final commits

This matters because `approve` from the lead is not enough by itself. Ralph still runs `verify_task_closure.py` before writing `verified_done`.

## Audit and Re-Audit
Each task run may write a compact audit artifact into `.ralph/audit/`. That artifact captures:
- task id and title
- final run status
- verification result and reason
- changed files and evidence files
- raw and parsed lead review
- attempts, duration, runtime success, verified success

Re-audit is a separate later operation. It looks at the current repository and can classify prior completed tasks as:
- `verified_done`
- `false_positive`
- `partial`
- `needs_human_review`

This is how Ralph repairs backlog truth after suspicious historical completions.

## Handoff Mode
`handoff` is a real execution mode, not just a human note. In this mode Ralph tries to find task-scoped evidence already present in the worktree or commit history and push that directly into review, possibly without running a new coder pass.

This is useful when work already exists but trust/closure is still missing. It is also risky, because the handoff path depends on task-text-driven heuristics to infer which files count as valid task evidence.

## Observability
The main evidence surfaces are:
- `logs/ralph_YYYY-MM-DD.log`
- `logs/metrics.csv`
- `logs/task_phase_timings.csv`
- `ralph_state.json`
- `ralph_control.json`
- `.ralph/audit/*.json`
- `progress.md`
- `SESSION_NOTES.md`

Not all of these are equally authoritative. `progress.md` and `SESSION_NOTES.md` are narrative. `tasks.json`, `ralph_state.json`, and `.ralph/audit/*.json` are operational truth surfaces.

## Key Tradeoffs
### Why file-based state
The project uses JSON and markdown files instead of a DB because the system is meant to stay repo-local, portable, debuggable, and easy for operators to inspect.

### Why a two-agent loop
The `Coder -> Tech Lead` split gives a clearer quality gate, but it costs time and tokens.

### Why a trust layer exists at all
Earlier versions could mark tasks done without strong repo evidence. The trust layer is the repair for that failure mode.

### Why packaged resources are risky
The installable CLI uses `src/ralph/resources/*`, which means the packaged runtime can drift from the root scripts if they are not kept in sync.

## Interview Questions to Expect
If someone is interviewing you about Ralph, expect questions like:
- Why are there multiple truth layers instead of a single task status?
- Why is `approve` not enough for completion?
- Why is `progress.md` narrative only?
- What does handoff change in the execution flow?
- How do operator actions bypass or respect trust boundaries?
- What are the risks of duplicated packaged resources?

## Short Takeaway
Ralph is best understood as a repo-local autonomous delivery harness with:
- structured backlog execution
- operator control through Telegram
- a conservative trust and audit layer
- strong inspectability
- some real packaging and state-coherence risks that still need tightening
