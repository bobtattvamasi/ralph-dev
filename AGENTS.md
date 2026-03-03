# AGENTS.md — Ralph Dev

## What is Ralph
AI dev team orchestrator. Runs Codex CLI agents (Coder + Tech Lead) in a loop,
controlled via Telegram bot. Project-agnostic — attaches to any repo.

## Architecture
Telegram Bot (scripts/ralph_bot.py)
↓ /start TASK-01
Orchestrator (ralph.sh)
↓ reads tasks.json from PROJECT_DIR
↓ loop:
├── Coder Agent (codex exec) → writes code, runs tests, commits
├── Tech Lead Agent (codex exec) → reviews diff, decides: approve/fix/alert
├── If fix → coder retries (max 3)
├── If approve → update tasks.json, progress.md, commit
└── If alert → notify human via Telegram



## Key Concepts
- `RALPH_DIR` — where ralph lives (this repo)
- `PROJECT_DIR` — target project (has tasks.json, AGENTS.md, progress.md)
- ralph-init.sh — initializes ralph in a new project
- Templates in templates/ — copied to project on init

## Files
| File | Purpose |
|------|---------|
| ralph.sh | Main orchestrator (bash) |
| ralph-init.sh | Project initializer |
| scripts/ralph_bot.py | Telegram bot |
| scripts/ralph_notify.py | Send telegram notifications |
| scripts/next_task.py | Pick next pending task from tasks.json |
| scripts/update_task.py | Update task status in tasks.json |
| scripts/update_progress.py | Append to progress.md |
| templates/ | Files copied to new projects on init |

## How It Works (per task)
1. ralph.sh reads task from tasks.json
2. Builds prompt with task + AGENTS.md + fix instructions
3. Runs `codex exec` (Coder) with 180s timeout
4. Captures diff + test output
5. Runs `codex exec` (Tech Lead) to review
6. Parses JSON decision: approve/fix/alert/reorder
7. If approve → marks done, commits, next task
8. If fix → sends fix_instructions back to Coder (max 3 retries)
9. If alert → notifies human via Telegram

## Stack
- Bash (ralph.sh, ralph-init.sh)
- Python 3.11 (bot, helper scripts)
- Codex CLI (`codex exec`)
- Telegram Bot API (urllib, no frameworks)
- JSON for state (tasks.json, ralph_state.json, ralph_control.json)

## Rules for Development
1. ralph.sh must stay project-agnostic (no hardcoded project paths)
2. All script paths use $RALPH_DIR
3. All project paths use $PROJECT_DIR
4. Bot uses Path(__file__).parent.parent for RALPH_DIR
5. No external Python dependencies except dotenv
6. Bash must pass `bash -n ralph.sh`
7. Python must pass `python3 -c "import ast; ast.parse(...)"`

## Current Plan
See tasks.json for current development tasks.
Phases: R0 (setup) → R1 (stability) → R2 (convenience) → R3 (multi-project)

### Memory System (.ralph/memory/)
Ralph maintains persistent memory across tasks:
- core.md — project architecture, conventions (static, updated manually)
- recent.md — last 5 task summaries (auto-updated after each approved task)
- patterns.md — recurring error patterns and solutions (grows over time)
- decisions.md — architectural decisions log (grows over time)

Before each coder task, ralph.sh injects core.md + recent.md into the prompt.

### Circuit Breaker
3 consecutive agent failures → pipeline stops, human notified.
Rate limit detected → 30 minute pause → retry.
Exponential backoff: 60s → 120s → 300s between retries.

### Model Routing
Tasks with complexity: simple → codex-mini (saves rate limit budget)
Tasks with complexity: complex → codex-max (default)
Tasks with agent_suitable: false → skip, notify human

### Task Schema (enhanced)
Required: id, phase, title, description, status
Optional: complexity (simple/moderate/complex), required_context (file list),
agent_suitable (true/false/partial), timeout, model, dependencies
