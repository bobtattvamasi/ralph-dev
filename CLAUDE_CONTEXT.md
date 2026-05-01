# CLAUDE_CONTEXT

## 1. Project State
- Tasks by status: blocked=3, done=77, false_positive=27, pending=20, verified_done=66
- Last 3 completed tasks (by tasks.json order):
  - F04: Enable async support for bot tests by adding pytest-asyncio
  - F05: Fix test timeouts and hangs in phase/benchmark tests
  - F06: Improve Telegram notifications and logging for better debug visibility
- Current blocked tasks:
  - R19-03: Enforce target_files limit of 3 — [PARKING LOT] In next_task.py and task validation, warn or auto-split tasks with more than 3 target_files. Large scope tasks consistently fail in single codex exec.
  - R19-04: Ban inline Python heredoc >10 lines in bash — [PARKING LOT] Add a post-coder check: if any .sh file contains a Python heredoc (<<PY or <<PYTHON) longer than 10 lines, flag as scope anomaly and require extraction to scripts/. This prevents bash parse errors from embedded Python.
  - R20-03: Harden Lead JSON parsing — single authoritative source — Always prefer review file. Simplify extraction to: decision, quality_score, issues. Fallback on malformed JSON = skip (not fix). Test against archived lead outputs.
- ralph_state.json:
  - source: absent
  - is_running: false
  - current_task: null
  - last_update: unavailable

## 2. Recent Failures
- Most recent log file: logs/ralph_2026-04-27.log
- Last 10 error/failure entries:
  - 13:48:34 | T01 | timeout | [CODEX] result = subprocess.run([str(RALPH_SH), 'task', 'T01'], cwd=project_dir, env=env, capture_output=True, text=True, timeout=45)
  - 13:48:53 | - | missing_dependency | [CODEX] ModuleNotFoundError: No module named 'dotenv'
  - 13:49:10 | T01 | timeout | [CODEX] result = subprocess.run([str(RALPH_SH), 'task', 'T01'], cwd=project_dir, env=env, capture_output=True, text=True, timeout=45)
  - 13:50:50 | - | timeout | [CODEX]         timeout=45,
  - 13:50:51 | - | timeout | [CODEX]         timeout=45,
  - 13:51:20 | - | failure | [CODEX]         log "⚠️ Failed to consume operator comment from ralph_control.json"
  - 13:53:00 | T01 | timeout | [CODEX] result = subprocess.run([str(RALPH_SH), 'task', 'T01'], cwd=project_dir, env=env, capture_output=True, text=True, timeout=45)
  - 14:16:30 | - | failure | ❌ Self-heal failed. make test is still broken.
  - 14:16:30 | - | traceback | ⚠️ Notification helper exited with error: Traceback (most recent call last):
  - 22:08:41 | - | recovery | ⚠️ Auto-recovery: previous non-idle state detected ('blocked')
- Repeating patterns:
  - Notification/helper dependency failures mention missing python-dotenv
  - Repeated timeout-related entries around task/test execution
  - Recovery path is active after prior non-idle state
  - Pre-task/self-heal failures still surface in logs

## 3. Process & Reliability Issues
- ps aux / codex snapshot:
    PID  PPID  PGID STAT     ELAPSED COMMAND
  56706 55560 56706 S+   03-23:12:33 node /usr/local/bin/codex --yolo
  56707 56706 56706 R+   03-23:12:33 /usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-x64/vendor/x86_64-apple-darwin/codex/codex --yolo
  12671 10958 12671 S+      22:56:35 node /usr/local/bin/codex --yolo
  12675 12671 12671 S+      22:56:35 /usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-x64/vendor/x86_64-apple-darwin/codex/codex --yolo
- Observed codex processes: two active codex process groups are currently present; report does not infer ownership beyond PID/PPID/PGID.
- ralph_control.json current state:
  - file absent
