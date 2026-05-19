# Ralph Architecture

## Ralph as AI Execution Layer
Ralph is a project-agnostic AI execution layer for software delivery workflows.
It sits on top of an existing repository, reads structured tasks, runs AI agents,
collects outputs, applies review gates, and coordinates human escalation.

## Core Components
- `ralph.sh` — orchestrator loop and execution policy
- `scripts/ralph_bot.py` — Telegram control plane
- `codex exec` — tool runtime used for Coder and Tech Lead agents
- runtime Tester gate — authoritative configured test execution between Coder and Lead
- `scripts/verify_task_closure.py` — closure evidence verifier before finalization
- `scripts/*.py` — task, progress, notification, and memory helpers

## Execution Model
1. Select next pending task from `tasks.json`
2. Build coder prompt from task payload, repo docs, memory, and optional human comment
3. Run Coder agent through `codex exec`
4. If `assets_manifest.json` exists, validate it, wait for missing required assets, and sync them into target paths
5. Run the runtime Tester phase with the configured test command and emit `TESTER_START`, `TESTER_DONE`, `TESTER_TIMEOUT`, and `TESTER_REPORT`
6. Run Tech Lead review through `codex exec` against the diff, acceptance criteria, and tester report
7. Run closure verification to confirm the approved change matches task evidence expectations
8. Finalize by persisting audit, task status, commit flow, progress, memory, logs, and metrics

## Execution Pipeline
Ralph now runs as:

`Coder -> Tester -> Lead -> Verifier -> Finalizer`

Responsibility boundaries:
- Coder writes code and may do narrow local validation only when explicitly needed for implementation, but the runtime Tester phase is authoritative for test execution.
- Tester owns the configured test command, captures stdout/stderr, and emits `TESTER_REPORT` for downstream review.
- Lead reviews the diff, tester report, and acceptance criteria. Lead does not own the test phase and should not substitute ad hoc full-suite demands unless the task explicitly requires them.
- Verifier checks closure evidence after approval so bookkeeping-only or scope-mismatched changes do not finalize as success.
- Finalizer owns commit/status transitions, audit persistence, and end-of-task cleanup.

## Orchestrator
`ralph.sh` is the main runtime controller.

Responsibilities:
- task selection and phase/auto execution
- process supervision and cleanup
- retries, timeouts, exponential backoff, and rate-limit pauses
- prompt assembly for Coder and Tech Lead
- authoritative Tester phase execution and result capture
- closure verification and finalization sequencing
- git commit flow for agent-produced changes
- task lifecycle updates and human alerting

## Tool Runtime
Ralph currently depends on:
- `codex exec` for both agent roles
- configured project test commands for Tester execution
- `git` for diffing and commits
- `gtimeout` for bounded runs
- `python3` helper scripts for state and file updates

## Test Profiles
Ralph separates unattended auto checks from explicit full verification:
- Auto and phase mode should use the configured fast or overnight profile via `test_cmd_fast` when available.
- The fast overnight profile is intended to cover shell helpers, bot command parsing, and core auto-mode guards without pulling in the full integration baseline.
- Explicit verify or manual full checks may use the full project test command such as `make test`.
- Tasks that explicitly require integration evidence or a full-suite baseline are not good candidates for unattended overnight auto by default.

## Tester Signals
The runtime logs the Tester phase with stable event names:
- `TESTER_START` — the configured test command has started.
- `TESTER_DONE` — the command finished and returned an exit code.
- `TESTER_TIMEOUT` — the Tester phase exceeded its allowed wall-clock time.
- `TESTER_REPORT` — structured tester summary handed to Lead.

Common tester-derived reason codes:
- `tester_timeout` — the Tester phase did not complete before timeout.
- `tester_failed` — the configured test command completed but returned a failing result.

## State Model
Runtime state is file-based and repo-local:
- `tasks.json` — backlog, dependencies, and task statuses
- `ralph_state.json` — current runner state
- `ralph_control.json` — bot-to-runner control signals
- `progress.md` — append-only human-readable execution log
- `logs/` — execution logs and metrics

## Memory Model
Persistent memory lives in `.ralph/memory/` and is partially injected into agent prompts.
See `MEMORY_SYSTEM.md` for the memory layers and update rules.

## Human Control Layer
Telegram is the primary remote control interface.

Current control surface:
- start a task, phase, or full auto mode
- stop gracefully or force kill
- inspect tasks, logs, progress, cost, and diff
- leave a comment for the next agent attempt

Asset-heavy projects can also use `assets_manifest.json` as an async handoff between the agent and a human who later supplies binary assets.

## Reliability Model
Implemented safeguards include:
- recursive process cleanup
- retry with exponential backoff
- rate-limit detection and pause
- watchdog around Codex execution
- circuit breaker after repeated failures
- alert path for human intervention
