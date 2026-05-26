# Ralph Architecture

## Ralph as AI Execution Layer
Ralph is a project-agnostic AI execution layer for software delivery workflows.
It sits on top of an existing repository, reads structured tasks, runs AI agents,
collects outputs, applies review gates, and coordinates human escalation.
It now also exposes an installed CLI so operators can work through a packaged
entrypoint instead of depending on repo-local shell invocation alone.

## Core Components
- `src/ralph/cli.py` — installed CLI layer and console-script entrypoint
- `pyproject.toml` console script — publishes the `ralph` command
- `src/ralph/resources/ralph.sh` — packaged runtime shell and helper resources
- `ralph.sh` — orchestrator loop and execution policy
- `scripts/ralph_bot.py` — Telegram control plane
- `codex exec` — tool runtime used for Coder and Tech Lead agents
- runtime Tester gate — authoritative configured test execution between Coder and Lead
- `scripts/verify_task_closure.py` — closure evidence verifier before finalization
- `scripts/*.py` — task, progress, notification, and memory helpers

## Execution Model
1. Operator enters through the installed CLI or Telegram control layer
2. Select next pending task from `tasks.json`
3. Build coder prompt from task payload, repo docs, memory, and optional human comment
4. Run Coder agent through `codex exec`
5. If `assets_manifest.json` exists, validate it, wait for missing required assets, and sync them into target paths
6. Run the runtime Tester phase with the configured test command and emit `TESTER_START`, `TESTER_DONE`, `TESTER_TIMEOUT`, and `TESTER_REPORT`
7. Run Tech Lead review through `codex exec` against the diff, acceptance criteria, and tester report
8. Run closure verification to confirm the approved change matches task evidence expectations
9. Finalize by persisting audit, task status, commit flow, progress, memory, logs, and metrics

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

Repo and package parity matters here: `ralph.sh` in the repository and
`src/ralph/resources/ralph.sh` in the packaged distribution should behave the
same for operator-visible runtime flows.

## CLI Layer
The CLI layer lives in `src/ralph/cli.py` and is published through the
`pyproject.toml` console script as `ralph`.

Current operator-facing commands include:
- `ralph init`
- `ralph status`
- `ralph doctor`
- `ralph verify`
- `ralph next`
- `ralph explain`
- `ralph groom`
- `ralph tail`
- `ralph log`
- `ralph task <ID>`
- `ralph auto --safe`
- `ralph bot`

Default operator behavior is project-local: `cd <project> && ralph status`
should work without requiring users to reference internal package paths.

## Install And Distribution Model
The current distribution path is install-first rather than publish-first:
- `pipx` is the primary install path during this stage
- GitHub URL or local checkout install flows come before PyPI
- PyPI remains a later distribution milestone, not the current baseline

GitHub Actions package smoke exists to protect the install path, although some
CI coverage may be blocked by account billing constraints.

## Packaged Resources Model
Packaged runtime assets live under `src/ralph/resources/`.

This directory is the package source of truth for:
- `ralph.sh`
- helper shell scripts shipped with the installed CLI
- runtime assets needed by the console-script entrypoint

The package resource model must preserve runtime shell parity between the repo
checkout and the installed distribution.

## Tool Runtime
Ralph currently depends on:
- `codex exec` for both agent roles
- configured project test commands for Tester execution
- `git` for diffing and commits
- `gtimeout` for bounded runs
- `python3` helper scripts for state and file updates

Python baseline is 3.11+.
Platform baseline is macOS/Linux first.
Windows is currently a secondary path and should be treated as supported only
through a bash-capable environment such as Git Bash for now.

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
