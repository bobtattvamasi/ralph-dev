
## 

===TELEGRAM===
> b.g_ / build log #03

Сдвинул Ralph из "просто раннера задач" в более управляемый оркестратор: усилил runtime, добавил ролевую логику агентов и вывел генерацию материалов в отдельный контур.

**Что сделал**
- Дожал стабильность рантайма: cleanup зависших Codex-процессов, cleanup process group, retry после timeout, более аккуратная обработка rate limit и watchdog.
- Добавил и расширил интеграционные тесты для `ralph.sh`: завершение задачи, `skip`, `stop`, убийство зависшего процесса, повторные попытки.
- Вынес управление агентами на уровень ролей: Ralph теперь понимает `role` и `risk` в задачах, подхватывает отдельные инструкции для journalist/designer.
- Поставил human approval gate перед high-risk действиями, чтобы опасные шаги не проходили в commit-контур автоматически.
- Добавил генерацию драфтов статей: `write_article.sh`, команда `/article`, сохранение в `BLOG_DRAFTS.md`.
- Подкрутил Telegram-бота: команды для задач, паузы/резюма, лимитов, статьи; обновил help и маршрутизацию.
- Переписал README как описание project-agnostic orchestrator, убрал устаревший `system_promt.md`.

**Что сломалось / Технический челлендж**
- Главная проблема была не в модели, а в процессе: orphan PID, stale Codex-процессы, таймауты и recovery вели себя недостаточно жёстко для длинных прогонов.
- Отдельно пришлось разруливать safe cleanup не только по PID, но и по process group, иначе watchdog лечил симптом, а не причину.
- После добавления ролей и risk-gate стало критично удержать control flow простым: где пауза, где skip, где stop, где нужен человек перед commit.

**Что добавил в систему**
- Role-based agent layer для разных типов задач.
- High-risk approval gate в execution pipeline.
- Контур article generation внутри Telegram-управления.
- Более жёсткий runtime safety слой: cleanup, retries, rate-limit pause, тестовое покрытие этих сценариев.

**Вывод**
Система стала менее хрупкой и ближе к реальному автономному циклу: не только выполняет задачи, но и лучше переживает сбои, различает типы работы и не делает рискованные шаги без человека. Фокус всё ещё тот же: инфраструктура и контроль важнее "магии модели".

===LINKEDIN===
The last round of work on Ralph reinforced a simple point: once you move beyond demos, the real bottleneck is rarely the model. It is the infrastructure around it.

I spent this cycle hardening the execution layer: better cleanup of orphaned Codex processes, stronger timeout recovery, safer retry handling, and broader integration tests for stop, skip, stale-process recovery, and rate-limit scenarios. That work matters because autonomous runs fail in operationally boring ways long before they fail in intellectually interesting ways.

On top of that, Ralph now supports role-based agents and explicit task risk metadata. Different instructions can be loaded for different roles, and high-risk actions now hit a human approval gate before entering the commit path. This is the kind of control flow that becomes necessary when you want an agent system to be useful in production rather than impressive in a screenshot.

I also added an article-generation path through the bot interface, which is a smaller feature on the surface, but useful as a test of orchestration boundaries: task classification, role routing, output persistence, and user control all in one loop.

The pattern keeps repeating: model quality helps, but reliability, safety, process isolation, and explicit control surfaces decide whether the system is actually usable. Infrastructure is what turns model capability into something you can trust overnight.

===PROMPTS===
Minimalist cyberpunk control room dashboard, autonomous AI orchestration, process cleanup and retry loops, cold terminal glow, black graphite and acid green
Cyberpunk developer workstation, agent roles and human approval gate visualized as branching execution paths, dense technical UI, restrained neon
Minimal poster design, infrastructure over model theme, orchestration pipeline with safety checkpoints and runtime states, monochrome with sharp red accent

## 

## Telegram

> b.g_ / build log #03

Собрал следующий слой вокруг Ralph: из набора скриптов он уехал в более жёсткую проектную систему с CLI, bootstrap-потоком и мультипроектным управлением из бота. Смысл простой: меньше ручной сборки, меньше хрупких точек, больше повторяемости.

**Что сделал**
- Упаковал Ralph в CLI: появился `ralph` entrypoint, структура `src/ralph`, ресурсные шаблоны и тест на packaging.
- Добавил `ralph.toml` как конфигурационный слой вместо разрозненных ручных настроек.
- Собрал Project Bootstrapper: проект можно поднимать через шаблоны, а не склеивать руками каждый раз.
- Дотянул мультипроектность в Telegram-бот до рабочего состояния: один контур управления, несколько репозиториев.
- Перед этим закрыл операционные хвосты: `/stop` теперь нормально сбрасывает состояние, добавлен cleanup orphan PID, graceful stop с таймаутом, git safety для codex subshell.

**Что сломалось / Технический челлендж**
- Главная проблема была не в модели, а в управлении процессами: висячие PID, незакрытые process groups, нестабильный stop/retry-контур.
- По мере роста фич стало видно, что без нормального bootstrap и config-слоя каждый новый проект превращает оркестратор в набор исключений.
- Мультипроектный режим в боте повышает ценность системы, но сразу поднимает требования к изоляции состояния и предсказуемости runtime.

**Что добавил в систему**
- CLI-оболочку как стабильную точку входа.
- Конфиг-файл `ralph.toml`.
- Bootstrapper для разворачивания новых проектов.
- Шаблоны ролей и проектных файлов внутри package resources.
- Мультипроектный control surface в Telegram-боте.

**Вывод**
Сдвиг не в сторону “ещё одного AI-агента”, а в сторону инфраструктуры, которую можно переносить между проектами без ручной пересборки. Чем дальше, тем яснее: ценность здесь делает не модель, а дисциплина исполнения, контроль состояния и упаковка среды.

## LinkedIn

Most AI agent work still over-focuses on the model layer.

What actually moved this system forward was infrastructure: packaging Ralph into a real CLI, adding a config layer with `ralph.toml`, introducing a bootstrapper for new projects, and extending the bot toward multi-project control. That is the difference between a demo loop and an operational system.

The technical pressure point was runtime reliability, not prompting. Process cleanup, stop semantics, retry behavior, orphan PID handling, and safe Git execution all mattered more than model cleverness. Once an agent touches real repositories and long-running tasks, control flow becomes the product.

This is the pattern I keep seeing: models generate output, but infrastructure determines whether the system is reusable, safe, and scalable. Entry points, state isolation, config boundaries, role templates, watchdog behavior, and human approval gates are what let an agent survive outside a toy environment.

If you want multi-agent systems to work across projects, “better prompts” is not enough. You need repeatable bootstrap, explicit runtime contracts, and failure handling that assumes the process will eventually get weird.

Infrastructure is not support work here. It is the system.

## Cover Prompts

Minimalist terminal dashboard controlling multiple AI projects, cold white typography, black grid, precise orchestration UI  
Cyberpunk ops room with parallel agent pipelines, glowing repo nodes, PID cleanup and control flow overlays  
Minimal poster of AI infrastructure stack, CLI entrypoint, config file, bootstrap flow, stark layout, engineering mood
