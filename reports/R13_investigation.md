### ✅ Успешно закрытые задачи

Примечание: таблица ниже опирается на текущее `tasks.json` как backlog truth. По нескольким задачам latest-run truth в `.ralph/audit/` расходится с backlog truth, это отдельно отмечено ниже.

| ID | Title | Quality | Attempts | Duration | Tokens |
| --- | --- | ---: | ---: | ---: | --- |
| R13-01 | Sync root and packaged trust/runtime resources | 62 | 2 | 883s | n/a |
| R13-02 | Add locking and atomic writes for runtime shared files | n/a | n/a | n/a | n/a |
| R13-03 | Consolidate duplicated task and control logic | 82 | 3 | 2940s | n/a |
| R13-04 | Harden silent error handling and malformed JSON paths | 95 | 3 | 2985s | n/a |
| R13-06 | Remove or wire up dead shell helpers | 95 | 1 | 806s | n/a |
| R13-07 | Consolidate runtime constants and gate destructive rollback | 94 | 3 | 10359s | n/a |

Комментарии:
- `R13-01` отмечена в [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L2896) как `verified_done`, но latest-run audit в [.ralph/audit/R13-01.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/R13-01.json) имеет `status=blocked`.
- `R13-03` отмечена как `verified_done`, но latest-run audit в [.ralph/audit/R13-03.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/R13-03.json) имеет `status=failed`.
- `R13-02` отмечена как `verified_done`, но у неё нет ни audit artifact, ни metrics row, ни явной `TASK_DONE` строки в логах. Это отдельный runtime gap.
- В audit artifacts поле `review.parsed` пустое `{}` даже там, где `review.raw` содержит валидный JSON review, поэтому `decision/quality_score` приходилось брать из raw-review evidence, а не из parsed structure.

### ❌ Заблокированные задачи

#### R13-05 — Add coverage for untested mutators and trust helpers
- Причина блокировки:
  Из latest-run audit: `Tech Lead requested only runtime-owned bookkeeping or diff-production work and did not specify a coder-owned implementation gap.`  
  Evidence: [.ralph/audit/R13-05.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/R13-05.json), [logs/ralph_2026-03-31.log](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/logs/ralph_2026-03-31.log)
- Можно ли было сделать в auto?
  Нет, не надёжно.
  Почему:
  latest-run log показывает красный тестовый прогон и меняющуюся формулировку lead fix path. Сначала было 3 падения, потом 2 падения, но финальный lead fix уже целился только в тесты `tests/test_ralph_shell_helpers.py`, а runtime заблокировал задачу как contradictory/runtime-owned gap. Это означает, что auto-loop не смог устойчиво согласовать review target и coder-owned fix scope.
- Что нужно для разблокировки:
  1. Привести `tests/test_ralph_shell_helpers.py` к реальному helper contract:
     - `test_handoff_candidate_paths_include_packaged_and_test_evidence`
     - `test_run_task_closure_verification_falls_back_when_verifier_crashes`
  2. Перепроверить, не осталось ли третьего helper regression из более раннего lead review:
     - `test_handoff_commit_parent_hash_uses_empty_tree_for_root_commit`
  3. После фикса прогнать только целевой test path и убедиться, что lead review больше не сводится к runtime-owned diff bookkeeping.

### 🐛 Найденные баги в Ralph runtime

#### 1. Backlog truth расходится с latest-run truth по R13 задачам
- Описание:
  `tasks.json` показывает `verified_done` для `R13-01` и `R13-03`, хотя latest-run artifacts фиксируют соответственно `blocked` и `failed`.
- Где:
  [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L2896), [.ralph/audit/R13-01.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/R13-01.json), [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L2939), [.ralph/audit/R13-03.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/R13-03.json)
- Severity:
  critical
- Предложенный fix:
  ввести инвариант reconcile step между `tasks.json` и `.ralph/audit/<TASK>.json` после auto/phase runs, чтобы `verified_done` нельзя было получить при latest-run `failed/blocked` без явного re-audit/apply или human override trail.

#### 2. У `R13-02` нет audit artifact и metrics row при статусе `verified_done`
- Описание:
  Задача отмечена как завершённая в backlog truth, но не имеет ни `.ralph/audit/R13-02.json`, ни строки в `logs/metrics.csv`, ни явной `TASK_DONE` записи.
- Где:
  [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L2918), [logs/metrics.csv](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/logs/metrics.csv), [.ralph/audit/](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit), [logs/ralph_2026-03-31.log](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/logs/ralph_2026-03-31.log)
- Severity:
  critical
- Предложенный fix:
  добавить пост-closure invariant check: если задача получила `verified_done`, runtime обязан записать metrics row и audit artifact, иначе fail-close и не менять backlog status.

#### 3. Audit artifacts теряют parsed lead review
- Описание:
  В `R13-01`, `R13-03`, `R13-04`, `R13-05`, `R13-06`, `R13-07` `review.raw` содержит валидный `BEGIN_RALPH_REVIEW_JSON ... END_RALPH_REVIEW_JSON`, но `review.parsed` остаётся `{}`.
- Где:
  [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L731), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L761), [.ralph/audit/R13-04.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/R13-04.json)
- Severity:
  medium
