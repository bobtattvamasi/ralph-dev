                            Context: Ralph Dev
Ralph — bash orchestrator (ralph.sh) запускает Codex CLI агентов в цикле, управляется через Telegram бот.

Core files
ralph.sh (2970L) — main loop, prompt builder, codex runner, timeout/retry/watchdog
scripts/ralph_bot.py (1661L) — Telegram bot, все команды
tasks.json — задачи (phases R0–R12+, statuses: pending/done/verified_done/blocked/false_positive/partial)
ralph_state.json, ralph_control.json — runtime state
logs/ralph_YYYY-MM-DD.log — execution log
logs/metrics.csv — token/cost metrics
Scripts (scripts/)
next_task.py, update_task.py, verify_task_closure.py, extract_json.py, audit_artifact.py, re_audit_tasks.py, explain_task.py, models.py, bot_smoke_check.py, reopen_tasks.py, run_eval.py, manage_assets.py, auto_update.py, ralph_notify.py, ralph_tail.sh, update_memory.py, update_progress.py, write_article.sh, auto_commit.sh

Templates (templates/)
AGENTS_CODER.md, AGENTS_LEAD.md, AGENTS_JOURNALIST.md, AGENTS_DESIGNER.md, AGENTS.md.template, ARCHITECTURE.md.template, tasks.json.template, progress.md.template

Key commands
bash

./ralph.sh task <ID>        # run single task
./ralph.sh auto             # run all pending
./ralph.sh phase <PHASE>    # run phase
make test                   # python3 -m pytest tests/ -v (140 tests, ~5min)
python3 scripts/update_task.py <ID> --status verified_done
python3 scripts/explain_task.py <ID>
python3 scripts/next_task.py
Architecture

Telegram → ralph_bot.py → ralph.sh → codex exec (coder) → codex exec (lead)
                                           ↓ approve/fix/alert
                                      git commit → next task
Codex execution (run_codex in ralph.sh)
codex exec -s danger-full-access [prompt]
Wrapped in gtimeout --foreground (macOS, coreutils)
Launched via python3 subprocess with start_new_session=True
PID tracked in ralph_codex.pid, PGID in ralph_codex.pgid
Watchdog monitors output file activity (RALPH_WATCHDOG_TIMEOUT)
Timeout defaults: simple=180s, moderate=420s, complex/critical=600s
MAX_CODEX_RETRIES=3, backoff delays in CODEX_RETRY_DELAYS array
Stack
Bash + Python 3.11 + Codex CLI + Telegram Bot API (urllib) + macOS (gtimeout, kill_tree)

How I work with you
Paste error/log → you diagnose
You give sed/python fix or codex prompt
I run, paste result → iterate
Tasks planned → /auto overnight