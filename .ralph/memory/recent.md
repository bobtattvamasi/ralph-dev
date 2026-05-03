# Recent Task History

### R22-03: Fast test gate — pytest -x -q вместо make test в auto mode
- Files: Makefile,ralph.sh,tests/test_ralph_shell_helpers.py
- Result: approved
- Notes: 
- Time: 2026-05-03T17:14:53Z

### R19-02: Bash syntax gate before test run
- Files: ralph.sh,src/ralph/resources/ralph.sh
- Result: approved
- Notes: Fix the failing `ralph.sh` phase/task-mode regression so the full `make test` suite passes again, then rerun verification; this task cannot be approved while the current branch still fails those existing integration tests.
- Time: 2026-04-10T17:49:39Z

### R13-07: Consolidate runtime constants and gate destructive rollback
- Files: ralph.sh,reports/chrome_extension_readiness.md,scripts/ralph_bot.py,scripts/ralph_common.py,scripts/ralph_notify.py,src/ralph/resources/ralph.sh,src/ralph/resources/scripts/ralph_bot.py,src/ralph/resources/scripts/ralph_common.py,src/ralph/resources/scripts/ralph_notify.py,tests/test_bot_commands.py,tests/test_integration.py
- Result: approved
- Notes: Исправь сборку crash rollback command в одном месте: либо храни в `CRASH_ROLLBACK_COMMANDS` только git subcommands/args (`('reset','HEAD','--','.')`, `('checkout','--','.')`), либо перестань добавлять внешний `git` в `scripts/ralph_bot.py`. После этого destructive rollback будет и gated, и рабочим.
- Time: 2026-03-31T10:50:01Z

### R13-04: Harden silent error handling and malformed JSON paths
- Files: ralph.sh,scripts/explain_task.py,scripts/next_task.py,scripts/ralph_bot.py,scripts/ralph_common.py,scripts/ralph_notify.py,scripts/reopen_tasks.py,scripts/run_benchmark.py,scripts/update_task.py,src/ralph/resources/scripts/explain_task.py,src/ralph/resources/scripts/next_task.py,src/ralph/resources/scripts/ralph_bot.py,src/ralph/resources/scripts/ralph_common.py,src/ralph/resources/scripts/ralph_notify.py,src/ralph/resources/scripts/reopen_tasks.py,src/ralph/resources/scripts/run_benchmark.py,src/ralph/resources/scripts/update_task.py
- Result: approved
- Notes: Sync the same hardening changes into the packaged copies under `src/ralph/resources/scripts/` so installed/runtime execution gets the same typed logging and structured malformed-JSON errors as the root scripts.
- Time: 2026-03-31T07:57:20Z

### R13-06: Remove or wire up dead shell helpers
- Files: ralph.sh,src/ralph/resources/ralph.sh
- Result: approved
- Notes: 
- Time: 2026-03-31T05:52:15Z