- Предложенный fix:
  писать в audit artifact именно уже validated `REVIEW_JSON`, а при пустом `parsed` fail-close либо добавлять явный `review_parse_error`.

#### 4. Schema drift в `logs/metrics.csv`
- Описание:
  Header `metrics.csv` не соответствует числу полей в строках R13: `csv.DictReader` отдаёт лишний столбец в `None`, потому что старый header не содержит `web_search_policy`, а новые строки уже содержат его.
- Где:
  [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L697), [ralph.sh](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/ralph.sh#L719), [logs/metrics.csv](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/logs/metrics.csv)
- Severity:
  medium
- Предложенный fix:
  запускать header migration до любой записи в metrics и добавить self-check на длину CSV row against header.

#### 5. R13 auto-phase зависел от несогласованного dependency truth
- Описание:
  Лог показывает deadlock по R13 dependency chain после `R13-01` fail и позже после `R13-07` success, но final backlog truth потом оказался частично “исправлен” без согласованных latest-run artifacts.
- Где:
  [logs/ralph_2026-03-31.log](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/logs/ralph_2026-03-31.log) строки с `Phase R13 deadlocked`, [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json#L2896)
- Severity:
  medium
- Предложенный fix:
  после deadlock/phase-stop сохранять explicit phase outcome artifact и запрещать последующую silent status reconciliation без re-audit trail.

### 📊 Статистика фазы

#### По backlog truth (`tasks.json`)
- Всего задач: 7
- Done (`verified_done`): 6
- Blocked: 1

#### По latest-run metrics (`logs/metrics.csv`)
- Есть метрики только для 6 задач из 7
- Success rows (`verified_success=true`): 3
- Failed rows: 3
- Success rate по имеющимся metrics rows: 50%
- Среднее время на задачу по имеющимся metrics rows: 4054.5s
- Общая стоимость по имеющимся metrics rows: 1.69
- Общих токенов в repo artifacts нет: безопасно считать только `cost_est`, а не токены

#### По последнему зафиксированному test run из логов
- Последний явно зафиксированный итог: `2 failed, 197 passed, 2 skipped in 697.86s`
- До этого был прогон: `3 failed, 196 passed, 2 skipped in 712.30s`
- Последние явно видимые падающие тесты:
  - `tests/test_ralph_shell_helpers.py::test_handoff_candidate_paths_include_packaged_and_test_evidence`
  - `tests/test_ralph_shell_helpers.py::test_run_task_closure_verification_falls_back_when_verifier_crashes`
- В более раннем lead feedback фигурировал ещё:
  - `tests/test_ralph_shell_helpers.py::test_handoff_commit_parent_hash_uses_empty_tree_for_root_commit`
- Тесты в этом расследовании не запускались; это только лог-based evidence из [logs/ralph_2026-03-31.log](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/logs/ralph_2026-03-31.log)

#### Bash syntax
- `bash -n ralph.sh`:
  - result: pass
  - evidence: exit code 0

#### Git состояние
- Uncommitted:
  - modified: [tasks.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/tasks.json)
  - untracked: [.ralph/audit/R13-05.json](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/R13-05.json)
  - untracked: [.ralph/audit/lead_prompt_R13-05.txt](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/lead_prompt_R13-05.txt)
  - untracked: [.ralph/audit/lead_reasoning_R13-05.txt](/Users/bogdan_galaxy/Documents/My_deals/mine_projects/AI-Agent_experiments/structure-of-mind/ralph-dev/.ralph/audit/lead_reasoning_R13-05.txt)
- Последние коммиты:
  - `f253948 wip(R13-05): coder changes`
  - `dd236ec wip(R13-05): coder changes`
  - `a61bfef wip(R13-05): coder changes`
  - `83f5b97 chore: R13-02 locking verified, skip bookkeeping regression test, launch R13-05`
  - `75d2c62 fix: COMPLETED_STATUSES in explain_task.py, verified R13-03 consolidation`
  - `6813877 chore: R13 auto results — R13-04, R13-07 verified_done, audit artifacts`

### 🔧 Рекомендуемые задачи для R14

1. `R14-01` — Enforce closure invariants between `tasks.json`, `.ralph/audit`, and `logs/metrics.csv`
   - `verified_done` impossible without audit artifact + metrics row + `TASK_DONE` evidence

2. `R14-02` — Repair audit review persistence so `review.parsed` is never silently `{}` when raw review is valid
   - preserve `decision`, `quality_score`, `issues`, `fix_instructions` structurally

3. `R14-03` — Add metrics schema/version migration with row/header consistency checks
   - fix current `web_search_policy` column drift

4. `R14-04` — Truth reconciliation command/report for phase runs
   - compare backlog truth vs latest-run truth and emit mismatches automatically after `phase` / `auto`

5. `R14-05` — Reopen and finish `R13-05` with focused shell-helper test repair
   - target the 2 current failing tests
   - verify whether root-commit helper regression is still present

6. `R14-06` — Add direct regression coverage for contradictory-fix blocking logic
   - ensure runtime distinguishes real coder-owned test fixes from runtime-owned bookkeeping demands

7. `R14-07` — Record phase outcome artifact for `auto` / `phase`
   - capture deadlock, verified closures, blocked tasks, and unresolved mismatches in one structured report
