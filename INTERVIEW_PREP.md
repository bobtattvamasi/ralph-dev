# Ralph Dev — Interview Prep

## 1. Что делает система
Ralph — это AI-оркестратор для разработки поверх любого репозитория с `tasks.json`. Он берёт задачу из backlog, запускает AI-исполнителя и AI-ревьюера, проверяет результат через trust layer и даёт оператору Telegram-пульт для запуска, остановки, аудита и контроля состояния.

## 2. Architecture overview

### Основные компоненты

| Файл | Компонент | Ответственность |
|---|---|---|
| `ralph.sh` | Главный оркестратор | Выбор задачи, запуск Coder/Lead, retry/backoff, smoke test, self-heal, state machine, audit, commits |
| `ralph-init.sh` | Инициализация проекта | Копирует шаблоны, создаёт `tasks.json`, `.env`, `.ralph/memory`, обновляет `.gitignore` |
| `scripts/ralph_bot.py` | Telegram bot/control plane | Команды `/start`, `/phase`, `/auto`, `/stop`, `/audit`, `/ask`, `/stats`, управление `ralph_control.json` |
| `scripts/next_task.py` | Scheduler helper | Выбирает следующий runnable `pending` task с учётом dependency graph |
| `scripts/update_task.py` | Backlog writer | Меняет статус задачи в `tasks.json` |
| `scripts/update_progress.py` | Progress log writer | Апдейтит `progress.md` |
| `scripts/update_memory.py` | Memory writer | Обновляет `.ralph/memory/recent.md` после успешного таска |
| `scripts/verify_task_closure.py` | Trust gate | Проверяет, достаточно ли repo evidence для честного closure |
| `scripts/audit_artifact.py` | Audit layer | Пишет и читает `.ralph/audit/<TASK>.json`, строит trust report |
| `scripts/re_audit_tasks.py` | Repo-truth reassessment | Переоценивает backlog по текущему состоянию репо |
| `scripts/reopen_tasks.py` | Operator repair helper | Controlled reopen/reclassify task statuses |
| `scripts/explain_task.py` | Operator forensic helper | Показывает runnable state, причины non-runnable, suggested next action |
| `scripts/manage_assets.py` | Async asset workflow | Валидирует и синхронизирует `assets_manifest.json` |
| `scripts/extract_json.py` | Review parser | Достаёт authoritative JSON review из lead output |
| `scripts/models.py` | Pydantic models | `RalphState`, `TaskRecord`, `LeadReview` |
| `scripts/ralph_notify.py` | Notification adapter | Шлёт уведомления в Telegram |
| `scripts/run_eval.py` | Offline eval helper | Минимальный fixture-based eval script |
| `src/ralph/cli.py` | Packaged CLI | Команды `ralph init/auto/status/bot` через package resources |
| `src/ralph/resources/...` | Packaged mirror | Ресурсная копия shell/python/template surface для installable CLI |
| `templates/*` | Bootstrap templates | Стартовые `AGENTS`, `ARCHITECTURE`, `MEMORY_SYSTEM`, prompt templates, memory templates |
| `tests/*` | Regression suite | Integration, bot, trust layer, packaging, operator helpers, assets, eval |
| `docs/TRUST_LAYER.md` | Trust model doc | Граница между runtime success и verified success |
| `docs/AUDIT_WORKFLOW.md` | Audit workflow doc | Как оператор читает truth layers |
| `docs/STATUS_MODEL.md` | Status semantics | `pending`, `verified_done`, `partial`, `false_positive`, и т.д. |
| `docs/TASK_VERIFICATION_POLICY.md` | Verification policy | Минимальная task-aware verification matrix |
| `tasks.json` | Backlog truth | Задачи, статусы, deps, timeout, complexity, risk |
| `ralph_state.json` | Runtime truth | Текущее состояние рантайма |
| `ralph_control.json` | Control plane file | Stop/pause/resume/comment/skip actions от оператора |
| `logs/metrics.csv` | Runtime metrics | duration, attempts, quality, runtime_success, verified_success |
| `.ralph/audit/*.json` | Latest run truth | Артефакт каждого task run |

