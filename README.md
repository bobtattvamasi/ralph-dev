# Ralph — Project-Agnostic AI Dev Team Orchestrator

Ralph is a project-agnostic AI execution layer for software repositories. It runs a 2-agent loop with a `Coder` and `Tech Lead`, exposes a Telegram control interface, and is designed for unattended task execution with human escalation when needed.

## What It Is
- `Coder` agent: implements the current task through `codex exec`
- `Tech Lead` agent: reviews diff, tests, and acceptance criteria
- `Orchestrator`: `ralph.sh` manages task selection, retries, state, and commits
- `Telegram Bot`: `scripts/ralph_bot.py` controls runs remotely and reports status

Ralph attaches to any repo that has `tasks.json`, project docs, and a working test command.

## Features
- 2-agent execution loop: `approve`, `fix`, `alert`, `reorder`
- Telegram control plane for remote operation
- Context injection from repo docs and `.ralph/memory/`
- Memory system with `core`, `recent`, `patterns`, and `decisions`
- Exponential backoff and rate-limit pause handling
- Circuit breaker after repeated failures
- Watchdog around Codex execution
- Recovery-oriented PID cleanup and stop/skip/pause/resume controls
- Per-task logs plus `metrics.csv` for costs and runtime stats

## Architecture
Core docs:
- [AGENTS.md](./AGENTS.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [MEMORY_SYSTEM.md](./MEMORY_SYSTEM.md)

Main runtime pieces:
- [ralph.sh](./ralph.sh) — orchestrator loop
- [scripts/ralph_bot.py](./scripts/ralph_bot.py) — Telegram bot
- [scripts/next_task.py](./scripts/next_task.py) — task picker
- [scripts/update_task.py](./scripts/update_task.py) — task status updates
- [scripts/update_progress.py](./scripts/update_progress.py) — progress log
- [scripts/update_memory.py](./scripts/update_memory.py) — recent memory updates

## Quick Start
### 1. Add Ralph to a target repo
```bash
cd your-project
git clone <your-ralph-repo-url> .ralph
```

### 2. Initialize the target repo
```bash
.ralph/ralph-init.sh
```

This creates:
- `AGENTS.md`
- `ARCHITECTURE.md`
- `MEMORY_SYSTEM.md`
- `AGENTS_CODER.md`
- `AGENTS_LEAD.md`
- `tasks.json`
- `progress.md`
- `.ralph/memory/*`

### 3. Configure Telegram
```bash
cp .ralph/.env.example .env
```

Set:
- `RALPH_TELEGRAM_TOKEN`
- `RALPH_TELEGRAM_CHAT_ID`

### 4. Define tasks
Edit `tasks.json` and add tasks with:
- required: `id`, `phase`, `title`, `description`, `status`
- standard optional: `priority`, `dependencies`, `timeout`, `complexity`, `required_context`, `agent_suitable`, `tags`, `skip_lead`

### 5. Run Ralph
Single task:
```bash
.ralph/ralph.sh task TASK-ID
```

Full queue:
```bash
.ralph/ralph.sh auto
```

Telegram bot:
```bash
python3 .ralph/scripts/ralph_bot.py --project-dir .
```

## Telegram Commands
Current Telegram surface:
- `/status` — current runner state
- `/tasks [phase]` — task list
- `/plan` — phase summary and next pending tasks
- `/start TASK_ID` — run one task
- `/phase NUM` — run one phase
- `/auto` — run all pending tasks
- `/stop` — stop after current step/task boundary
- `/stop now` — force kill the runner
- `/pause` — pause execution until resumed
- `/resume` — resume after pause
- `/add <phase> <title>` — add a pending task
- `/rm <task_id>` — remove a task
- `/redo TASK_ID [notes]` — move task back to pending
- `/comment text` — inject human instruction for the next agent attempt
- `/log [N]` — tail orchestrator log
- `/progress [N]` — tail `progress.md`
- `/tail [N]` — tail latest Codex output
- `/cost` — token-based cost estimate from logs
- `/stats` — all-time aggregate metrics from `metrics.csv`
- `/limits` — today's usage vs cost limit
- `/diff` — last git diff stat
- `/help` — command list

## CLI Commands
- `ralph.sh task <id>` — run one task
- `ralph.sh phase <phase>` — run all ready tasks in a phase
- `ralph.sh auto` — run all pending tasks
- `ralph.sh redo <task_id> [notes]` — reset task state
- `ralph.sh status` — print repo progress summary

## Runtime Model
Ralph executes:
1. pick next pending task from `tasks.json`
2. build coder prompt from docs, memory, and task payload
3. run `Coder`
4. collect diff and test output
5. run `Tech Lead`
6. apply decision
7. update task state, progress, memory, logs, and metrics

## Reliability Model
Implemented safeguards:
- recursive process cleanup
- stop and force-stop paths
- skip current task
- pause/resume via control file
- exponential backoff
- rate-limit detection and pause
- circuit breaker
- execution watchdog

## Metrics And Logs
Ralph writes:
- `logs/ralph_YYYY-MM-DD.log` — execution log
- `logs/metrics.csv` — task metrics
- `ralph_state.json` — current runner state
- `ralph_control.json` — user control actions
- `progress.md` — human-readable progress log

## Development
Run tests:
```bash
make test
```

Shell syntax check:
```bash
bash -n ralph.sh
```

Bot syntax check:
```bash
python3 -c "import ast; ast.parse(open('scripts/ralph_bot.py').read())"
```

## Current Status
Ralph is in active MVP development. The core orchestration loop, memory injection, Telegram controls, metrics, and integration tests are in place. Packaging, richer multi-project support, and more advanced retrieval/routing remain future work.
