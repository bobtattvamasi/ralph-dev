# Ralph Architecture

## High-level architecture
Ralph is a repo-local orchestration system built around a shell runtime plus Python helper scripts. The top-level controller is `ralph.sh`; it reads `tasks.json`, assembles prompts, runs `codex exec` twice (`Coder`, then `Tech Lead`), applies verification and decision logic, persists audit/state artifacts, and exposes remote control through `scripts/ralph_bot.py`.

Packaging exists via `src/ralph/cli.py` and `src/ralph/resources/*`, which ship a runnable copy of the shell runtime, scripts, and templates.

Primary documents:
- `README.md`
- `ARCHITECTURE.md`
- `MEMORY_SYSTEM.md`
- `docs/TRUST_LAYER.md`
- `docs/STATUS_MODEL.md`

## Main components

### CLI / shell entrypoints
- Responsibility: start/init packaged Ralph or direct shell runtime
- Key files: `ralph.sh`, `ralph-init.sh`, `src/ralph/cli.py`, `src/ralph/__main__.py`
- Inputs: CLI args, cwd, `RALPH_PROJECT_DIR`, repo files
- Outputs: process exit codes, initialized files, task execution side effects
- Dependencies: `bash`, packaged resources, `python3`
- Failure modes: missing packaged resource, wrong project dir, syntax/tool mismatch

### Orchestration loop
- Responsibility: end-to-end task execution
- Key files: `ralph.sh`
- Inputs: mode (`task`, `phase`, `auto`, `handoff`, `status`), `tasks.json`, memory, docs, control state
- Outputs: task state changes, logs, commits, audit artifacts, notifications
- Dependencies: `git`, `python3`, `codex`, `gtimeout`, helper scripts
- Failure modes: codex timeout, invalid lead output, stale state, control-file race, prompt budget overflow

### Task queue
- Responsibility: validate task schema and pick next runnable task
- Key files: `scripts/next_task.py`, `scripts/ralph_common.py`, `tasks.json`
- Inputs: task list, optional explicit task/phase
- Outputs: selected task JSON, warnings like `scope_too_wide`
- Dependencies: JSON task store
- Failure modes: malformed `tasks.json`, dependency deadlocks, schema drift

### Persistent state
- Responsibility: runner/control/task/audit persistence
- Key files: `scripts/ralph_common.py`, `scripts/models.py`, `scripts/audit_artifact.py`
- Inputs: runtime updates, control actions, verification results
- Outputs:
  - `ralph_state.json`
  - `ralph_control.json`
  - `.ralph/audit/*.json`
  - `progress.md`
  - `logs/*.log`
  - `logs/metrics.csv`
- Dependencies: file locking, atomic writes
- Failure modes: malformed JSON, concurrent writes, stale files

### Coder agent runner
- Responsibility: build coder prompt and run implementation attempt
- Key files: `ralph.sh`, `templates/AGENTS_CODER.md`
- Inputs: selected task, docs, memory, required context, human comment
- Outputs: repo changes, codex output files, prompt metrics
- Dependencies: `codex exec`
- Failure modes: timeout, rate limit, prompt oversize, out-of-scope changes

### Reviewer agent runner
- Responsibility: review diff/tests and produce authoritative decision JSON
- Key files: `ralph.sh`, `templates/AGENTS_LEAD.md`, `scripts/extract_json.py`
- Inputs: cumulative diff, tests, task definition, scope warnings
- Outputs: parsed review JSON, decision, quality score
- Dependencies: `codex exec`, JSON extraction
- Failure modes: placeholder review, ambiguous JSON, parse mismatch, contradictory output

### Decision logic
- Responsibility: decide approve/fix/alert/reorder/block based on lead + verifier + runtime checks
- Key files: `ralph.sh`, `scripts/verify_task_closure.py`
- Inputs: lead review, changed files, task class, verification result
- Outputs: task completion, retry, blocked/human-review state
- Dependencies: trust-layer helpers
- Failure modes: false positive closure, retry loops, mismatch between task scope and actual files

### Telegram bot / control plane
- Responsibility: remote operation and repo-aware Q&A
- Key files: `scripts/ralph_bot.py`, `scripts/ralph_notify.py`, `scripts/manage_projects.py`
- Inputs: Telegram messages, registry, repo files, state files
- Outputs: control file writes, status messages, Q&A responses, registry updates
- Dependencies: Telegram HTTP API, shared project/task helpers
- Failure modes: transport failure, stale state, registry drift, control-file races

