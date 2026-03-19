# Session Notes - 2026-03-02

## What happened
- /auto mode tested end-to-end: 5/5 tasks completed successfully
- Fixed 3 critical hanging bugs in ralph.sh execution pipeline
- Root causes: tee PID loss, bash wait on background codex, cat blocking on open FD

## Current state
- ralph.sh: fully synchronous codex execution via gtimeout
- ralph_bot.py: UTF-8 safe log reading, safe /stop with child kill
- All 18 unit tests passing
- /auto successfully completes full task cycle

## Known limitations
- /tail shows stale file when codex is running synchronously (no live streaming)
- gtimeout required (brew install coreutils on macOS)

## Next steps
- Apply ralph to real project (geoceph.ai frontend)
- Add live progress streaming during codex exec
- Add /cost tracking per session

# Session Notes - 2026-03-03 (Planning)

## Research findings applied
- Perplexity analysis of multi-agent orchestration best practices (2025-2026)
- Key sources: Anthropic context engineering, Factory.ai, Nubank/Devin, Spotify agents, Amazon eval

## Decisions made
- Keep sequential pipeline (coder→lead), correct for our use case
- Add .ralph/memory/ system for cross-task context (highest ROI improvement)
- Add circuit breaker (3 failures → stop) and exponential backoff
- Add model routing: simple→codex-mini, complex→codex-max
- Add agent_suitable field for task classification
- Vector DB and parallel execution deferred to R4 (future)
- Magentic/group-chat patterns not needed at current scale

## Priority order for implementation
1. R1-14: Exponential backoff + rate limit detection (blocker for overnight runs)
2. R1-13: Circuit breaker (prevent runaway failures)
3. R3-08: Memory system (highest ROI for agent quality)
4. R3-09: Structured task summaries (feeds memory system)
5. R3-10: Model routing + complexity field (free optimization)
6. R2-01..R2-09: Bot UX improvements
7. R3-11: Agent-suitable classification
8. R4-05, R4-06: Vector DB, parallel (future)

## Current state
- 40-task wasteland calculator completed successfully
- 10-task polish batch completed
- /stop now properly resets state (fixed this session)
- Git safety (GIT_EDITOR=true) added to codex subshells
- Orphan PID cleanup on bot startup added
- Graceful stop with 30s timeout implemented

### 2026-03-12 12:58 UTC
Добавлен скрипт `scripts/auto_commit.sh` для автоматизации коммита через `codex exec`.
Скрипт сам собирает staged diff, запрашивает у Codex summary и Conventional Commit message, затем парсит JSON-ответ.
Перед коммитом он дописывает краткое описание с таймстампом в `SESSION_NOTES.md` и завершает `git commit` без открытия редактора.

### 2026-03-12 13:04 UTC
- Добавлен интеграционный тест `tests/test_integration.py` для сценариев запуска `ralph.sh`.
- Покрыты ключевые потоки: успешное завершение задачи, `skip` через control-файл и остановка по `stop`.
- В тестах поднимается изолированный fake-проект с mock-бинарями `codex` и `gtimeout`.
- В `tasks.json` задача R2-03 помечена как выполненная с `completed_at`.

### 2026-03-12 13:11 UTC
Добавлены команды Telegram-бота `/add` и `/rm` для управления задачами прямо в `tasks.json`. Вынесены отдельные функции чтения и сохранения `tasks.json` со стабильным форматированием. Обновлены help и роутинг команд бота. В `tasks.json` две задачи помечены как выполненные с `completed_at`.

### 2026-03-12 13:26 UTC
Добавлена поддержка паузы выполнения: `ralph.sh` теперь уходит в режим ожидания и корректно возобновляет работу по команде пользователя. В Telegram-бот добавлены команды `/pause` и `/resume`, а также обновлена справка. Задача `R1-05` в `tasks.json` помечена как выполненная с timestamp.

### 2026-03-12 13:31 UTC
Добавлена команда /limits в Telegram-боте для показа сегодняшних затрат по metrics.csv относительно дневного лимита $500. Команда считает число задач и суммарную стоимость за текущий день, обрабатывает отсутствие данных и ошибки чтения. Обновлена справка /help и роутинг команд. В tasks.json задача R2-06 отмечена как выполненная с датой завершения.

### 2026-03-12 13:36 UTC
README полностью переписан: проект теперь описан как project-agnostic AI orchestrator с ролями Coder/Tech Lead, архитектурой и ключевыми возможностями. Добавлены подробные разделы по установке, настройке Telegram, запуску, CLI/Telegram-командам, runtime/reliability-модели, логам и проверкам. Удалён устаревший файл system_promt.md с ручным контекстом проекта.