- Last 10 ralph_alerts.log entries:
  - четверг, 12 марта 2026 г. 22:37:44 (+07): Tests broken before start. Fix manually.
  - пятница, 13 марта 2026 г. 01:34:11 (+07): Tests broken before start. Fix manually.
  - пятница, 13 марта 2026 г. 01:40:59 (+07): Unknown issue
  - пятница, 13 марта 2026 г. 01:41:01 (+07): R3-01 failed after 2 retries
  - пятница, 13 марта 2026 г. 01:59:26 (+07): Tests broken before start. Fix manually.
  - пятница, 13 марта 2026 г. 02:04:47 (+07): Unknown issue
  - пятница, 13 марта 2026 г. 02:04:49 (+07): R3-01 failed after 2 retries
  - пятница, 13 марта 2026 г. 02:13:18 (+07): Tests broken before start. Fix manually.
  - пятница, 13 марта 2026 г. 02:17:37 (+07): Unknown issue
  - пятница, 13 марта 2026 г. 02:17:39 (+07): R3-01 failed after 2 retries

## 4. Code Health Snapshot
- ralph.sh
  - No TODO/FIXME/XXX markers found by ripgrep.
  - Hardcoded/retry timeout values visible at: ralph.sh:493 (`MAX_CODEX_RETRIES=3`), ralph.sh:2990 (`stale_timeout` default 300), ralph.sh:2992 (`poll_interval=5`), ralph.sh:3036 (`RALPH_WATCHDOG_TIMEOUT` default 300), ralph.sh:3069 (`gtimeout --kill-after=10`), ralph.sh:3976 / ralph.sh:3983 (pre-task timeouts).
  - Control/recovery fail-fast hot paths are around ralph.sh:1633 (`read_control_file`), ralph.sh:1664 (`apply_control_action_snapshot`), ralph.sh:2822 (`check_and_recover_state`), ralph.sh:3028 (`run_codex`).
- scripts/ralph_bot.py
  - No TODO/FIXME/XXX markers found by ripgrep.
  - File contains many broad exception handlers (`except Exception`) across command/recovery paths; examples surfaced by ripgrep at lines 870, 1137, 1157, 1533, 1706, 1734, 1756, 1817, 1887, 1962, 2055, 2357.
  - Bot crash/state handling hot functions from ripgrep: `reset_stale_state` (line 486), `terminate_tracked_processes` (line 1029), `cmd_stop` (line 1538), `watch_state` (line 2365).
- auto_commit.sh
  - Scoped staging is in place. Current staging loop uses `git add -A -- "$scope_path"` only for task scope paths emitted from `target_files` plus `.ralph/audit/<task>.json` and `audit_report.md` (scripts/auto_commit.sh lines 16-54 and 56-60).
- Lock files present:
  - progress.md.lock
  - ralph_control.json.lock
  - ralph_state.json.lock
  - tasks.json.lock

