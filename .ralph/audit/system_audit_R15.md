# Ralph System Audit R15

## Feature Inventory

### `ralph.sh` major capabilities
- Project-agnostic launcher with separate `RALPH_DIR` and `PROJECT_DIR`; it runs from a project directory containing `tasks.json` or from the Ralph directory next to a target project.
- Main runtime loop for `task`, `phase`, and `auto` execution modes.
- Two-agent orchestration: `Coder` prompt assembly, Codex execution, `make test` gate, and `Tech Lead` review.
- Prompt shaping: task-class detection, narrow/broad coder prompt profiles, token-budget enforcement, relevant-context injection, and required-context file clipping.
- Repo context loading from `AGENTS.md`, `ARCHITECTURE.md`, `MEMORY_SYSTEM.md`, and `.ralph/memory/*`.
- Handoff mode for adopting existing worktree or repo-backed candidate changes.
- Control plane: stop, skip, pause/resume, high-risk approval wait, control-file parsing, and Telegram notifications.
- Reliability features: process-tree cleanup, watchdog around Codex execution, timeout overrides, rate-limit handling, retry loop, and recovery helpers.
- Verification and trust features: diff capture, closure verification, lead review JSON validation/parsing, scope anomaly warning, audit artifact writing, and trust-score logging.
- Metrics/reporting: task metrics CSV, phase timings CSV, status report, audit report, trust report, benchmark mode, and final state reporting.
- Auxiliary CLI modes present in `ralph.sh`: `status`, `audit`, `audit-last`, `trust-report`, `re-audit-last`, `benchmark`, `redo`.

### `scripts/` inventory
- `audit_artifact.py`: write and inspect Ralph task audit artifacts.
- `auto_commit.sh`: generate a human summary and conventional commit message from staged diff via Codex.
- `auto_update.py`: update task status in `tasks.json` and append `progress.md`.
- `bot_smoke_check.py`: smoke-check live Telegram command transport.
- `check_prompt_budgets.py`: create a synthetic project and validate coder prompt budget behavior.
- `explain_task.py`: explain current task truth for operator review.
- `extract_json.py`: extract one trustworthy lead-review JSON object from mixed model output.
- `manage_assets.py`: validate and synchronize async asset manifests.
- `models.py`: Pydantic models for Ralph state, task records, and lead review schema.
- `next_task.py`: choose the next pending task from `tasks.json`.
- `ralph_bot.py`: Telegram bot for monitoring and remote control.
- `ralph_common.py`: shared helpers for project, tasks, control state, and task truth.
- `ralph_notify.py`: send Telegram notifications from shell/runtime.
- `ralph_tail.sh`: tail latest coder and/or lead temp output files.
- `re_audit_tasks.py`: re-audit completed tasks against current repo truth.
- `reopen_tasks.py`: reopen or reclassify a task for manual review.
- `run_benchmark.py`: compare Ralph auto execution time against an estimated manual baseline.
- `run_eval.py`: run a minimal offline eval from JSON fixtures.
- `trust_score.py`: compute auto-pilot trust score from recent audit reviews.
- `update_memory.py`: update `.ralph/memory/recent.md` with latest task summary.
- `update_progress.py`: append an entry to `progress.md`.
- `update_task.py`: update task status in `tasks.json`.
- `verify_task_closure.py`: run trust-layer verification before task closure.
- `write_article.sh`: generate article drafts from recent project context and commits.

### `tasks.json` summary
- Total tasks: `152`
- `done`: `68`
- `verified_done`: `54`
- `false_positive`: `21`
- `pending`: `9`
- No tasks currently marked `blocked` in `tasks.json`.

### `.ralph/audit/` summary
- Audit JSON files: `31`
- Last 3 audit files:
  - `R15-02.json`: valid JSON, top-level keys are task/audit metadata with nested `review.parsed`; no top-level `approved`; no top-level `checklist`; `status=failed`.
  - `R15-04.json`: same structure pattern; `status=blocked`.
  - `R15-01.json`: same structure pattern; `status=blocked`.
- Current audit artifact shape is richer than the simple trust-score input contract. Review outcome lives under `review.parsed`, not at top level.

### `tests/` summary
- Test files matching `tests/test_*.py`: `19`
- Total discovered test functions: `172`
- Largest file: `tests/test_integration.py` with `70` tests.

## Trust Layer Status

Command run:

```bash
python3 scripts/trust_score.py --audit-dir .ralph/audit --window 20
```

Output:

```json
{"trust_score": 0.0, "window": 20, "tasks_evaluated": 20, "details": [{"file": "OPS-13.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "OPS-14.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "JOUR-01.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R12-01.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R12-01b.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R12-03.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "OPS-10.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "BUG-03.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R13-06.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R13-01.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R13-03.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R13-04.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R13-07.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R13-05.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "BUG-05.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R14-02.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R14-03.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R15-02.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R15-04.json", "approved": false, "has_checklist": false, "task_score": 0.0}, {"file": "R15-01.json", "approved": false, "has_checklist": false, "task_score": 0.0}]}
```

