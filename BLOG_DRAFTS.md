

## 

## Telegram

> b.g_ / build log #03

Поджал Ralph не в сторону “умнее модель”, а в сторону “меньше случайного хаоса в рантайме”.

**Что сделал**
- Добил runtime-слой: watchdog/retry стали настраиваемыми через env, усилил cleanup зависших `codex`-процессов, добавил работу с `PID/PGID`, ретраи после timeout и более нормальную обработку rate limit.
- Закрыл это интеграционными тестами: success path, `skip`, `stop`, убийство зависшего Codex, повторные попытки.
- Добавил ролевую схему агентов: Ralph теперь понимает `role` и `risk` в задачах, подхватывает отдельные инструкции для `designer` и `journalist`.
- Поставил human approval gate перед high-risk коммитами: `pause/skip/stop` до записи в git.
- Добавил контентный контур: `write_article.sh`, команду `/article` в Telegram-боте и сохранение драфтов в `BLOG_DRAFTS.md`.
- По боту добил UX-слой: `/add`, `/rm`, `/pause`, `/resume`, `/limits`.
- Переписал README: теперь проект описан как project-agnostic AI orchestrator, без старого ручного промпта.

**Что сломалось / Технический челлендж**
- Главная грязь была не в “агентности”, а в управлении процессами: orphan/stale `codex`, таймауты, process group cleanup, recovery после rate limit.
- Без этого любой auto-режим быстро превращается в лотерею: бот жив, задача висит, процессы не добиты, состояние поломано.
- Отдельно всплыл разрыв между синхронным исполнением и наблюдаемостью: live-control есть, но runtime всё ещё требует жёсткой дисциплины вокруг логов и остановки.

**Что добавил в систему**
- Ролевой слой поверх задач: разные инструкции под разные типы работы.
- Risk gate для high-impact изменений перед коммитом.
- Контентный пайплайн из оркестратора в Telegram и `BLOG_DRAFTS.md`.
- Более жёсткий execution control: retries, watchdog, cleanup, интеграционные проверки.

**Вывод**
Сдвиг полезный: Ralph стал меньше “обвязкой вокруг Codex” и больше управляемым execution layer. Ценность сейчас не в том, что он может что-то написать, а в том, что он умеет это делать с контролем, остановкой и проверяемым состоянием.

## LinkedIn

Most AI tooling discussions still over-focus on the model.

This week reinforced the opposite point: infrastructure beats model quality surprisingly often.

In Ralph, the meaningful progress was not “better prompts” or “smarter agents.” It was tightening the execution layer around them:
- watchdog and retry behavior became configurable
- Codex process cleanup was hardened with PID/PGID-aware termination
- timeout and rate-limit recovery paths were made more reliable
- integration tests were added for stop, skip, retry, and stale-process scenarios
- role-based agent instructions were introduced
- high-risk tasks now pause behind a human approval gate before commit

That changes the system in a deeper way than swapping one model for another.

A model can generate output. It cannot guarantee safe control flow, consistent state transitions, bounded retries, or predictable operator intervention. Those are infrastructure concerns. And in any real autonomous workflow, those concerns define whether the system is usable.

The pattern is becoming clearer:
- Model quality affects local output quality
- System design affects whether the workflow survives contact with reality

If the runtime can’t clean up orphan processes, recover from rate limits, gate risky actions, and expose control to a human operator, “agentic” behavior is mostly theater.

The interesting work is increasingly in orchestration:
reliability, review gates, memory boundaries, task semantics, and operational control.

Infrastructure is what turns a model into a system.

## Cover Prompts

Minimalist terminal UI, red approval gate, black and bone palette, orchestration dashboard, clean grid, infrastructure over model
Cyberpunk control room with watchdog alerts, orphan process cleanup, PID graphs, cold neon cyan and amber, AI runtime supervision
Minimal poster, single command line glowing in dark space, retries timeout rate-limit safety, sharp typography, restrained futuristic aesthetic
