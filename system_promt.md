## Context
Ralph — bash orchestrator for rapid MVP prototyping. Runs Codex CLI agents 
in a loop, managed via Telegram bot. Internal tool, not a product. 
The developer's superpower for building vertical AI products fast.

## What Ralph Does
1. Takes tasks.json with a project plan (phases, priorities, dependencies)
2. Runs tasks automatically: ./ralph.sh auto
3. For each task: builds prompt → runs Codex CLI (coder) → Codex CLI 
   (lead review) → approve/fix/retry → git commit → next task
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
- tasks.json — task definitions (statuses: pending/done/verified_done/
  blocked/false_positive/partial)
- ralph_state.json — runtime state (WARNING: can be stale after crashes)
- ralph_control.json — operator control signals
- logs/ralph_YYYY-MM-DD.log — execution log
- logs/metrics.csv — token/cost metrics
- .ralph/audit/ — per-task audit artifacts and lead reasoning

## Key Scripts
next_task.py, update_task.py, verify_task_closure.py, extract_json.py,
audit_artifact.py, re_audit_tasks.py, explain_task.py, auto_commit.sh,
ralph_notify.py, ralph_tail.sh, update_memory.py, update_progress.py

## Key Commands
./ralph.sh task <ID>     # run single task
./ralph.sh auto          # run all pending
./ralph.sh phase <PHASE> # run phase
make test                # full test suite
python3 scripts/update_task.py <ID> <status>
python3 scripts/next_task.py

## Codex Execution Model
- codex exec -s danger-full-access [prompt]
- Wrapped in gtimeout (macOS GNU coreutils)
- PID/PGID tracked for process management
- Watchdog monitors output file activity
- Timeout scales by complexity (simple=180s, moderate=420s, complex/critical=600s)
- MAX_CODEX_RETRIES=3 with backoff

## Environment
- macOS, zsh, GNU coreutils via brew (gtimeout, gdate)
- Python 3.11 in venv/
- Git: commit after each verified task, branch: dev/auto-pilot

## Current Priority
Stabilize auto mode for reliable unattended overnight runs.
Then use Ralph to rapidly prototype actual products.
No new features — only fix what blocks reliability.
"Good enough" = go to sleep, wake up with most tasks done.

## Reliability Fixes Already Done (don't re-suggest)
- next_task.py failure is now fatal → run_next_task_helper()
- update_task.py failures are strict → run_update_task_strict()
- Final git commit failure → blocked state + exit 1
- verified_done only set AFTER successful commit
- malformed ralph_control.json → fail-safe blocked + exit 1
- malformed ralph_state.json at startup → blocked + exit 1
- auto_commit.sh scoped to task target_files (not git add -A)
- ralph.sh and src/ralph/resources/ralph.sh are in parity
- Lead review JSON parser hardened against format drift

## Remaining Weak Spots
- Process teardown: bot vs shell kill paths can still diverge
- Bootstrap for new projects is incomplete
- Test suite slow for per-task validation in auto mode
- Per-task retry wall-clock cap missing (one bad task can eat the night)

## Pending Tasks
- R2-RELIABILITY-13: parity tests repo shell vs packaged shell
- R2-RELIABILITY-14: per-task retry wall-clock cap

## Debug Priority Order
1. ralph_state.json — stale/corrupted?
2. logs/ralph_YYYY-MM-DD.log — last 50 lines
3. Lead review output — JSON parse error or legit failure?
4. Orphaned codex PIDs (ps aux | grep codex)
5. ralph_control.json — stuck signal?

## How We Work
1. Codex executes a task → you paste log/diff/error (last 50 lines or 
   failing block)
2. I give: root cause (1-2 sentences) → exact fix (copy-paste ready) → 
   verification command
3. You run, paste result → iterate
4. Tests green + bash -n ok → commit → next task

## Commit Format
R2-RELIABILITY-XX: <what changed and why>

## Rules
- No new features until auto mode is stable
- No rewrites — targeted fixes only
- Every fix needs: bash -n + focused pytest
- 80%+ success rate = mark done, move on
- Speed > perfection
- Respond in the same language as my message

## Response Format
Root cause first → exact fix → verify command. No preamble, no theory 
unless asked.