# Ralph — AI Dev Team Orchestrator

Automated development system that orchestrates Codex CLI to execute tasks.

## Architecture
- **Coder** (codex exec) — writes code
- **Tech Lead** (codex exec) — reviews diffs
- **Orchestrator** (ralph.sh) — manages workflow
- **Telegram Bot** — human control interface

## Quick Start

```bash
# 1. Clone into your project
cd your-project
git clone https://github.com/bogdan/ralph-dev .ralph

# 2. Initialize
.ralph/ralph-init.sh

# 3. Configure
cp .env.example .env
# Edit .env: add RALPH_TELEGRAM_TOKEN, RALPH_TELEGRAM_CHAT_ID

# 4. Add tasks to tasks.json

# 5. Run
.ralph/ralph.sh task YOUR-TASK-01

# Or via Telegram bot
python3 .ralph/scripts/ralph_bot.py
Commands (Terminal)
.ralph/ralph.sh task T01 — run one task
.ralph/ralph.sh phase 1 — run all in phase
.ralph/ralph.sh auto — run all pending
.ralph/ralph.sh status — show progress
.ralph/ralph.sh redo T01 "notes" — reset task
Commands (Telegram)
/status — current state
/start TASK_ID — run task
/stop — stop after current task
/tasks — task list
/log — recent log
/help — all commands EOF
cat > .env.example << ‘EOF’
RALPH_TELEGRAM_TOKEN=your-bot-token
RALPH_TELEGRAM_CHAT_ID=your-chat-id