### ASCII схема потока

```text
Operator / Telegram
        |
        v
scripts/ralph_bot.py
        |
        | writes control / starts shell
        v
  ralph_control.json ----> ralph.sh <---- tasks.json
                              |
                              | smoke test / recovery
                              v
                         select task
                              |
                              v
                    build coder prompt
                              |
                              v
                   codex exec (Coder agent)
                              |
                              | git diff + make test
                              v
                   codex exec (Tech Lead)
                              |
                   +----------+----------+
                   |                     |
                 approve                fix/alert
                   |                     |
                   v                     v
      verify_task_closure.py         retry / block / notify
                   |
                   v
      update_task.py / update_progress.py / update_memory.py
                   |
                   v
          audit_artifact.py + metrics.csv + final git commit
```

## 3. Tech stack — что используется и почему

- `Bash`
  - основа orchestration в `ralph.sh` и `ralph-init.sh`
  - выбран из-за простого управления процессами, `git`, `make`, PID files, shell glue
- `Python 3.9+`
  - вся прикладная логика helpers и bot
  - удобно для JSON, Telegram polling, CLI helpers, trust-layer logic
- `codex exec`
  - runtime для Coder и Tech Lead
  - позволяет использовать одну и ту же оркестрацию поверх разных задач/репозиториев
- `pytest`
  - regression suite и integration checks
  - нужен для self-heal gate и доверия к baseline
- `Pydantic`
  - `scripts/models.py`
  - типизированная валидация `ralph_state.json` и review/task payloads
- `setuptools` + `pyproject.toml`
  - packaging CLI как installable Python package
- `python-dotenv`
  - чтение `.env` для Telegram token/chat id
- `git`
  - diff, commits, repo-backed evidence, task closure, stale state recovery
- `make`
  - единая тестовая точка входа `make test`
- `gtimeout`
  - bounded execution для codex processes
- `urllib`
  - Telegram integration без тяжёлого framework
- `JSON`
  - главная storage-модель: `tasks.json`, `ralph_state.json`, `ralph_control.json`, audit artifacts
- `CSV`
  - дешёвое хранение runtime metrics в `logs/metrics.csv`

## 4. Key technical decisions & tradeoffs

1. **Project-agnostic runtime**
   - Решение: `ralph.sh` и helpers работают через `PROJECT_DIR`, а не через hardcoded paths.
   - Tradeoff: больше shell glue и careful path discipline.

2. **File-based state instead of DB**
   - `tasks.json`, `ralph_state.json`, `ralph_control.json`, `.ralph/audit/*.json`
   - Плюс: inspectable, debuggable, легко переносить между проектами.
   - Минус: stale state, PID residue, manual reconciliation.

3. **Two-agent loop: Coder + Tech Lead**
   - Плюс: разделение “сделать” и “оценить”.
   - Минус: latency и токеновая цена.

4. **Trust layer after lead approve**
   - `approve` недостаточно, нужен `verify_task_closure.py`
   - Плюс: меньше false-positive closures.
   - Минус: сложнее status model и больше operator tooling.

5. **Runtime owns bookkeeping**
   - coder не трогает `tasks.json`, `progress.md`, audit, final commits
   - Плюс: чище ownership boundary.
   - Минус: нужно санитизировать noisy lead fixes.

6. **Handoff path как отдельный operator-only mode**
   - для validated partial/repo-backed candidate state
   - Плюс: дешёвое closure path без нового coder run.
   - Минус: ещё один execution mode и отдельная contamination semantics.

7. **Self-heal before task execution**
   - если `make test` красный до task start, запускается `ENV-FIX`
   - Плюс: не запускать feature task поверх broken baseline.
   - Минус: expensive detour, который может съесть весь session budget.

8. **Packaged mirror of runtime surface**
   - `src/ralph/resources/...` дублирует shell/scripts/templates
   - Плюс: installable CLI.
   - Минус: нужно держать root и packaged copies синхронными.

## 5. How the Telegram bot works

