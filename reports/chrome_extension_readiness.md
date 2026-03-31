# Аудит готовности Ralph к генерации Chrome Extension

## Вывод
Ralph **частично готов**, но **не готов из коробки** как специализированный генератор Chrome Extension.  
Он уже умеет работать как project-agnostic orchestration/runtime для внешнего репозитория и может создавать новые файлы по task-driven workflow, но ему не хватает extension-specific scaffolding, frontend/web-extension шаблонов, явного multi-project/workspace UX и более подходящей verification strategy для JS/HTML/CSS проектов.

## Готово

### 1. Ralph уже умеет работать не только внутри собственного репозитория
- `ralph.sh` отделяет `RALPH_DIR` от `PROJECT_DIR` и запускается из любого проекта, где есть `tasks.json`: [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L5), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L12), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L23)
- Telegram bot умеет работать с внешним проектом через `--project-dir`: [scripts/ralph_bot.py](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/scripts/ralph_bot.py#L2115), [scripts/ralph_bot.py](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/scripts/ralph_bot.py#L2126)

### 2. Task model уже достаточно гибкий для Chrome Extension задач
- В `tasks.json` schema уже есть `phase`, `category`, `complexity`, `required_context`, `role`, `risk`, `agent_suitable`, `skip_lead`: [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L25), [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L34)
- Это позволяет формулировать extension-задачи вроде:
  - `manifest.json`
  - `popup.html`
  - `content.js`
  - `background.js`
  - `options.html`
  - `src/*` и `tests/*`

### 3. Coder runtime уже умеет работать с конкретными target files
- Prompt path в `ralph.sh` строится от task JSON и `required_context`, а для narrow tasks выделяет concrete targets: [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L312), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L334), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L378)
- То есть Ralph уже может вести coder к созданию новых файлов проекта, если они явно заданы в задаче.

### 4. Система ролей уже допускает не-Python / product-oriented задачи
- Есть не только coder и lead, но и designer/journalist templates: [templates/AGENTS_CODER.md](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/templates/AGENTS_CODER.md), [templates/AGENTS_DESIGNER.md](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/templates/AGENTS_DESIGNER.md), [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L1121)
- Для Chrome Extension это полезно, потому что popup/options UX и content-flow можно раскладывать отдельно от core coding tasks.

