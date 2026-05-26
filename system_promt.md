## Context
Ralph — project-agnostic AI execution layer with an installed CLI. It still
uses the bash orchestrator and Telegram bot as important runtime/control
layers, but they are not the whole product. Ralph now ships as a repo-local
and installable operator surface for driving AI-assisted software delivery.

## What Ralph Does
1. Takes tasks.json with a project plan (phases, priorities, dependencies)
2. Exposes installed CLI commands for operators and repo bootstrap
3. Runs tasks automatically through the shell/runtime path when requested
4. For each task: builds prompt → runs Codex CLI (coder) → runtime Tester
   phase → Codex CLI (lead review) → closure verification → final commit/status
   handling → next task
5. Handles failures: timeout, watchdog, retry with backoff, skip and alert
6. Developer controls and monitors via CLI and Telegram bot
7. Produces working committed code with audit trail
8. Relies on manual/operator-guided planning today; Ralph executes `tasks.json`
   and does not yet implement automatic project analysis or task generation

## Architecture
CLI / Telegram → ralph_bot.py / src/ralph/cli.py → ralph.sh → codex exec (coder) → Tester
                                                                          ↓ TESTER_REPORT
                                                                     codex exec (lead)
                                                                          ↓ approve/fix/alert
                                                                     Verifier → Finalizer

## Core Files
- src/ralph/cli.py — installed CLI entrypoint and operator command surface
- src/ralph/resources/ralph.sh — packaged runtime shell and helper resources
- ralph.sh — repo runtime shell kept in parity with packaged runtime behavior
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
- ralph status
- ralph doctor
- ralph verify
- ralph init
- ralph next
- ralph explain
- ralph groom
- ralph log
- ralph tail
- ralph task <ID>
- ralph auto --safe
- ralph bot

## Codex Execution Model
- codex exec -s danger-full-access [prompt]
- Wrapped in gtimeout (macOS GNU coreutils)
- PID/PGID tracked for process management
- Watchdog monitors output file activity
- Timeout scales by complexity (simple=180s, moderate=420s, complex/critical=600s)
- MAX_CODEX_RETRIES=3 with backoff

## Tester Phase
- Coder and Lead do not own the main test phase.
- The runtime Tester phase runs the configured project test command and is the authoritative source of test truth for the task.
- Tester emits `TESTER_START`, `TESTER_DONE`, `TESTER_TIMEOUT`, and `TESTER_REPORT`.
- `tester_timeout` means the configured test command exceeded the allowed runtime.
- `tester_failed` means the configured test command completed with a failing result.
- Lead should review the diff, acceptance criteria, and tester report. Lead should not require full-suite evidence unless the task explicitly asks for it.

## Test Profiles
- Auto and phase mode should prefer the fast or overnight profile configured in `test_cmd_fast`.
- The overnight profile is intentionally smaller than the full suite and should avoid heavy integration coverage by default.
- Explicit verify or manual full checks may use the full test command such as `make test`.
- Tasks that explicitly require integration scenarios or full-suite baselines should not rely on overnight-smoke evidence alone.

## Environment
- macOS, zsh, GNU coreutils via brew (gtimeout, gdate)
- Python 3.11+ baseline
- Git: commit after each verified task, branch: dev/auto-pilot

## Current Priority
Release/distribution polish for the installed CLI packaging stage.
Priority order:
1. pipx install UX
2. package smoke coverage
3. GitHub push and CI reliability
4. bootstrap and kickoff flow
5. first manual real-project pilot

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
- Install/distribution polish before PyPI is still in progress
- pipx-first UX and packaged resource ergonomics need ongoing tightening
- GitHub package smoke can be blocked by account billing constraints
- Bootstrap and kickoff flow still trails the CLI/operator surface
- Hosted cross-platform CI proof is still missing
- Automatic project analysis and task generation are still future workflows

## Pending Tasks
- R25 packaging/distribution hardening for the installed CLI path
- R26 governance, packaging smoke, and bootstrap/kickoff alignment

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
R25/R26-XX: <what changed and why>

## Rules
- Keep repo shell and packaged shell behavior aligned
- Prefer pipx/GitHub install clarity over premature PyPI assumptions
- No rewrites — targeted fixes only
- For packaging work, assume Python 3.11+ and do not trust local python3 blindly
- Do not claim native Windows support, hosted CI green status, or automatic `ralph analyze` / `ralph propose-tasks` workflows
- Speed > perfection
- Respond in the same language as my message

## Response Format
Root cause first → exact fix → verify command. No preamble, no theory 
unless asked.