### Основные file-level элементы
- `scripts/ralph_bot.py`
  - `read_state()`
  - `get_live_ralph_pid()`
  - `normalize_state_for_display()`
  - `reset_stale_state()`
  - `write_control()`
  - `handle_update()`
  - `poll_updates()`

### Команды
- Execution:
  - `/start TASK_ID`
  - `/phase NUM`
  - `/auto`
  - `/stop`
  - `/stop now`
  - `/pause`
  - `/resume`
  - `/timeout [seconds]`
- Backlog/operator:
  - `/tasks [phase]`
  - `/plan`
  - `/done [task_id]`
  - `/redo [task_id] [notes]`
  - `/comment text`
- Inspection:
  - `/status`
  - `/log [N]`
  - `/tail [N]`
  - `/progress`
  - `/diff`
  - `/cost`
  - `/stats`
  - `/limits`
  - `/audit <task_id>`
  - `/audit_last [N]`
  - `/trust_report`
  - `/ask <question>`
  - `/reload`

### State machine с точки зрения бота
- Бот не является execution engine.
- Он:
  - читает `ralph_state.json`
  - пишет control action в `ralph_control.json`
  - проверяет live PID via `ralph_main.pid`
  - умеет auto-reset stale display state для UX

### `/ask`
- Реализован через:
  - `build_repo_local_ask_backend()`
  - `answer_repo_local_question()`
- Это intentionally bounded single-shot backend:
  - без chat history
  - без multi-turn memory
  - ответ строится из `read_state()` + summary tasks

## 6. How the agent pipeline works

### Основной loop в `ralph.sh`
- smoke/preflight: `check_and_recover_state()`, затем `make test`
- task selection: `next_task.py`
- coder:
  - prompt assembly
  - `run_codex()`
  - optional retries/backoff
- post-coder:
  - commit WIP changes
  - `make test`
  - diff capture
- lead:
  - review prompt с diff + tests
  - parse JSON review
- decision handling:
  - `approve` -> `run_task_closure_verification()`
  - `fix` -> retry with fix instructions
  - `alert` -> block/notify
  - `reorder` -> change next exact task
- closure:
  - update task/progress/memory
  - final commit
  - write audit artifact
  - update final runtime state

### Core functions
- `run_codex()` — bounded codex execution with watchdog and exponential backoff
- `coder_prompt_profile()` — selects `broad` vs `narrow`
- `run_task_closure_verification()` — repo evidence gate before closure
- `write_task_audit_artifact()` — writes `.ralph/audit/<TASK>.json`
- `persist_task_success_state()` — truthful final state on success
- `self_heal_environment()` — baseline repair branch when preflight tests fail

## 7. State management

### `tasks.json`
- backlog truth
- scheduler reads only `pending`
- statuses now include:
  - `pending`
  - `done`
  - `verified_done`
  - `partial`
  - `false_positive`
  - `blocked`
  - `needs_human_review`

### `ralph_state.json`
- runtime truth
- fields include:
  - `status`
  - `current_task`
  - `current_phase_step`
  - `last_update`
  - `message`
- updated throughout the shell runtime

### `ralph_control.json`
- operator intent
- examples:
  - `continue`
  - `pause`
  - `stop`
  - `skip`
  - `comment`

### How they work together
- `tasks.json` answers: “что backlog считает правдой?”
- `ralph_state.json` answers: “что runtime делает прямо сейчас?”
- `ralph_control.json` answers: “что оператор хочет, чтобы runtime сделал дальше?”
- `.ralph/audit/<TASK>.json` adds a fourth layer:
  - “что concluded latest run?”

## 8. Error handling & reliability mechanisms

- **Smoke test before task selection**
  - `make test` before any task run
- **Self-heal path**
  - if smoke fails, runtime generates synthetic `ENV-FIX` task
- **Timeouts**
  - `run_codex()` wraps each codex exec in `gtimeout`
- **Watchdog**
  - separate watchdog kills stale codex processes
- **Exponential backoff**
  - `60s -> 120s -> 300s`
- **Rate-limit pause**
  - detects `429` / throttling in output
- **Circuit breaker**
  - stops after repeated failures
