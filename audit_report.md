# Test Coverage Audit

## Covered ✅
- `duplicate pid-guard блокирует второй запуск`
  - `tests/test_integration.py::test_ralph_blocks_duplicate_launch_with_pid_guard`
- `timeout -> retry, не зависает`
  - `tests/test_integration.py::test_ralph_timeout_cleans_up_orphan_children`
  - `tests/test_integration.py::test_ralph_watchdog_kills_stale_codex_and_retries`
- `rate limit (429) -> pause RATE_LIMIT_PAUSE, не crash`
  - `tests/test_integration.py::test_ralph_pauses_and_retries_on_rate_limit`
- `git commit не зависает`
  - косвенно покрыто интеграционными тестами успешного прохода, где коммиты выполняются без интерактива:
  - `tests/test_integration.py::test_ralph_marks_task_done_on_success`
  - `tests/test_integration.py::test_ralph_retries_after_fix_and_then_marks_done`
- `TASK_TIMEOUT берётся из complexity когда нет явного timeout`
  - `tests/test_integration.py::test_ralph_uses_complexity_default_timeout_when_timeout_missing`
- `watch_state: crash recovery (R1-10)`
  - `tests/test_bot_commands.py::test_watch_state_recovers_crashed_running_task`
- `/auto не запускает второй ralph если уже running`
  - `tests/test_bot_commands.py::test_cmd_start_auto_rejects_when_state_running`
- `/skip пропускает задачу без краша`
  - `tests/test_integration.py::test_ralph_marks_task_skipped_on_skip_control`
- `ralph_state.json корректно читается при битом JSON`
  - `tests/test_bot_commands.py::test_read_state_returns_idle_for_broken_json`
- `ralph_control.json читается при отсутствии файла`
  - косвенно покрыто через штатные `cmd_*` и integration runs без control file:
  - `tests/test_integration.py::test_ralph_marks_task_done_on_success`
- `полный цикл pending -> running -> approved -> done`
  - `tests/test_integration.py::test_ralph_marks_task_done_on_success`
- `полный цикл pending -> running -> fix -> retry -> approved -> done`
  - `tests/test_integration.py::test_ralph_retries_after_fix_and_then_marks_done`

## Missing ❌
- `circuit breaker -> после N failures останавливается`
  - явного теста нет
- `/stop сигнал -> ralph останавливается чисто, state=idle`
  - есть только `state=stopped` для orchestrator:
  - `tests/test_integration.py::test_ralph_stops_when_stop_control_is_present`
- `watch_state: двойное уведомление не отправляется`
  - теста на dedup `last_status/last_task` нет
- `/stop корректно сбрасывает state в idle`
  - unit-теста `cmd_stop(force=False/True)` нет
- `/redo сбрасывает задачу в pending`
  - unit-теста `cmd_redo()` нет
- `Telegram poll не падает при сетевой ошибке`
  - нет теста на exception path в `poll_updates()`
- `tasks.json: update_task.py идемпотентен`
  - helper не тестируется напрямую

## Fragile ⚠️
- `git commit не зависает`
  - покрытие только косвенное через integration success path; нет теста, который прямо валидирует `GIT_EDITOR=true`
- `ralph_control.json читается при отсутствии файла`
  - тоже косвенное покрытие, нет unit-теста на `read_control_file()`
- `duplicate pid-guard`
  - интеграционный тест зависит от тайминга и живого фонового процесса, хотя сделан максимально коротким
- `fix -> retry -> approve`
  - сценарий завязан на поведение мокнутого `codex`, а не на отдельный unit-тест decision-loop

## Recommended new tests
- `tests/test_integration.py::test_ralph_trips_circuit_breaker_after_consecutive_failures`
  - нужен после стабилизации текущего поведения circuit breaker относительно blocked-задач
- `tests/test_bot_commands.py::test_cmd_stop_force_sets_idle_and_cleans_runtime`
- `tests/test_bot_commands.py::test_cmd_redo_resets_task_to_pending`
- `tests/test_bot_commands.py::test_watch_state_does_not_repeat_waiting_human_notification`
- `tests/test_bot_commands.py::test_poll_updates_survives_network_error_and_backs_off`
- `tests/test_state_helpers.py::test_read_control_file_missing_returns_continue`
- `tests/test_update_task.py::test_update_task_idempotent_for_same_status`
