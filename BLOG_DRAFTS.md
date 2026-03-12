
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