- **PID guard**
  - prevents duplicate launches using `ralph_main.pid`
- **Stale state recovery**
  - `check_and_recover_state()` in shell
  - `reset_stale_state()` / `normalize_state_for_display()` in bot
- **Contradictory fix blocking**
  - lead instructions that ask for runtime-owned bookkeeping are sanitized or blocked
- **Closure verification**
  - prevents “approve => done” shortcut
- **Audit artifacts**
  - inspectable run truth even when backlog truth changes later
- **Repo-backed handoff**
  - can close validated state without rerunning coder

## 9. Metrics / scale

### Backlog scale right now
- Total tasks: **107**
- Status breakdown:
  - `done`: 68
  - `verified_done`: 18
  - `false_positive`: 15
  - `pending`: 4
  - `partial`: 1
  - `blocked`: 1

### R12 phase now
- `R12`:
  - `verified_done`: 3
  - `blocked`: 1
  - `pending`: 4

### Runtime metrics from `logs/metrics.csv`
- Recorded task runs: **79**
- Successes: **65**
- Fails: **14**
- Total recorded duration: **37078s** (~10.3h)

### Performance reality
- Main current bottleneck is not correctness of closure path.
- Main bottleneck is economics of fresh coder-first runs:
  - repeated `make test`
  - long coder attempts
  - self-heal detours when baseline is red

## 10. What I would do differently / known limitations

1. Убрал бы часть duplicate validation cost
   - сейчас есть full `make test` до coder и ещё one more runtime test after coder
   - плюс prompt may still encourage coder to rerun tests

2. Вынес бы state model в более explicit event log
   - file-based state inspectable, но stale-state recovery complexity высокая

3. Сократил бы root/packaged duplication
   - сейчас `ralph.sh` и `src/ralph/resources/ralph.sh` требуют disciplined sync

4. Улучшил бы scheduler/candidate shaping
   - helper optimism иногда misleading
   - хорошие runnable candidates критичны для unattended economics

5. Отделил бы baseline repair от feature execution строже
   - self-heal полезен, но сейчас expensive и opaque

6. Добавил бы richer metrics
   - prompt size
   - preflight time vs coder time vs lead time
   - retries by task class

## 11. Как это relates to FastAPI / async Python / queues / AI integration at scale

### FastAPI services
- Хотя здесь нет FastAPI, паттерны знакомые:
  - state + control plane
  - background job orchestration
  - auditability
  - operator endpoints
- Это легко мапится на service architecture:
  - bot commands -> API endpoints
  - `tasks.json` -> DB rows / job table
  - `ralph_state.json` -> runtime state store

### Async Python
- Бот уже по сути async control plane:
  - long polling
  - command dispatch
  - state inspection
- При переходе на FastAPI/Celery/RQ/Arq:
  - `ralph_bot.py` логически разделится на API layer + worker layer

### Queue systems
- `next_task.py` уже выполняет роль very simple queue consumer
- `tasks.json` + deps + statuses = primitive job queue
- `ralph_control.json` = side-channel control bus
- При масштабировании это naturally maps to:
  - Redis queue / Kafka / SQS
  - job leases
  - worker heartbeats

### AI integration at scale
- Ralph уже решает реальные integration problems:
  - agent retries
  - rate limits
  - process cleanup
  - trust gates
  - human escalation
  - auditability
- Это и есть core production lessons for AI systems:
  - model output alone is not truth
  - you need verification, state management, and operator tooling
  - latency/cost and correctness are separate axes

## Короткая interview framing

Если объяснять проект в одном абзаце:

> Я построил repo-local AI orchestration layer, где shell runtime управляет циклом Coder → Tech Lead → verification → audit, а Telegram bot даёт операторский control plane. Ключевая инженерная часть была не просто “запустить LLM”, а выстроить trustworthy closure: state files, PID recovery, retry/backoff, closure verification, audit artifacts, re-audit tooling и handoff path для дешёвого закрытия validated partial state. Основной remaining challenge сейчас — economics свежих coder-first runs, а не базовая correctness модели closure.
