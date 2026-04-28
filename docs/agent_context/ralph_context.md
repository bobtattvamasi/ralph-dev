# Ralph Context

## One-liner
Ralph is a project-agnostic AI execution layer that runs a `Coder` + `Tech Lead` loop over a repository task queue and exposes Telegram-based remote control.

## Purpose
- Automate narrow software delivery tasks from `tasks.json` with repo-local state and human escalation.
- Keep task execution inspectable through logs, audit artifacts, verification, and trust reporting.
- Provide operator control over start/stop/pause/review without requiring a separate backend service.

Evidence:
- `README.md`
- `ralph.sh`
- `scripts/ralph_bot.py`
- `docs/TRUST_LAYER.md`

## Target user
- Primary operator: repository owner / developer running Ralph over a local repo. Evidence: `README.md`, `scripts/ralph_bot.py`
- Remote operator: Telegram user controlling the runner. Evidence: `scripts/ralph_bot.py`
- Project owner maintaining stable context and backlog truth. Evidence: `MEMORY_SYSTEM.md`, `tasks.json`
- Named human persona like "Bogdan" is not hardcoded in product logic. Status: UNKNOWN

## Core workflow
1. Task is defined in `tasks.json`.
   - Schema/backfill logic lives in `scripts/ralph_common.py`
   - Selection logic lives in `scripts/next_task.py` and `scripts/ralph_common.py`
2. Orchestrator starts in task/phase/auto/handoff mode via `ralph.sh` or packaged CLI `src/ralph/cli.py`.
3. Ralph resolves project context, state files, control files, docs, and memory.
   - `ralph.sh`
   - `.ralph/memory/*`
4. Ralph builds a coder prompt from:
   - task payload
   - project docs
   - required context
   - recent memory
   - optional human comment from control file
   Evidence: `ralph.sh`
5. Ralph runs the `Coder` through `codex exec`.
   - Runtime wrapper, watchdog, timeout, retries, and output archival live in `ralph.sh`
6. Ralph runs tests / validation gates.
   - Pre-task checks and main test command flow live in `ralph.sh`
7. Ralph builds and runs a `Tech Lead` review prompt through `codex exec`.
   - Review parsing and normalization live in `ralph.sh`
   - Review JSON extraction helpers exist in `scripts/extract_json.py`
8. Ralph decides `approve`, `fix`, `alert`, `reorder`, or block/skip based on:
   - lead review
   - trust-layer verification
   - runtime conditions
   Evidence: `ralph.sh`, `scripts/verify_task_closure.py`
9. Before closure, Ralph verifies task evidence.
   - Audit/trust policy: `docs/TRUST_LAYER.md`, `docs/TASK_VERIFICATION_POLICY.md`
   - Implementation: `scripts/verify_task_closure.py`
10. Ralph writes state, audit artifact, metrics, progress, and updates task status.
    - `ralph_state.json`
    - `ralph_control.json`
    - `.ralph/audit/*.json`
    - `logs/metrics.csv`
    - `progress.md`
11. Human participates when:
    - approving high-risk tasks
    - reviewing blocked or ambiguous tasks
    - providing `/comment`
    - supplying assets from `assets_manifest.json`
    Evidence: `ralph.sh`, `scripts/ralph_bot.py`, `README.md`

## Key concepts

### task
- Meaning: unit of work stored in `tasks.json`
- Where: `tasks.json`, `scripts/ralph_common.py`, `scripts/models.py`
- Status: implemented

### run
- Meaning: one orchestrator execution attempt over one or more tasks
- Where: `ralph.sh`, `ralph_state.json`, `logs/ralph_YYYY-MM-DD.log`
- Status: implemented

### coder
- Meaning: implementation agent invoked through `codex exec`
- Where: `ralph.sh`, `templates/AGENTS_CODER.md`
- Status: implemented

### reviewer
- Meaning: Tech Lead review agent invoked through `codex exec`
- Where: `ralph.sh`, `templates/AGENTS_LEAD.md`
- Status: implemented

### decision
- Meaning: lead output such as `approve`, `fix`, `alert`, `reorder`, plus trust-layer outcomes
- Where: `ralph.sh`, `scripts/extract_json.py`, `scripts/verify_task_closure.py`
- Status: implemented

### queue
- Meaning: pending runnable tasks from `tasks.json`, optionally filtered by phase/task id
- Where: `scripts/next_task.py`, `scripts/ralph_common.py`, `ralph.sh`
- Status: implemented

