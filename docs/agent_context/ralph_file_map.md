# Ralph File Map

## Entry points

| File | Назначение | Как запускать |
| --- | --- | --- |
| `ralph.sh` | Основной shell orchestrator | `bash ralph.sh status|task <id>|phase <phase>|auto|handoff <id>` |
| `ralph-init.sh` | Инициализация Ralph-файлов в целевом проекте | `bash ralph-init.sh [project_name]` |
| `src/ralph/cli.py` | Packaged CLI wrapper | `python3 -m ralph ...` or installed `ralph ...` |
| `src/ralph/__main__.py` | `python -m ralph` entry | `python3 -m ralph` |
| `scripts/ralph_bot.py` | Telegram bot control plane | `python3 scripts/ralph_bot.py --project-dir .` |

## Core orchestration

| File | Назначение | Важные функции/команды |
| --- | --- | --- |
| `ralph.sh` | Выбор задач, prompt assembly, codex runs, retries, verification, final state | `run_codex`, `run_task_closure_verification`, `detect_scope_anomaly`, `apply_timeout_override`, `wait_for_required_assets`, `write_state` |
| `scripts/next_task.py` | Выбор следующей runnable задачи | `build_scope_warnings`, `main` |
| `scripts/ralph_common.py` | Общие helper’ы для tasks/control/state/env | `resolve_project_dir`, `load_tasks_data`, `pick_next_task`, `mutate_tasks_data`, `locked_path`, `infer_task_context` |
| `scripts/extract_json.py` | Извлечение authoritative review JSON | `is_placeholder_review`, parser helpers |
| `scripts/verify_task_closure.py` | Trust-layer verification before closure | `verify_task_completion`, `build_target_file_debug` |
| `scripts/audit_artifact.py` | Запись/чтение audit artifacts и trust report | `write_artifact`, `trust_report`, `audit_last` |
| `scripts/re_audit_tasks.py` | Conservative repo-truth re-audit | `classify_task`, `load_tasks`, apply/dry-run flow |
| `scripts/explain_task.py` | Operator-readable truth explanation for one task | `suggested_next_action`, `main` |
| `scripts/reopen_tasks.py` | Controlled manual reopen/status correction | CLI mutator |
| `scripts/manage_assets.py` | Assets manifest validation/sync | manifest helpers |
| `scripts/run_benchmark.py` | Benchmark/report helper | benchmark CLI |
| `scripts/check_prompt_budgets.py` | Prompt budget regression checks | script runner |

## Telegram

| File | Назначение | Команды |
| --- | --- | --- |
| `scripts/ralph_bot.py` | Telegram command dispatcher, state/status views, `/ask`, project switching | `/status`, `/projects`, `/switch`, `/tasks`, `/plan`, `/add`, `/rm`, `/pause`, `/resume`, `/start`, `/phase`, `/auto`, `/stop`, `/done`, `/redo`, `/timeout`, `/comment`, `/log`, `/progress`, `/tail`, `/audit`, `/audit_last`, `/trust_report`, `/ask`, `/cost`, `/stats`, `/limits`, `/diff`, `/reload`, `/help` |
| `scripts/ralph_notify.py` | One-shot Telegram notification helper used by runtime | notification sends only |
| `scripts/bot_smoke_check.py` | Smoke-check Telegram transport and bot help path | smoke-check CLI |
| `scripts/manage_projects.py` | Multi-project registry used by bot commands | `add`, `remove`, `list`, `switch`, `active` |

## State / data

| Файл/папка | Что хранит | Формат |
| --- | --- | --- |
| `tasks.json` | Backlog truth, phase/task metadata | JSON |
| `progress.md` | Narrative progress history | Markdown |
| `ralph_state.json` | Current runtime state | JSON |
| `ralph_control.json` | Operator control actions/comments | JSON |
| `.ralph/memory/` | Memory layers (`core.md`, `recent.md`, `patterns.md`, `decisions.md`) | Markdown |
| `.ralph/audit/` | Latest-run task audit artifacts | JSON |
| `logs/ralph_YYYY-MM-DD.log` | Orchestrator log | text log |
| `logs/metrics.csv` | Aggregated task metrics | CSV |
| `logs/task_phase_timings.csv` | Phase timing metrics | CSV |
| `assets_manifest.json` | Async asset handoff contract | JSON |
| `audit_report.md` | Human-readable re-audit output | Markdown |

## Config

