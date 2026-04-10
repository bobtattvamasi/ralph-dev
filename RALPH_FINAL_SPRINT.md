# Ralph Final Sprint — 1 Week to "Good Enough"

## Current State Summary
- Total tests: 211 collected, Passing: 210, Failing: 0
- Tasks in tasks.json: 172 total (131 done, 20 pending, 0 blocked, 21 other)
- Critical issues found: 4
- Friction issues found: 5

Notes:
- `tasks.json` has no `blocked` items, but the runtime is not clean: `ralph_state.json` still says `running` on `R19-04` with step `blocked`, while `ralph_control.json` is stale and says `continue`.
- Recent metrics show test phases taking 765-939 seconds per task, which makes overnight throughput far worse than the stated goal.
- Full suite is large and slow. During the audit, targeted shell-helper tests passed (`8 passed in 12.20s`), and the slow benchmark integration test passed, but took `74.41s` for a single test.

## Day 1-2: Fix Blockers (🔴)
### BLOCKER-1: Force-stop can leave Codex descendants alive
- **What breaks:** `/stop now` kills tracked PIDs, but not the full process group Ralph itself creates. If the main Codex process forks or PGID differs, the bot can say "killed" while real worker processes keep running in the background.
- **Where:** `scripts/ralph_bot.py:1448-1489`, `ralph.sh:2469-2505`, `ralph.sh:2629-2659`
- **Fix:** Make the bot stop path use the same PGID-aware termination model as `ralph.sh`. Read `ralph_codex.pgid`, kill the process group first, then clean residual PIDs. Remove duplicate kill logic between bot and shell so one path owns process teardown.
- **Verify:** Start `./ralph.sh auto`, force `/stop now`, then confirm no `ralph_codex.pid`, no `ralph_codex.pgid`, and no live Codex descendants via `pgrep`.
- **Effort:** M

### BLOCKER-2: State can lie after crashes or interrupted runs
- **What breaks:** Operator-facing state is inconsistent. `ralph_state.json` can remain `running/blocked` long after the process is gone; bot reset logic only fixes this in some code paths. That means `/status`, `/auto`, `/switch`, and human decisions can act on stale state.
- **Where:** `ralph_state.json`, `ralph_control.json`, `scripts/ralph_bot.py:448-497`, `scripts/ralph_bot.py:1413-1427`
- **Fix:** Centralize stale-state reconciliation and run it on bot startup, `/status`, `/auto`, and `/switch`. Treat missing or dead PID as authoritative and reset state/control consistently.
- **Verify:** Kill Ralph ungracefully, then run `/status` and `/auto`. Status must self-heal to idle and auto mode must start without manual file cleanup.
- **Effort:** M

### BLOCKER-3: Model-output parsing is too brittle for unattended runs
- **What breaks:** Tech Lead review parsing fail-closes on format drift, mismatch between stdout and review file, or malformed JSON. That is safer than silent corruption, but in practice it converts model formatting noise into false task failures and burns retries.
- **Where:** `ralph.sh:2788-2837`, `scripts/extract_json.py`, `templates/AGENTS_LEAD.md:14-35`
- **Fix:** Tighten the contract in one place: always prefer one authoritative source, simplify the wrapper format, and harden extraction around `decision`, `quality_score`, and issue fields only. Stop comparing two partially independent JSON sources unless both are intentionally produced.
- **Verify:** Replay archived lead outputs from `.ralph/audit/lead_reasoning_*.txt` and confirm the parser returns one stable decision object for each file without spurious `fix` fallbacks.
- **Effort:** M

### BLOCKER-4: Auto mode is too slow to be useful overnight
- **What breaks:** Ralph runs the configured project test command after every coder attempt. In practice, recent logs show 12-15 minute test gates per task, and even one benchmark integration test takes 74s. That makes `auto` throughput too low for "go to sleep and wake up with 70-80% of simple tasks done."
- **Where:** `ralph.sh:229-270`, `ralph.sh:4204-4208`, `logs/task_phase_timings.csv`, `tests/test_integration.py::test_ralph_benchmark_reports_auto_vs_manual_breakdown`
- **Fix:** Separate per-task fast validation from full-suite confidence. Keep a deterministic fast gate for auto mode, and reserve the full suite for preflight, milestone checkpoints, or explicit manual verification. Do this through the existing project test command/config path, not by inventing a new subsystem.
- **Verify:** Run `./ralph.sh auto` on a queue of 10 simple/moderate tasks and confirm average per-task test phase stays under 2 minutes.
- **Effort:** L

