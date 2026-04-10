Context: Ralph Dev

## What is Ralph
Ralph — bash orchestrator for rapid MVP prototyping. Runs Codex CLI agents in a loop, managed via Telegram bot. Internal tool, not a product. The developer's superpower for building vertical AI products fast.

## What Ralph Does
1. Takes a tasks.json with a project plan (phases, priorities, dependencies)
2. Runs tasks automatically: ./ralph.sh auto
3. For each task: builds prompt → runs Codex CLI (coder) → runs Codex CLI (lead review) → approve/fix/retry → git commit → next task
4. Handles failures: timeout, watchdog, retry with backoff, skip and alert
5. Developer controls and monitors via Telegram bot
6. Produces working committed code with audit trail

## Architecture
Telegram → ralph_bot.py → ralph.sh → codex exec (coder) → codex exec (lead)
                                           ↓ approve/fix/alert
                                      git commit → next task

## Core Files
- ralph.sh — main loop, prompt builder, codex runner, timeout/retry/watchdog
- scripts/ralph_bot.py — Telegram bot, all commands
- tasks.json — task definitions (phases, statuses: pending/done/verified_done/blocked/false_positive/partial)
- ralph_state.json — runtime state (can be stale after crashes)
- ralph_control.json — operator control signals
- logs/ralph_YYYY-MM-DD.log — execution log
- logs/metrics.csv — token/cost metrics
- .ralph/audit/ — per-task audit artifacts and lead reasoning

## Key Scripts
next_task.py, update_task.py, verify_task_closure.py, extract_json.py, audit_artifact.py, re_audit_tasks.py, explain_task.py, auto_commit.sh, ralph_notify.py, ralph_tail.sh, update_memory.py, update_progress.py

## Templates
AGENTS_CODER.md, AGENTS_LEAD.md, AGENTS.md.template, ARCHITECTURE.md.template, tasks.json.template, progress.md.template

## Key Commands
./ralph.sh task <ID>        # run single task
./ralph.sh auto             # run all pending
./ralph.sh phase <PHASE>    # run phase
make test                   # full test suite
python3 scripts/update_task.py <ID> <status>
python3 scripts/next_task.py

## Codex Execution Model
- codex exec -s danger-full-access [prompt]
- Wrapped in gtimeout (macOS GNU coreutils)
- PID/PGID tracked for process management
- Watchdog monitors output file activity
- Timeout scales by complexity (simple=180s, moderate=420s, complex/critical=600s)
- MAX_CODEX_RETRIES=3 with backoff

## Stack
Bash + Python 3.11 + Codex CLI + Telegram Bot API (urllib) + macOS

## Current Priority
Finish stabilization so Ralph works reliably for overnight unattended runs. Then use it to rapidly prototype actual products. No new features — only fix what blocks reliability. Speed over perfection. "Good enough" = go to sleep, wake up with most tasks done.

## Known Weak Spots
- Process teardown (bot vs shell kill paths can diverge)
- State recovery after crashes (ralph_state.json can lie)
- Lead review JSON parsing (model format drift causes false failures)
- Test suite is slow for per-task validation in auto mode
- auto_commit.sh scopes too broadly (git add -A)
- Bootstrap for new projects is incomplete

## How We Work
1. Codex executes a task → I paste log/diff/error
2. You diagnose what worked, what broke, root cause
3. You give: concrete fix, or better codex prompt, or decision (done/retry/blocked)
4. I run, paste result → iterate
5. Task solid → mark done → next

## Rules
- No new features until reliability is solid
- No rewrites — targeted fixes only
- Every fix needs a verification step
- If it works 80%+ of cases — mark done, move on
- Speed > perfection
- Respond in the same language as my message