### Repo inspection / Q&A
- Responsibility: answer operator questions from repo context
- Key files: `scripts/ralph_bot.py`
- Inputs: prompt, tasks, logs, selected repo files
- Outputs: streamed `/ask` answer
- Dependencies: configured backend/provider, local context builder
- Failure modes: prompt overgrowth, timeout, provider mismatch

### Logging / reporting
- Responsibility: execution logs, metrics, trust reporting, benchmark reports
- Key files: `ralph.sh`, `scripts/audit_artifact.py`, `scripts/run_benchmark.py`
- Inputs: task attempts, token counts, audit data
- Outputs: `logs/ralph_YYYY-MM-DD.log`, `logs/metrics.csv`, benchmark output, trust report
- Dependencies: filesystem, audit artifacts
- Failure modes: malformed artifacts, formatter failure in final reporting, drift between root and packaged reporters

### Watchdog / recovery
- Responsibility: cleanup, stale-process kill, startup recovery, circuit breaker
- Key files: `ralph.sh`
- Inputs: PIDs, timeouts, stale state, retries
- Outputs: killed processes, paused/blocked state, alerts
- Dependencies: `kill`, `pgrep`, `gtimeout`
- Failure modes: orphan children, false stale detection, crash during cleanup

### Config / env
- Responsibility: repo/project/runtime configuration
- Key files: `scripts/ralph_common.py`, `.env.example`, `pyproject.toml`, `templates/tasks.json.template`
- Inputs: env vars, project registry, task fields
- Outputs: timeout values, active project, packaged metadata
- Dependencies: env, home directory for registry
- Failure modes: doc/code mismatch, missing tooling, hidden defaults

### Tests
- Responsibility: cover unit, integration, packaging, bot, trust, operator helper flows
- Key files: `tests/*.py`
- Inputs: temp repos, fake binaries, fixtures
- Outputs: regression coverage
- Dependencies: `pytest`, stdlib temp/process tooling
- Failure modes: timing-sensitive tests, host-tool differences, packaged/root drift

## Data flow
1. `tasks.json` -> `scripts/next_task.py` / `scripts/ralph_common.py`
2. selected task -> prompt builders in `ralph.sh`
3. prompt -> `codex exec` (`Coder`)
4. repo diff + test output -> `codex exec` (`Tech Lead`)
5. lead JSON -> parsing/normalization in `ralph.sh` and `scripts/extract_json.py`
6. verification gate -> `scripts/verify_task_closure.py`
7. result ->
   - close as `verified_done`/`done`
   - retry with fix instructions
   - block / human review / pause
8. audit/state/reporting ->
   - `.ralph/audit/<TASK_ID>.json`
   - `ralph_state.json`
   - `progress.md`
   - `logs/*`

## State model
- Task
  - Stored in `tasks.json`
  - Fields include `id`, `phase`, `status`, `dependencies`, `timeout`, `complexity`, `required_context`, `risk`, `tags`, `skip_lead`
- Run/session
  - Implicit, modeled through current state and log stream
  - Stored in `ralph_state.json`, `logs/ralph_YYYY-MM-DD.log`
- Status
  - Task statuses: `pending`, `done`, `verified_done`, `partial`, `needs_human_review`, `false_positive`, plus `blocked` seen in current task data
  - Runtime statuses: `idle`, `running`, `paused`, `waiting_human`, `blocked`, `circuit_breaker`, etc.
  - Evidence: `scripts/models.py`, `docs/STATUS_MODEL.md`, `tasks.json`
- Attempts
  - Retry counters are runtime-local in `ralph.sh`
  - Audit artifacts store attempt count
- Logs
  - `logs/ralph_YYYY-MM-DD.log`
  - archived codex output
  - `progress.md`
- Artifacts
  - `.ralph/audit/*.json`
  - `assets_manifest.json`
  - `audit_report.md`
- Decisions
  - lead review JSON + verifier result in audit artifact
- Approvals
  - High-risk gate uses state/control flow inside `ralph.sh`

## Error handling and recovery
- timeout
  - `run_codex()`, watchdog, retry delays, docs-only no-retry path
  - `ralph.sh`
