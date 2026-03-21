# Recent Task History

### R12-05: Bot: implement bounded single-shot backend for /ask
- Files: scripts/ralph_bot.py,src/ralph/resources/scripts/ralph_bot.py,tests/test_bot_commands.py
- Result: approved
- Notes: Добавь и покажи минимальную реализацию явного repo-local backend path, который cmd_ask вызывает для непустого /ask <question> и который возвращает один bounded single-shot ответ без истории; вместе с этим добавь один regression test, проверяющий успешный non-empty /ask response path через этот backend.
- Time: 2026-03-21T19:14:08Z

### R12-04: Bot: route /ask and add dedicated cmd_ask usage handler
- Files: scripts/ralph_bot.py,src/ralph/resources/scripts/ralph_bot.py,tests/test_bot_commands.py
- Result: approved
- Notes: 
- Time: 2026-03-21T17:15:05Z

### R12-02: Minimal scripts/run_eval.py skeleton for offline eval fixtures
- Files: .ralph/audit/R11-04.json,scripts/run_eval.py,src/ralph/resources/scripts/run_eval.py,tests/fixtures/basic_eval_fixture.json,tests/test_run_eval.py
- Result: approved
- Notes: 
- Time: 2026-03-20T18:05:09Z

### R11-04: Preserve clean final tail and truthful state after successful one-task completion
- Files: .ralph/audit/R11-03.json,ralph.sh,src/ralph/resources/ralph.sh,tests/test_integration.py
- Result: approved
- Notes: 
- Time: 2026-03-20T04:01:41Z

### R11-03: Exit cleanly after successful one-task final status reporting
- Files: .ralph/audit/R11-02.json,ralph.sh,src/ralph/resources/ralph.sh,tests/test_integration.py
- Result: approved
- Notes: 
- Time: 2026-03-20T02:51:28Z
