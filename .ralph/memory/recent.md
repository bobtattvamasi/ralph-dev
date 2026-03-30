# Recent Task History

### OPS-10: Fail-fast: block retry if coder output is identical to prior attempt
- Files: tests/test_integration.py
- Result: approved
- Notes: 
- Time: 2026-03-30T10:02:50Z

### OPS-09: Narrow: reduce coder prompt to <15k tokens for narrow tasks
- Files: .ralph/audit/OPS-09.json,ralph.sh,src/ralph/resources/ralph.sh
- Result: approved
- Notes: 
- Time: 2026-03-28T07:58:21Z

### OPS-04: Cleanup: remove orphan /tmp/ralph_coder_*.txt files on startup and after run
- Files: .ralph/audit/OPS-05.json,ralph.sh,src/ralph/resources/ralph.sh,system_promt.md,tests/test_integration.py
- Result: approved
- Notes: 
- Time: 2026-03-24T17:47:31Z

### OPS-03: Observability: stream codex output to ralph log in real time
- Files: ralph.sh,src/ralph/resources/ralph.sh,tests/test_integration.py
- Result: approved
- Notes: Доработай timeout/failure ветку в `run_codex()` так, чтобы перед логированием `TIMEOUT`/failure гарантированно завершался и flush-ился FIFO stream logger, а затем вызывался `archive_codex_output()` для сохранения полного вывода в `logs/codex_TASKID_N.txt`; добавь точечный regression test именно на этот сценарий.
- Time: 2026-03-23T16:16:45Z

### R12-05: Bot: implement bounded single-shot backend for /ask
- Files: scripts/ralph_bot.py,src/ralph/resources/scripts/ralph_bot.py,tests/test_bot_commands.py
- Result: approved
- Notes: Добавь и покажи минимальную реализацию явного repo-local backend path, который cmd_ask вызывает для непустого /ask <question> и который возвращает один bounded single-shot ответ без истории; вместе с этим добавь один regression test, проверяющий успешный non-empty /ask response path через этот backend.
- Time: 2026-03-21T19:14:08Z
