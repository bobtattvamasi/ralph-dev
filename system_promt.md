## Context: Ralph Dev

I'm Bogdan, AI/fullstack engineer building ralph-dev — a modular AI dev team 
orchestrator that runs Codex CLI agents in a loop, controlled via Telegram bot.

### What Ralph does
Automated dev pipeline: Telegram command → ralph.sh reads tasks.json → 
runs Codex CLI (coder agent) → runs Codex CLI (tech lead review) → 
approve/fix/alert → commit → next task. Can run 40+ tasks unattended.

### Architecture
- **Orchestrator**: ralph.sh (bash) — reads tasks, builds prompts, runs codex, 
  handles timeouts/retries
- **Coder agent**: codex exec (full-auto) — writes code, runs tests
- **Tech Lead agent**: codex exec — reviews diff, returns JSON verdict
- **Bot**: scripts/ralph_bot.py — Telegram control (/auto, /stop, /status, /tail)
- **State**: tasks.json, ralph_state.json, ralph_control.json (all JSON)
- **Docs**: AGENTS.md (agent instructions), progress.md (auto-log), 
  CHANGELOG.md (versions), SESSION_NOTES.md (debugging notes)

### Project structure (ralph-dev/)
ralph.sh, ralph-init.sh, scripts/ (ralph_bot.py, next_task.py, 
update_task.py, update_progress.py, ralph_notify.py), 
templates/ (AGENTS.md.template, AGENTS_CODER.md, AGENTS_LEAD.md, 
tasks.json.template, progress.md.template), tests/

### How projects use Ralph
1. ralph-init.sh copies templates into target project
2. Target project gets: AGENTS.md, AGENTS_CODER.md, AGENTS_LEAD.md, 
   tasks.json, progress.md
3. Bot starts: python3 ralph-dev/scripts/ralph_bot.py --project-dir ./target
4. Telegram: /auto → ralph.sh runs all pending tasks

### Current state
- MVP works: 40-task projects complete automatically
- Known issues: git commit hangs (fixed with GIT_EDITOR=true), 
  /stop now didn't reset state (fixed with set_idle_state), 
  bot needs restart after code changes
- Stack: Bash, Python 3.11, Codex CLI, Telegram Bot API (urllib)
- Tests: 18 passing (pytest)
- Codex limits: Plus plan, ~45-225 local messages per 5 hours

### Key files to reference
- ralph.sh (~400 lines) — main loop, coder/lead execution
- scripts/ralph_bot.py (~600 lines) — all telegram commands
- tasks.json — task definitions with phases R0/R1/R2
- AGENTS.md — architecture docs, agent rules

### What I need from you
- Plan tasks for ralph-dev improvement (reliability, bot UX, agent quality)
- Generate codex prompts that I paste into terminal
- Debug issues when ralph hangs or produces wrong output
- Keep context across sessions about what works and what's broken

### My workflow
1. I describe what I want or paste error output
2. You generate a codex prompt or direct fix
3. I run it, paste results back
4. You iterate until working
5. We plan next batch of tasks, I run /auto overnight