- crash
  - startup recovery and stale-state reconciliation
  - `ralph.sh`, `scripts/ralph_bot.py`
- failed coder run
  - retry with backoff or fail/alert
  - `ralph.sh`
- failed review
  - parse/placeholder/mismatch fail-closed
  - `ralph.sh`, `scripts/extract_json.py`
- failed tests
  - verification and retry/block logic
  - `ralph.sh`
- stale state
  - stale PID detection and reset/recovery
  - `ralph.sh`, `scripts/ralph_bot.py`
- duplicate run
  - bot rejects `/auto` or `/start` if running/PID alive
  - `scripts/ralph_bot.py`
- rate limit
  - pause and retry after configured interval
  - `ralph.sh`
- manual stop/pause
  - control file polled by runtime
  - `ralph.sh`, `scripts/ralph_bot.py`

## Telegram control plane
Commands implemented in `scripts/ralph_bot.py`:
- `/status`
- `/projects`
- `/switch`
- `/tasks`
- `/plan`
- `/article`
- `/add`
- `/rm`
- `/pause`
- `/resume`
- `/start`
- `/phase`
- `/auto`
- `/stop`
- `/exit`
- `/done`
- `/redo`
- `/timeout`
- `/comment`
- `/log`
- `/progress`
- `/tail`
- `/audit`
- `/audit_last`
- `/trust_report`
- `/ask`
- `/cost`
- `/stats`
- `/limits`
- `/diff`
- `/reload`
- `/help`

Multi-project registry support exists in `scripts/manage_projects.py`, storing data in `~/.ralph/projects.json`.

## Safety / human-in-the-loop
- High-risk tasks pause for human approval. Evidence: `ralph.sh`
- Verification-before-closure blocks runtime-only success from auto-closing. Evidence: `scripts/verify_task_closure.py`, `docs/TRUST_LAYER.md`
- Tech Lead cannot safely force runtime-owned bookkeeping into coder fix goals; Ralph sanitizes such requests. Evidence: `docs/TRUST_LAYER.md`, `ralph.sh`
- Asset-heavy tasks can pause in `waiting_human`. Evidence: `ralph.sh`, `README.md`
- Re-audit apply mode is conservative. Evidence: `scripts/re_audit_tasks.py`, `docs/TRUST_LAYER.md`

## Testing and verification
- Test runner: `python3 -m pytest tests`
- Collection observed: 216 tests collected in current repo snapshot
- Test areas:
  - shell helpers: `tests/test_ralph_shell_helpers.py`
  - full integration: `tests/test_integration.py`
  - bot commands/reload/stats/helpers: `tests/test_bot_*.py`
  - trust/audit/re-audit: `tests/test_verify_task_closure.py`, `tests/test_re_audit_tasks.py`
  - packaging: `tests/test_cli_packaging.py`
  - operator helpers: `tests/test_operator_helpers.py`
  - benchmark/assets/models/manage_projects: dedicated test modules

## Architecture risks
- Root vs packaged resource drift. Evidence: `BRITTLENESS_AUDIT.md`
- Shell runtime remains large and monolithic. Evidence: `ralph.sh`
- Mixed truth layers (`tasks.json`, audit artifact, re-audit) require careful operator interpretation. Evidence: `docs/TRUST_LAYER.md`
- Host tooling differences on macOS can still affect shell/runtime behavior. Evidence: recent git log, `ralph.sh`
- Telegram bot, runtime, and helper scripts all mutate shared repo-local files. Evidence: `scripts/ralph_common.py`, `scripts/ralph_bot.py`, `ralph.sh`

## Suggested next architecture improvements
1. Eliminate root/resource duplication by packaging one shared implementation source.
2. Split `ralph.sh` orchestration logic into smaller testable modules.
3. Keep all task/control/state mutation behind shared locked helpers only.
4. Expand verifier from minimal task-aware checks to stronger generic code-feature checks.
5. Formalize run/session model instead of inferring it from logs and state.
6. Move prompt building and review parsing into importable Python modules.
7. Add explicit environment preflight for required host tools before auto mode.
8. Unify backlog truth, latest-run truth, and repo-truth surfaces in one operator view.
9. Reduce timing-sensitive integration behavior where possible.
10. Document multi-project mode as either supported MVP or still experimental.