## Day 3-4: Reduce Friction (🟡)
### FRICTION-1: Auto-commit is unsafe in a dirty repo
- **What breaks:** `auto_commit.sh` blindly runs `git add -A`, sends the entire staged diff to Codex, regex-parses a JSON blob out of model text, and commits whatever comes back. In a dirty tree, unrelated changes can get swept into the commit.
- **Where:** `scripts/auto_commit.sh:10-18`, `scripts/auto_commit.sh:39-69`, `scripts/auto_commit.sh:82-83`
- **Fix:** Scope commit candidates to task-owned files or current staged set only, fail fast on mixed unrelated changes, and stop using greedy regex extraction when strict JSON parsing fails.
- **Verify:** Create a dirty worktree with unrelated files, run auto-commit, and confirm it refuses to commit unrelated changes.
- **Effort:** M

### FRICTION-2: Bot command surface is broader than what is actually trustworthy
- **What breaks:** The bot exposes many commands, but the core "sleep at night" contract only depends on a small reliable subset. Some command naming is inconsistent (`/trust_report` instead of a simpler `/trust`), and the bot surface is larger than the hardened runtime beneath it.
- **Where:** `scripts/ralph_bot.py:2068-2101`, `scripts/ralph_bot.py:2139-2249`
- **Fix:** Reduce the default supported command set operationally to `/status`, `/tasks`, `/auto`, `/stop`, `/pause`, `/resume`, `/log`, `/tail`, `/diff`. Mark everything else as secondary until the core path is stable.
- **Verify:** Dry-run each core command end-to-end against a live local project and confirm the help text matches what is actually supported.
- **Effort:** S

### FRICTION-3: Logs and metrics are noisy, but not decisive
- **What breaks:** Ralph logs a lot, but operators still have to hunt for the real reason a task failed. Metrics capture cost and timing, but not enough of the trust/failure surface to diagnose overnight runs quickly.
- **Where:** `ralph.sh:605-742`, `logs/metrics.csv`, `logs/task_phase_timings.csv`
- **Fix:** Add one canonical failure summary line per task with reason, retry count, verifier result, lead decision, and trust score. Keep raw detail in existing logs, but make the summary grep-friendly.
- **Verify:** After 5 mixed tasks, one `rg 'TASK_(DONE|FAIL)' logs/ralph_*.log` should explain the night without reading the full file.
- **Effort:** M

### FRICTION-4: Bootstrap templates do not create a runnable new project
- **What breaks:** `ralph-init.sh` copies docs and task scaffolding, but it does not create a runnable test command, project config, git repo, or any bootstrap guide for a fresh MVP repo. That means "new project in under 30 minutes" is not currently real.
- **Where:** `ralph-init.sh:17-87`, `templates/tasks.json.template:1-26`, `templates/ARCHITECTURE.md.template`, `templates/AGENTS.md.template`
- **Fix:** Tighten the init flow around the minimal contract Ralph actually needs: docs, task file, test command, and operator checklist. Do not expand features; just make the bootstrap honest and complete.
- **Verify:** Initialize an empty temp repo, follow only repo docs, and get to a valid `./ralph.sh status` plus runnable test command without ad-hoc manual fixes.
- **Effort:** M

### FRICTION-5: GNU `gtimeout` and shell-tool assumptions are implicit
- **What breaks:** `run_codex()` hard-depends on `gtimeout`. If the host machine is missing GNU coreutils or differs from the current dev box, Codex execution fails before the queue even starts.
- **Where:** `ralph.sh:2551-2560`
- **Fix:** Add an explicit startup check with a hard error message, or fall back to `timeout` when available. The important part is to fail immediately and clearly, not halfway into an overnight run.
- **Verify:** Run on a machine without `gtimeout` and confirm Ralph exits with one actionable prerequisite error instead of a broken queue.
- **Effort:** S

## Day 5: Stabilize & Verify
- [ ] All tests pass (`make test`)
- [ ] `./ralph.sh auto` runs 10 tasks without manual intervention
- [ ] Telegram bot responds to: /status, /task, /auto, /stop, /pause, /resume
- [ ] Auto-commit works for completed tasks
- [ ] Watchdog correctly kills stuck processes
- [ ] Retry logic handles 3 consecutive failures gracefully

## Day 6-7: Template for New Projects
- [ ] Create `templates/new_project_bootstrap.md` — step-by-step guide
- [ ] Verify: can start a brand new project with `./ralph.sh` in under 30 minutes
- [ ] Document known limitations and workarounds

## Parking Lot (🟢 skip for now)
- Multi-project registry polish: it can wait because a single-project overnight auto loop must be trustworthy first.
- Trust-score sophistication: current scoring is useful enough for telemetry once the audit schema stops drifting.
- More Telegram commands: adding `/dashboard`, `/kickoff`, archival, and similar surface area now would widen the failure surface before the core runtime is stable.
- Packaging polish: `ralph` CLI packaging exists already; shipping a cleaner package can wait until the runtime and bot path are boringly reliable.