### state
- Meaning: live runner state plus control inputs
- Where: `ralph_state.json`, `ralph_control.json`, `scripts/ralph_common.py`, `scripts/models.py`
- Status: implemented

### Telegram control plane
- Meaning: remote operator interface for status, queue control, audit, and repo-aware Q&A
- Where: `scripts/ralph_bot.py`
- Status: implemented

### trust/reporting
- Meaning: audit artifacts, trust report, latest-run truth vs backlog truth vs repo-truth
- Where: `docs/TRUST_LAYER.md`, `scripts/audit_artifact.py`, `scripts/re_audit_tasks.py`
- Status: implemented

### verification-before-closure
- Meaning: approved run is not enough; evidence must match task class and changed files
- Where: `scripts/verify_task_closure.py`, `docs/TASK_VERIFICATION_POLICY.md`
- Status: implemented, partial by policy scope

### approval gates
- Meaning: extra blocking points, especially high-risk tasks and failed verification
- Where: `ralph.sh`
- Status: implemented

### watchdog
- Meaning: stale codex process detection and forced cleanup
- Where: `ralph.sh`
- Status: implemented

### retries/timeouts
- Meaning: codex retries, watchdog retries, rate-limit pause, task/lead timeout overrides
- Where: `ralph.sh`, `scripts/ralph_common.py`
- Status: implemented

### repo-aware Q&A
- Meaning: `/ask` builds context from repo files, task state, and logs, then queries provider
- Where: `scripts/ralph_bot.py`
- Status: implemented, provider/routing depth partial

## Current capabilities
- Task / phase / auto / handoff execution. Evidence: `ralph.sh`
- Packaged CLI with `init`, `auto`, `status`, `bot`. Evidence: `src/ralph/cli.py`
- Telegram bot commands for runtime control, audit, trust report, diff, cost, stats, ask. Evidence: `scripts/ralph_bot.py`
- Repo-local state and control files. Evidence: `scripts/ralph_common.py`
- Audit artifact writing and trust report. Evidence: `scripts/audit_artifact.py`
- Re-audit and explain/reopen tooling. Evidence: `scripts/re_audit_tasks.py`, `scripts/explain_task.py`, `scripts/reopen_tasks.py`
- Asset wait/resume workflow. Evidence: `README.md`, `ralph.sh`, `scripts/manage_assets.py`
- Prompt shaping with narrow/broad modes and token budgets. Evidence: `ralph.sh`, `scripts/check_prompt_budgets.py`
- Packaging parity tests and broad integration coverage. Evidence: `tests/test_cli_packaging.py`, `tests/test_integration.py`

## Known limitations
- Root files and packaged copies under `src/ralph/resources/` can drift. Evidence: `BRITTLENESS_AUDIT.md`
- Verification policy is only partially implemented for generic code-feature tasks. Evidence: `docs/TASK_VERIFICATION_POLICY.md`
- `patterns.md` and `decisions.md` memory files are placeholders, not auto-maintained. Evidence: `MEMORY_SYSTEM.md`
- README says richer multi-project support is future work, but partial registry support already exists. Documentation is behind code. Evidence: `README.md`, `scripts/manage_projects.py`, `scripts/ralph_bot.py`
- macOS compatibility around shell tooling is still a hardening area. Evidence: recent git log entries and `ralph.sh`
- `progress.md` is narrative history, not authoritative truth. Evidence: `AGENTS.md`, `docs/TRUST_LAYER.md`

## Non-goals
- Full backend/service architecture. Evidence: `README.md`, shell-first design
- Database-backed memory/state. Evidence: `MEMORY_SYSTEM.md`
- Autonomous mass status rewriting of historical tasks. Evidence: `docs/TRUST_LAYER.md`
- Secret storage or credential management beyond env-based usage. Evidence: `README.md`, `scripts/ralph_notify.py`
- Broad multi-agent parallel execution in current repo snapshot. Status: planned/partial. Evidence: `README.md`, `tasks.json`

## Glossary
- `backlog truth`: current authoritative task status in `tasks.json`
- `latest run truth`: result of latest task attempt in `.ralph/audit/<TASK_ID>.json`
- `repo truth`: later reassessment from `scripts/re_audit_tasks.py`
- `handoff`: mode that tries to close a task from existing repo/worktree evidence without running coder
- `bookkeeping`: runtime-owned files like `tasks.json`, `progress.md`, state/control, logs, audit artifacts
- `verification`: minimal evidence gate before closure
- `high-risk task`: task paused for human approval before final commit/closure
- `required_context`: task-declared high-signal files injected into coder prompt