### 5. Есть полезные механизмы для продуктовой extension-разработки
- asset handoff / `assets_manifest.json` уже предусмотрены: [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L1254), [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L1166)
- bootstrap from large prompt уже запланирован как capability: [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L1190)
- bounded `/ask` и audit/trust tooling пригодятся для operator workflow и сопровождения нового проекта: [scripts/ralph_bot.py](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/scripts/ralph_bot.py#L1675), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L4098)

## Нужно доработать

### 1. Нет extension-specific project templates
- В `templates/` нет ничего для Chrome Extension:
  - нет `manifest.json`
  - нет `popup.html`
  - нет `content script`
  - нет `background/service worker`
  - нет `options page`
  Evidence: [templates](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/templates)
- Сейчас Ralph может **сгенерировать** эти файлы задачами, но не умеет **скелетонизировать** extension repo из готового набора шаблонов.

### 2. Нет явной поддержки modern JS/TS frontend stack
- Есть coder/designer prompts, но нет project templates для:
  - `package.json`
  - `pnpm`
  - `tsconfig.json`
  - Vite/Webpack/Plasmo
  - extension build pipeline
- Проверки и preflight у Ralph всё ещё сильно завязаны на Python/make/pytest paths: [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L3222), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L3555), [templates/AGENTS_CODER.md](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/templates/AGENTS_CODER.md#L4)
- Для Chrome Extension это значит: orchestration уже есть, но build/test conventions надо адаптировать под Node/TS/WebExtension.

### 3. Multi-project/workspace не доведён до product-ready состояния
- Bot умеет `--project-dir`, но полноценный multi-project bot UX пока только как roadmap item: [scripts/ralph_bot.py](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/scripts/ralph_bot.py#L2115), [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L894)
- Для реального extension workflow удобнее было бы:
  - держать `ralph-dev` отдельно
  - подключать `hh-extension/` как рабочий проект
  - переключаться между проектами без ручного перезапуска/перенастройки

### 4. Verification layer не адаптирован под Chrome Extension artifacts
- Текущий verifier сильнее всего ориентирован на command/script/template/docs/tests patterns: [scripts/verify_task_closure.py](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/scripts/verify_task_closure.py#L86)
- Для extension-задач понадобятся отдельные checks:
  - `manifest_version`
  - наличие `permissions`
  - корректные `content_scripts`
  - связность popup/background/content wiring
  - отсутствие сломанного JSON в `manifest.json`
  - возможно smoke-check на build или static bundle layout

### 5. Нет готовой domain model под hh.ru / LLM-assisted cover letter workflow
Для цели:
- анализ вакансии на странице
- сопоставление с профилем
- генерация сопроводительного письма через LLM API
- помощь в чате с HR

Ralph пока не даёт готовых шаблонов под:
- page DOM extraction
- profile schema
- prompt contracts для cover letter
- privacy/credential model
- extension-side API key handling
- rate limits / background request orchestration

То есть продуктовую логику придётся проектировать как новый task tree.

## Не нужно менять

### 1. Task-driven orchestration model
- Сам подход “разбивать работу на phases/tasks и прогонять через coder/reviewer/runtime” уже подходит для Chrome Extension проекта as-is: [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json)

### 2. Project-agnostic execution base
- Разделение `RALPH_DIR` / `PROJECT_DIR` уже правильное и менять его не нужно: [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L5), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L23)

### 3. Role system
- `coder` + `designer` + `lead` уже можно использовать для extension flow:
  - coder: implementation
  - designer: popup/options UX and flows
  - lead: narrow review and acceptance

### 4. Audit / trust / operator tooling
- Для нового проекта это полезно без изменений:
  - audit artifacts
  - `/ask`
  - `/audit`
  - `/audit_last`
  - `/trust_report`
  - pause/resume/redo/comment flow

### 5. `tasks.json` schema
- Поля `complexity`, `required_context`, `role`, `risk`, `agent_suitable` уже достаточно универсальны для web-extension backlog.

## План задач

Ниже предлагаю не “одну большую задачу”, а phases/tasks для нового extension-проекта.

### Phase E0 — Bootstrap Extension Project
- `E0-01`: Bootstrap external project `hh-chrome-extension/` with `tasks.json`, `AGENTS.md`, `ARCHITECTURE.md`, `.ralph/memory/`
- `E0-02`: Add Node 20 + pnpm project skeleton (`package.json`, `tsconfig.json`, lint/test scripts)
- `E0-03`: Add Chrome Extension base structure (`manifest.json`, `src/popup`, `src/content`, `src/background`, `assets/`)

### Phase E1 — Ralph Readiness for Web Extensions
- `E1-01`: Add template set for Chrome Extension scaffolding under `templates/extensions/chrome/`
- `E1-02`: Add role/template guidance for JS/TS/HTML/CSS projects
- `E1-03`: Add verification rules for `manifest.json`, popup/background/content wiring
- `E1-04`: Add Node/TS-oriented preflight and targeted verification path instead of Python-biased defaults
- `E1-05`: Improve external-project bootstrap so Ralph can initialize non-Python repos from a product brief

### Phase E2 — Vacancy Parsing Product Logic
- `E2-01`: Define domain schema for vacancy/profile/cover-letter/chat-assist
- `E2-02`: Implement hh.ru vacancy DOM extraction in content script
- `E2-03`: Implement profile storage/options page
- `E2-04`: Implement matching engine between vacancy and profile

### Phase E3 — LLM Features
- `E3-01`: Add secure LLM API settings flow in options page
- `E3-02`: Generate structured cover letter from vacancy + profile context
- `E3-03`: Add HR chat assist prompts and response suggestions
- `E3-04`: Add rate-limit/error handling for LLM requests in background/service worker

### Phase E4 — Product UX
- `E4-01`: Popup UX for quick vacancy summary and fit score
- `E4-02`: Options/settings UX for profile editing and API config
- `E4-03`: Injected page actions on hh.ru vacancy pages
- `E4-04`: Empty/error/loading states for all extension surfaces

### Phase E5 — Reliability and Release
- `E5-01`: Add local smoke checks for manifest validity and extension bundle
- `E5-02`: Add targeted tests for parser/matcher/prompt builders
- `E5-03`: Add privacy and secret-handling review
- `E5-04`: Add packaging/release instructions for loading unpacked extension

## Честная оценка

Если вопрос звучит как:

**“Можно ли прямо сейчас запустить Ralph и получить хорошо структурированный Chrome Extension проект под hh.ru без дополнительных изменений?”**

Ответ: **нет**.

Если вопрос звучит как:

**“Можно ли использовать текущий Ralph как orchestration/runtime основу для разработки внешнего Chrome Extension проекта по task tree?”**

Ответ: **да, вполне**.

### Итог
- **Как task orchestrator для внешнего extension repo**: да, уже usable
- **Как готовый extension generator/platform**: нет, пока не хватает scaffold + JS/web-extension verification + product bootstrap
- **Как база для следующего шага**: хорошая, особенно если сначала сделать маленький readiness phase `E1`
