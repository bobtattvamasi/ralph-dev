# Ralph Dev — blog context

## 1. О проекте Ralph

Ralph — это project-agnostic AI orchestration layer для software-репозиториев. По сути это автономный исполнитель задач поверх обычного git-проекта: он читает `tasks.json`, собирает контекст из документации и памяти, запускает Coder-агента через `codex exec`, затем прогоняет результат через Tech Lead review, тестовый gate и trust layer verification.

Отдельная сильная сторона Ralph — не просто “запустить агента”, а держать управляемый runtime. У проекта есть Telegram control plane, file-based state, retry/backoff, watchdog, recovery после зависаний и audit artifacts. Это делает Ralph похожим не на чат-бота, а на рантайм для ночного auto-pilot режима.

### Ключевые фичи

- 2-agent loop: `Coder` + `Tech Lead`
- Оркестрация задач из `tasks.json`
- Telegram bot для удалённого управления
- File-based state: `ralph_state.json`, `ralph_control.json`, `progress.md`, `logs/*`
- Memory system: `core`, `recent`, `patterns`, `decisions`
- Retry logic, exponential backoff и rate-limit pause
- Watchdog для зависших `codex exec`
- Process cleanup через `kill_tree` и PGID cleanup
- Trust layer verification перед закрытием задачи
- Audit artifacts и `metrics.csv` для разборов прогонов
- Async asset handoff через `assets_manifest.json`
- Project-agnostic attach к любому repo с `tasks.json`

### Текущая фаза и прогресс

- Всего задач: **144**
- Завершено: **119/144** (`68 done` + `51 verified_done`)
- Текущая активная фаза по состоянию рантайма: **R14**
- Текущий runtime state: `running`, task `R14-03`, step `blocked`
- Полностью закрытые фазы: **R0, R1, R1.5, R2, R3, R4, R10, R11, R13**
- Незаполненные хвосты сейчас в основном в **R5–R9, R12, R14**

### Стек технологий

- Bash: основной orchestrator `ralph.sh`
- Python 3: bot, shared helpers, verifier, mutator scripts
- Codex CLI: execution runtime для агентов
- Git: diff, review context, commit flow
- Telegram Bot API: remote control plane
- JSON + Markdown: tasks, state, memory, audit, docs
- Pytest: unit/integration coverage

## 2. Архитектура (кратко)

### Схема работы в 5 строк

1. Ralph выбирает следующую runnable-задачу из `tasks.json`.
2. Собирает prompt из task payload, project docs и `.ralph/memory/`.
3. Запускает Coder через `codex exec`.
4. Снимает diff, тесты и отдаёт результат на Tech Lead review + verification.
5. Обновляет state, audit, metrics, progress и либо двигается дальше, либо блокирует/эскалирует.

### Ключевые компоненты

- `ralph.sh` — главный orchestrator, retries, watchdog, process cleanup, metrics, audit
- `scripts/ralph_bot.py` — Telegram bot, long polling, remote commands, status/log/diff/cost controls
- `scripts/ralph_common.py` — shared IO helpers, locks, atomic writes, task/control/state helpers
- `scripts/verify_task_closure.py` — trust-layer verifier перед закрытием задач
- `templates/AGENTS_CODER.md` — правила для Coder, включая local-first discipline
- `templates/AGENTS_LEAD.md` — строгий JSON-review contract для Tech Lead
- `templates/AGENTS_JOURNALIST.md` — отдельная роль для build-log/author workflow

## 3. Достижения и метрики

- Завершённых задач: **119 из 144**
- Статусы: `68 done`, `51 verified_done`, `21 false_positive`, `4 pending`
- Закрытых фаз: **9**
- Последние активные hardening-фазы: **R10, R11, R13**
- Тестовых файлов: **22**
- Отдельных `test_*` кейсов: **151**
- Python-файлов в `scripts/` и `src/`: **42**
- Shell/Makefile артефактов: **7**
- Размер оркестратора `ralph.sh`: **4488 строк**
- Размер Telegram bot: **2154 строки**
- Агентов в основном runtime loop: **2** (`Coder` и `Tech Lead`)

### Дополнительные числа из рантайма

- В последних метриках есть успешные long-running задачи уровня hardening, например `R13-07` с длительностью **10359s**
- В `metrics.csv` видны и удачные, и проваленные canary/r14-прогоны, что даёт материал для честного инженерного нарратива, а не “всё зелёное”

## 4. Интересные детали для блога

### Необычные решения

- `kill_tree()` и `kill_process_group()` в shell: Ralph чистит не только parent PID, а дерево процессов и process group
- Watchdog вокруг `codex exec`: если output-file перестал меняться, рантайм считает агент зависшим и убивает его
- Retry logic с backoff и отдельной веткой для rate limits
- Trust-layer verification: задача не считается закрытой только потому, что review сказал `approve`
- Local-first discipline для Coder: сначала искать паттерны в repo, а не тратить время на web search
- File locks и atomic writes для `tasks.json`, `ralph_state.json`, `ralph_control.json`, `progress.md`

### Что можно подать как историю/кейс

- Переход от “агент просто что-то делает” к “агент работает внутри честного runtime с ограничениями, проверками и recovery”
- Как обычный shell-оркестратор оброс trust layer, audit artifacts и state model
- Почему Telegram bot стал не “чатиком”, а основным control surface для автономного исполнения
- Как проект пришёл к фазе brittleness fixes: сначала функциональность, потом борьба с дрейфом, race conditions и ложными closure

### Проблемы, которые решались нетривиально

- False positives и ложное закрытие задач: пришлось добавлять отдельный verifier
- Drift между root-скриптами и packaged resources
- Гонки на shared JSON/state файлах
- Зависшие `codex` процессы и orphan children
- Непрозрачность lead review, из-за чего пришлось сохранять prompt и reasoning в audit
- Bookkeeping-only closure regression: система могла “закрывать” задачу без реального implementation evidence

## 5. Хронология ключевых событий

### Главные вехи по `git log --oneline -50`

- `063861d` — большой аудит хрупкости и постановка фазы **R13**
- `a141d51` — зависимостям R13 дали правильный порядок исполнения
- `5f3d9c8` — подтверждение `R13-01` и `R13-06`, плюс появление `BUG-05`
- `75d2c62` — подтверждена консолидация логики в `R13-03`
- `6813877` — зафиксированы результаты auto-run по R13, часть задач переведена в `verified_done`
- `83f5b97` — подтверждён locking из `R13-02`, после чего запущен финальный блок тестового hardening
- `a66f1cb` — фаза **R13** закрыта полностью
- `21076fd` — старт планирования **R14** как cleanup/repair-хвоста после R13
- `0cc102d` — фикс regression по bookkeeping-only closure gate
- `68117e7` — cleanup after audit: исправлены 3 невалидных статуса, закрыт `R14-01`, deferred tasks переведены в `false_positive`
- `b3a4cef` — вручную закрыты мета-задачи `R14-05` и `R14-06`

### Как это подать в статье

Если коротко, сюжет такой: Ralph начинался как AI dev orchestrator с двумя ролями и Telegram-управлением, потом дошёл до стадии, где основная работа сместилась с “добавить ещё одну команду” на “сделать runtime честным, проверяемым и способным переживать реальные сбои”. Самая сильная линия для блога — это эволюция от MVP-автоматизации к инженерной системе с watchdog, trust layer, audit trail и ручками для ночного auto-pilot.