Assessment:
- The trust layer is wired into `ralph.sh`, but the reported score is currently not decision-useful.
- Root cause: `trust_score.py` expects top-level `approved` and optional top-level `checklist`, while actual audit artifacts store lead output under `review.parsed`.
- Result: recent tasks all evaluate as `approved=false`, producing `0.0/100`.

## External Readiness

### a) Can `ralph.sh` run outside its own repo?
Yes, with constraints.

- `ralph.sh` is designed around `RALPH_DIR` for runtime assets and `PROJECT_DIR` for the target project.
- It discovers the project by checking `./tasks.json` first, then `$RALPH_DIR/../tasks.json`.
- This supports two usage patterns:
  - run from a target project directory that already contains `tasks.json`;
  - place Ralph in a subdirectory such as `.ralph/` and run it from there or from the project root.
- It is not fully location-agnostic in the abstract sense; it assumes a packaged Ralph directory plus a neighboring project or a current working directory with `tasks.json`.

Conclusion: external use is supported, but the intended model is “clone/package Ralph into a target repo”, not “single shell script dropped anywhere”.

### b) Does `ralph.sh` require specific files in the target project?
Hard requirement:
- `tasks.json`

Operationally expected and created by `ralph-init.sh`:
- `AGENTS.md`
- `ARCHITECTURE.md`
- `MEMORY_SYSTEM.md`
- `AGENTS_CODER.md`
- `AGENTS_LEAD.md`
- `progress.md`
- `.ralph/memory/core.md`
- `.ralph/memory/recent.md`

Behavior notes:
- Some of these are soft-optional at runtime because prompt loaders check `-f` before reading.
- In practice, prompts explicitly reference project docs, and README positions them as part of the standard setup.
- Core execution also assumes the target project has a working `make test` command, because the main loop runs `make test` after coder output.

### c) Is there an install/setup script or pip package?
Yes, both exist.

- Setup/init script:
  - `ralph-init.sh`
  - packaged copy: `src/ralph/resources/ralph-init.sh`
- Python packaging:
  - `pyproject.toml`
  - `setup.py`
  - CLI entrypoint: `ralph = ralph.cli:main`
  - implemented in `src/ralph/cli.py`

Current maturity:
- There is a real package layout and packaged resources.
- README still documents the `.ralph/` clone workflow as the primary path.
- Packaging exists, but the project still describes itself as active MVP with “richer multi-project support” pending.

### d) Minimum setup to point Ralph at a fresh Python project
Minimum practical setup:
1. Put Ralph into the target project, either by package install or by cloning/copying it into `.ralph/`.
2. Run `ralph-init.sh` or `ralph init` from the target project.
3. Ensure the target project has:
   - `tasks.json`
   - `AGENTS.md`
   - `ARCHITECTURE.md`
   - `MEMORY_SYSTEM.md`
   - `AGENTS_CODER.md`
   - `AGENTS_LEAD.md`
   - `progress.md`
   - `.ralph/memory/*`
4. Ensure runtime dependencies exist:
   - Python `>=3.9`
   - `python-dotenv`
   - Codex CLI available as `codex`
   - `make test` implemented and passing or at least runnable
5. Optionally configure `.env` for Telegram if remote control/notifications are needed.

Bottom line:
- For a fresh Python repo, Ralph is close to usable externally if you accept the repo-scaffold model.
- The minimum setup is not zero-config; it is scaffold + task file + docs + working test command + Codex CLI.

## Gaps & Recommendations

### Main gaps
- Trust-score input mismatch: audit artifacts do not expose top-level `approved` and `checklist`, so the current trust score collapses to zero.
- Verification command is hardcoded to `make test`, which limits portability across projects without a Makefile.
- External setup still leans on repo cloning/scaffolding rather than a cleaner install-and-init flow.
- Documentation claims project-agnostic behavior, but success still depends on a specific repo contract: task file, prompt docs, memory files, and Make-based verification.
- Audit and trust layers are promising but not yet normalized into a stable external API/schema.

### Recommendations
1. Normalize audit schema so `approved` and `checklist` are always available at top level, or teach `trust_score.py` to read `review.parsed`.
2. Make the verification command configurable per project, for example via `.env`, `tasks.json`, or a Ralph config file, instead of hardcoding `make test`.
3. Publish one supported external workflow and reduce ambiguity:
   - either package-first: `pip install ralph-dev && ralph init`
   - or repo-vendored: clone into `.ralph` and run `./.ralph/ralph-init.sh`
4. Add a readiness check command that validates `codex`, `make test`, required docs, Telegram env vars, and repo layout before first run.
5. Document the minimum supported target-project contract explicitly, especially the expectation around `tasks.json`, prompt docs, and verification command.

Overall assessment:
- Internally, Ralph already has substantial orchestration capability.
- For external users, it is usable by advanced operators today, but not yet polished enough to be called plug-and-play.
