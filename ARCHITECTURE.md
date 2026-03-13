# Ralph Architecture

## Ralph as AI Execution Layer
Ralph is a project-agnostic AI execution layer for software delivery workflows.
It sits on top of an existing repository, reads structured tasks, runs AI agents,
collects outputs, applies review gates, and coordinates human escalation.

## Core Components
- `ralph.sh` — orchestrator loop and execution policy
- `scripts/ralph_bot.py` — Telegram control plane
- `codex exec` — tool runtime used for Coder and Tech Lead agents
- `scripts/*.py` — task, progress, notification, and memory helpers

## Execution Model
1. Select next pending task from `tasks.json`
2. Build coder prompt from task payload, repo docs, memory, and optional human comment
3. Run Coder agent through `codex exec`
4. If `assets_manifest.json` exists, validate it, wait for missing required assets, and sync them into target paths
5. Capture git diff and test output
6. Run Tech Lead review through `codex exec`
7. Resolve decision: `approve`, `fix`, `alert`, or `reorder`
8. Persist state, progress, memory, logs, and metrics

## Orchestrator
`ralph.sh` is the main runtime controller.

Responsibilities:
- task selection and phase/auto execution
- process supervision and cleanup
- retries, timeouts, exponential backoff, and rate-limit pauses
- prompt assembly for Coder and Tech Lead
- git commit flow for agent-produced changes
- task lifecycle updates and human alerting

## Tool Runtime
Ralph currently depends on:
- `codex exec` for both agent roles
- `make test` as the default verification gate
- `git` for diffing and commits
- `gtimeout` for bounded runs
- `python3` helper scripts for state and file updates

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