| File | Переменные/настройки без значений |
| --- | --- |
| `.env.example` | Telegram token/chat id and runtime env examples. File content not inspected for secrets here. |
| `pyproject.toml` | package metadata, `requires-python >=3.9`, `python-dotenv`, pytest testpaths, package data |
| `templates/tasks.json.template` | baseline task schema and example task |
| `scripts/ralph_common.py` | default timeout/retry/Telegram constants and env names |

## Tests

| File | Что проверяет | Как запускать |
| --- | --- | --- |
| `tests/test_integration.py` | End-to-end runtime behavior, prompts, handoff, retries, audit, assets, timeout paths | `python3 -m pytest tests/test_integration.py` |
| `tests/test_ralph_shell_helpers.py` | Shell helper semantics and trust/review parsing | `python3 -m pytest tests/test_ralph_shell_helpers.py` |
| `tests/test_verify_task_closure.py` | Closure verification policy | `python3 -m pytest tests/test_verify_task_closure.py` |
| `tests/test_re_audit_tasks.py` | Re-audit classification/apply logic | `python3 -m pytest tests/test_re_audit_tasks.py` |
| `tests/test_bot_commands.py` | Telegram command handlers | `python3 -m pytest tests/test_bot_commands.py` |
| `tests/test_bot_reload.py` | Bot reload and traceback behavior | `python3 -m pytest tests/test_bot_reload.py` |
| `tests/test_bot_stats.py` | Metrics and `/stats` | `python3 -m pytest tests/test_bot_stats.py` |
| `tests/test_cli_packaging.py` | Packaged CLI/resource parity | `python3 -m pytest tests/test_cli_packaging.py` |
| `tests/test_operator_helpers.py` | Explain/reopen/smoke/shared I/O | `python3 -m pytest tests/test_operator_helpers.py` |
| `tests/test_manage_projects.py` | Project registry | `python3 -m pytest tests/test_manage_projects.py` |
| `tests/test_manage_assets.py` | Asset manifest validation/sync | `python3 -m pytest tests/test_manage_assets.py` |
| `tests/test_extract_json.py` | Review JSON extraction fail-closed behavior | `python3 -m pytest tests/test_extract_json.py` |
| `tests/test_prompt_budgets_script.py` | Prompt budget tool | `python3 -m pytest tests/test_prompt_budgets_script.py` |
| `tests/test_mutator_scripts.py` | update/progress/memory/notify scripts | `python3 -m pytest tests/test_mutator_scripts.py` |
| `tests/test_models.py` | Data models and statuses | `python3 -m pytest tests/test_models.py` |
| `tests/test_tasks_parsing.py` | Task schema defaults/robustness | `python3 -m pytest tests/test_tasks_parsing.py` |
| `tests/test_benchmark.py` | Benchmark reporting | `python3 -m pytest tests/test_benchmark.py` |
| `tests/test_run_eval.py` | Eval harness helper | `python3 -m pytest tests/test_run_eval.py` |
| `tests/test_kill_tree.py` | Process cleanup helpers | `python3 -m pytest tests/test_kill_tree.py` |

## Docs

| File | Что содержит |
| --- | --- |
| `README.md` | Product overview, quick start, Telegram commands, runtime model |
| `ARCHITECTURE.md` | High-level architecture summary |
| `MEMORY_SYSTEM.md` | Memory layers and update policy |
| `CHANGELOG.md` | Dated release-style changes |
| `docs/TRUST_LAYER.md` | Trust model and closure semantics |
| `docs/STATUS_MODEL.md` | Minimal status set and truth precedence |
| `docs/AUDIT_WORKFLOW.md` | Operator audit workflow |
| `docs/TASK_VERIFICATION_POLICY.md` | Verification policy, implemented vs deferred |
| `docs/POSTMORTEMS/2026-03-trust-layer-failure.md` | Trust-layer failure postmortem |
| `BRITTLENESS_AUDIT.md` | Drift/duplication/race/test-gap audit |

## Unknown / suspicious files

| File | Почему требует внимания |
| --- | --- |
| `src/ralph/resources/*` | Copied packaged resources can drift from root implementations |
| `auto_update.sh` / `scripts/auto_update.py` | Legacy-looking task/progress mutators; current role in main flow is not primary |
| `.ralph/audit/*.txt` and logs under `logs/` | Historical/generated artifacts; useful for forensics but not authoritative runtime source code |
| `docs/articles/interview_prep.md` | Appears non-core to orchestrator architecture |
| `progress.md` | Valuable history, but explicitly not authoritative task truth |