### 2026-03-12 14:08 UTC
Сделали параметры ретраев и watchdog настраиваемыми через переменные окружения. Упростили и усилили логику watchdog: корректное завершение stale-процессов, безопасная работа с PID и ожидание флага срабатывания. Добавили интеграционный тест на убийство зависшего Codex и повторные попытки. В tasks.json отметили задачу R1-07 выполненной и добавили новые roadmap-задачи для ролей агентов, risk gates, asset pipeline и bootstrap-команды.

### 2026-03-12 14:24 UTC
Усилена очистка зависших Codex-процессов: добавлено завершение process group, учтён `ralph_codex.pgid` и общий cleanup для timeout/watchdog/recovery. Переработан запуск `codex exec`: теперь PID/PGID сохраняются через Python-лаунчер, а timeout стал ретраиться с агрессивной зачисткой orphan-процессов. Исправлена обработка rate limit: состояние пишется корректнее, пауза стала настраиваемой и покрыта интеграционным тестом. В `tasks.json` две задачи помечены как выполненные с `completed_at`.

### 2026-03-12 14:53 UTC
Добавлена ролевая настройка агентов: Ralph теперь подхватывает отдельные инструкции для designer/journalist и учитывает `role`/`risk` в задачах. Усилен контроль high-risk задач: перед коммитом появился отдельный human approval gate с pause/skip/stop. Добавлена генерация контент-драфтов: новый `write_article.sh`, команда `/article` в Telegram-боте и сохранение статей в `BLOG_DRAFTS.md`.

### 2026-03-12 17:10 UTC
Обновили контур генерации статей в Telegram-боте: `/article` теперь умеет отдавать сегодняшнюю статью или принудительно генерировать новую, а парсинг секций стал гибче. Скрипт `write_article.sh` теперь возвращает сам текст статьи в stdout, чтобы бот мог сразу отправлять результат. Заодно поправили help-тексты команд и добавили пустые Telegram env-переменные в интеграционные тесты для стабильного запуска.

### 2026-03-12 18:32 UTC
Добавлен отдельный таймаут для lead-ревью и возможность разово переопределять таймаут через control-файл/Telegram-команду. Улучшена сборка prompt: контекст из AGENTS/архитектуры/памяти и релевантные сниппеты теперь подрезаются по лимитам, чтобы не раздувать запрос. В Telegram-бот добавлены команды /done и /timeout, а отправка сообщений стала безопаснее для HTML. Покрытие расширено тестами для новых команд и интеграционной проверкой инъекции и ограничения prompt-контекста.

### 2026-03-17 17:41 UTC
Добавлена минимальная расширенная модель статусов задач: `verified_done`, `partial`, `needs_human_review`, `false_positive`, с обновлением документации и валидации моделей. Ralph теперь помечает автоматически подтверждённые задачи как `verified_done`, учитывает этот статус в прогрессе, выборе следующих задач и timestamps. Добавлен скрипт и CLI-режим для консервативного re-audit завершённых задач, а в боте появились команды для просмотра audit/trust-отчётов. Тесты обновлены под новую семантику статусов и покрывают сценарии re-audit.

### 2026-03-17 18:14 UTC
Ужесточена переаудит-проверка команд: теперь учитываются алиасы хендлеров, явный роутинг, наличие команды в help-тексте и следы в тестах. Автоприменение вердиктов стало безопаснее: `partial` больше не меняет `tasks.json`, а только попадает в отчёт как пропущенный. В вывод добавлена сводка по результатам и отдельный блок Applied/Skipped. Тесты расширены под новые сценарии команд, summary и поведение apply-режима.

### 2026-03-19 07:07 UTC
Обновлён re-audit: при false_positive теперь удаляются устаревшие audit-артефакты, а уже согласованные задачи пропускаются без лишних изменений. Добавлены Pydantic-модели и новый verify_task_closure.py для проверки закрытия задач в packaged runtime. Пересобран audit_report.md и синхронизированы статусы/notes в tasks.json. Тесты расширены на packaging и новые сценарии re-audit.

### 2026-03-19 07:22 UTC
- В `/tasks` исправлен подсчёт выполненных задач: `verified_done` теперь считается завершённым статусом.
- Сохранены подсказки по зависимостям только для реально незакрытых блокеров, без ложных срабатываний.
- Обновлён `tasks.json`: задача помечена как `verified_done` с временем завершения и примечанием.
- Добавлены тесты на новый подсчёт и маршрутизацию команды `/tasks`.