## 5. Test Coverage
- Command run: `make test 2>&1 | tail -30`
- Observed tail (bounded with timeout externally because the suite did not finish promptly):
```text
tests/test_bot_commands.py::test_watch_state_recovers_crashed_running_task PASSED [ 12%]
tests/test_bot_commands.py::test_watch_state_tears_down_tracked_processes_on_crash_recovery PASSED [ 12%]
tests/test_bot_commands.py::test_cmd_stop_force_kills_tracked_process_groups_and_is_idempotent PASSED [ 12%]
tests/test_bot_commands.py::test_cmd_start_auto_rejects_when_state_running PASSED [ 13%]
tests/test_bot_commands.py::test_cmd_start_auto_rejects_when_pid_file_is_alive PASSED [ 13%]
tests/test_bot_commands.py::test_cmd_start_auto_ignores_stale_pid_file PASSED [ 14%]
tests/test_bot_commands.py::test_read_state_returns_idle_for_broken_json PASSED [ 14%]
tests/test_bot_commands.py::test_reset_stale_state_resets_running_state_when_no_tracked_process_is_alive PASSED [ 15%]
tests/test_bot_commands.py::test_reset_stale_state_keeps_running_state_when_tracked_process_is_alive PASSED [ 15%]
tests/test_bot_helpers.py::TestLogTail::test_no_logs_dir PASSED          [ 15%]
tests/test_bot_helpers.py::TestLogTail::test_empty_logs_dir PASSED       [ 16%]
tests/test_bot_helpers.py::TestLogTail::test_reads_latest_log PASSED     [ 16%]
tests/test_bot_helpers.py::TestLogTail::test_log_tail_limit PASSED       [ 17%]
tests/test_bot_helpers.py::TestCostParsing::test_parse_tokens_field PASSED [ 17%]
tests/test_bot_helpers.py::TestCostParsing::test_parse_tokens_with_comma PASSED [ 17%]
tests/test_bot_helpers.py::TestCostParsing::test_no_tokens_in_line PASSED [ 18%]
tests/test_bot_helpers.py::TestProgressFile::test_read_progress PASSED   [ 18%]
tests/test_bot_helpers.py::TestProgressFile::test_missing_progress PASSED [ 19%]
tests/test_bot_reload.py::test_apply_hot_reload_swaps_handlers PASSED    [ 19%]
tests/test_bot_reload.py::test_apply_hot_reload_rejects_incomplete_module PASSED [ 20%]
tests/test_bot_reload.py::test_cmd_reload_reports_failure_and_keeps_existing_handlers PASSED [ 20%]
tests/test_bot_reload.py::test_handle_update_dispatches_reload PASSED    [ 20%]
tests/test_bot_reload.py::test_handle_update_dispatches_exit PASSED      [ 21%]
tests/test_bot_reload.py::test_handle_update_logs_command_entry_exit_and_send_count PASSED [ 21%]
tests/test_bot_reload.py::test_handle_update_logs_exception_with_traceback PASSED [ 22%]
tests/test_bot_reload.py::test_poll_updates_logs_traceback_for_update_handler_errors PASSED [ 22%]
tests/test_bot_stats.py::test_summarize_metrics_aggregates_expected_fields PASSED [ 22%]
tests/test_bot_stats.py::test_cmd_stats_reports_aggregated_metrics PASSED [ 23%]
tests/test_bot_stats.py::test_cmd_stats_handles_missing_metrics_file PASSED [ 23%]
tests/test_cli_packaging.py::test_cli_entrypoint_install_and_core_commands make: *** [test] Terminated: 15
```
- Pass/fail summary from this run: no final pytest summary was emitted in the captured tail; the run ended with `make: *** [test] Terminated: 15` during `tests/test_cli_packaging.py::test_cli_entrypoint_install_and_core_commands`.
- Skipped/flaky tests visible in captured tail: none visible in the tail snippet.

## 6. What's Blocking Auto Mode
- Missing Python dependency in notification path is visible in the latest log: `ModuleNotFoundError: No module named 'dotenv'` at 13:48:53 and again around 14:16:30 after a notification helper traceback. This shows helper failures in an unattended run path.
- Latest log still records `❌ Self-heal failed. make test is still broken.` at 14:16:30 in `logs/ralph_2026-04-27.log`, which means pre-task/self-heal can still stop progress before task execution.
- No current `ralph_state.json` or `.ralph_state.json` is present, while lock files remain (`progress.md.lock`, `ralph_control.json.lock`, `ralph_state.json.lock`, `tasks.json.lock`). This leaves no current runtime state file to reconcile with the locks.
- Active codex process groups are currently present in `ps` output (PGID 56706 and PGID 12671) without a current `ralph_state.json` file, so runtime process state and persisted state are not aligned in the working tree snapshot used for this report.
- `make test` did not complete promptly and the captured run terminated during `tests/test_cli_packaging.py::test_cli_entrypoint_install_and_core_commands`, so current full-suite stability for unattended auto mode is not demonstrated by the requested test command.
