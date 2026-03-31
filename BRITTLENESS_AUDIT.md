# 1. Root vs `src/ralph/resources/` Drift

## Critical
- `scripts/extract_json.py:12` vs `src/ralph/resources/scripts/extract_json.py:22`  
  Severity: critical  
  Description: packaged parser extracts the first JSON object, while root parser enforces a single trustworthy Tech Lead review with markers, placeholder filtering, and decision validation.  
  Suggested fix: remove duplicated implementations and make both entrypoints import the same parser module.

- `scripts/verify_task_closure.py:14` vs `src/ralph/resources/scripts/verify_task_closure.py:14`  
  Severity: critical  
  Description: trust-layer verification logic has materially diverged: bookkeeping allowlist differs, path extraction differs, docs/task-class heuristics differ, and packaged file even redefines `is_bookkeeping`.  
  Suggested fix: keep one verifier source and package it directly instead of copying.

## High
- `scripts/models.py:8` vs `src/ralph/resources/scripts/models.py:8`  
  Severity: high  
  Description: `RalphState.status` supports `blocked` in root but not in packaged resources, so installed/runtime validation can disagree on valid state.  
  Suggested fix: centralize the model definition and add a drift test that diffs exported literals.

- `scripts/ralph_bot.py:1075` vs `src/ralph/resources/scripts/ralph_bot.py:1075`  
  Severity: high  
  Description: root bot blocks `/auto` start when runtime state is `blocked`; packaged bot does not, so operator behavior differs between repo and packaged modes.  
  Suggested fix: share one bot implementation or generate packaged copies automatically during build.

## Medium
- `templates/AGENTS_CODER.md:16` vs `src/ralph/resources/templates/AGENTS_CODER.md:16`  
  Severity: medium  
  Description: local-first discipline exists only in root template, so packaged coder prompts miss the web-search constraint.  
  Suggested fix: sync template resources from a single source and add a packaging parity test.

## Low
- `ralph.sh` vs `src/ralph/resources/ralph.sh`  
  Severity: low  
  Description: no substantive diff was detected in the current snapshot.  
  Suggested fix: keep a parity check in CI so this stays true.

# 2. Duplicated Logic

## High
- `scripts/update_task.py:9`, `scripts/update_progress.py:9`, `scripts/next_task.py:9`  
  Severity: high  
  Description: project-dir resolution logic is duplicated across multiple scripts with slightly different fallback policies elsewhere (`scripts/explain_task.py:15`, `scripts/reopen_tasks.py:13`).  
  Suggested fix: move project-dir resolution into one shared helper module and import it everywhere.

- `scripts/next_task.py:21`, `scripts/update_task.py:29`, `scripts/re_audit_tasks.py:34`, `scripts/explain_task.py:27`, `scripts/ralph_bot.py:623`  
  Severity: high  
  Description: `tasks.json` loading/parsing is repeated across runtime, helpers, and bot with different validation and error behavior.  
  Suggested fix: create a shared task-store module with typed load/save helpers and one validation path.

- `ralph.sh:1077`, `ralph.sh:2214`, `scripts/ralph_bot.py:251`  
  Severity: high  
  Description: control-file semantics are duplicated across shell and bot: one path writes the file, another reads it, a third consumes and mutates it.  
  Suggested fix: define a single control-file schema and one atomic read/write helper used from both runtimes.

## Medium
- `scripts/verify_task_closure.py:60` and `scripts/re_audit_tasks.py:48`  
  Severity: medium  
  Description: task classification logic is split between verifier and re-audit; `re_audit_tasks.py` partly imports verifier helpers but still layers its own classification behavior on top.  
  Suggested fix: make re-audit call a single classification/verdict library instead of partially re-implementing it.

- `scripts/explain_task.py:31` and `scripts/next_task.py:26`  
  Severity: medium  
  Description: runnable/dependency reasoning exists in both scheduler and operator-explanation code.  
  Suggested fix: expose scheduler truth as a library function and reuse it in the explain tool.

## Low
- `scripts/ralph_bot.py:151` and `ralph.sh:1056`  
  Severity: low  
  Description: state normalization/write logic exists separately in Python bot and shell runtime, increasing schema-drift risk.  
  Suggested fix: move state schema and serialization into one shared helper or validate every write through the same model.

# 3. Hardcoded Paths / Values

## High
- `scripts/ralph_bot.py:1956`  
  Severity: high  
  Description: bot crash recovery runs hardcoded git rollback commands (`git reset`, `git checkout`) against the live project.  
  Suggested fix: gate rollback behind explicit operator approval and move command construction to a reviewed helper.

## Medium
- `ralph.sh:151`, `ralph.sh:152`, `ralph.sh:3100`, `ralph.sh:3753`  
  Severity: medium  
  Description: lead timeout and retry delays use scattered magic numbers (`300`, `60 120 300`, `120`) instead of one central constant/config block.  
  Suggested fix: consolidate runtime defaults into a single config section and reference named constants.

- `scripts/ralph_bot.py:931`, `scripts/ralph_bot.py:950`, `scripts/ralph_notify.py:31`  
  Severity: medium  
  Description: Telegram HTTP timeouts are hardcoded as `10` seconds in several places.  
  Suggested fix: promote transport timeout to a shared constant/env override.

- `scripts/ralph_bot.py:1523`  
  Severity: medium  
  Description: article-generation subprocess timeout is hardcoded to `300` seconds.  
  Suggested fix: use a named constant or env-configurable timeout.

## Low
- Repository-wide scan  
  Severity: low  
  Description: no hardcoded `/Users/...` paths or inline API keys were found in tracked source files; Telegram credentials are read from env.  
  Suggested fix: keep secret/path scans in CI to preserve this property.

# 4. Error Handling Gaps

## High
- `ralph.sh:2214`  
  Severity: high  
  Description: `get_human_comment()` uses `except: pass` and rewrites `ralph_control.json` without surfacing malformed JSON or write failures, so operator comments can be silently dropped.  
  Suggested fix: catch specific exceptions, log failures, and write atomically through a temp file.

- `scripts/ralph_notify.py:30`  
  Severity: high  
  Description: Telegram notification failures are swallowed with bare `except Exception: pass`, hiding delivery outages.  
  Suggested fix: log transport failures to stderr or a runtime log with throttling.

## Medium
- `scripts/ralph_bot.py:247`, `scripts/ralph_bot.py:1949`, `scripts/ralph_bot.py:1962`, `scripts/ralph_bot.py:1976`  
  Severity: medium  
  Description: several bot state/crash-recovery paths swallow exceptions without logging, making stale-state and rollback failures invisible.  
  Suggested fix: replace bare catches with logged, typed exception handling.

- `scripts/update_task.py:29`, `scripts/next_task.py:25`, `scripts/explain_task.py:28`, `scripts/reopen_tasks.py:41`, `scripts/run_benchmark.py:49`  
  Severity: medium  
  Description: `json.loads(...read_text())` is used without guarding malformed `tasks.json`, so a single bad write can crash operator helpers.  
  Suggested fix: wrap JSON parsing in a shared loader that emits structured errors.

- `ralph.sh:1082`  
  Severity: medium  
  Description: `read_control_file()` falls back to `continue` on any parse failure, which converts corrupted control state into silent no-op behavior.  
  Suggested fix: log invalid control payloads and preserve the bad artifact for inspection.

## Low
- `scripts/verify_task_closure.py:136`, `src/ralph/resources/scripts/verify_task_closure.py:147`  
  Severity: low  
  Description: `read_text()` returns `""` on any exception, conflating missing files, decode errors, and permission problems.  
  Suggested fix: return a typed result or propagate the reason alongside the content.

# 5. Race Conditions

## Critical
- `scripts/ralph_bot.py:251` and `ralph.sh:2214`  
  Severity: critical  
  Description: `ralph_control.json` is written by the bot and read-modify-written by `get_human_comment()` with no locking, so concurrent `/comment`, `/skip`, `/timeout`, and runtime consumption can overwrite each other.  
  Suggested fix: use atomic compare-and-swap or advisory file locking around all control-file mutations.

## High
- `scripts/ralph_bot.py:233` and `ralph.sh:1056`  
  Severity: high  
  Description: `ralph_state.json` is read and rewritten by both bot and shell without locking; bot stale-state reset can race with runtime `write_state()`.  
  Suggested fix: make state writes atomic across both processes and include a monotonic revision field before overwrite.

- `scripts/update_task.py:29`, `scripts/ralph_bot.py:1198`, `ralph.sh:4252`  
  Severity: high  
  Description: `tasks.json` is modified from multiple processes via read-modify-write with no lock, so concurrent `/done`, `/redo`, runtime closure, and re-audit can lose updates.  
  Suggested fix: add a file lock around all task mutations or move task updates behind one coordinator process.

## Medium
- `scripts/update_progress.py:29` and `ralph.sh:4253`  
  Severity: medium  
  Description: `progress.md` appends are non-atomic and can interleave or overwrite on concurrent writes.  
  Suggested fix: append via locked file handle or journal entries.

# 6. Test Coverage Gaps

## High
- `scripts/auto_update.py:1`  
  Severity: high  
  Description: no corresponding test file references this legacy status/commit mutator, despite it changing both task truth and narrative files.  
  Suggested fix: add direct tests or remove/deprecate the script.

- `scripts/ralph_notify.py:1`  
  Severity: high  
  Description: no tests cover Telegram notification behavior or error handling.  
  Suggested fix: add a small transport unit test with mocked `urlopen`.

## Medium
- `scripts/check_prompt_budgets.py:1`  
  Severity: medium  
  Description: no dedicated test covers prompt-budget validation logic even though it shells into runtime code.  
  Suggested fix: add a fixture-based CLI test.

- `scripts/update_memory.py:1`  
  Severity: medium  
  Description: no direct tests cover memory entry trimming, header preservation, or malformed input handling.  
  Suggested fix: add unit tests for `split_entries()` and end-to-end file updates.

- `scripts/update_progress.py:1`  
  Severity: medium  
  Description: no tests cover progress append formatting or missing-file bootstrap behavior.  
  Suggested fix: add a tiny CLI test using a temp project dir.

## Medium
- `ralph.sh:432`, `ralph.sh:480`, `ralph.sh:505`  
  Severity: medium  
  Description: handoff helper functions (`handoff_candidate_paths`, `handoff_worktree_evidence_paths`, `handoff_latest_repo_candidate_commit`) have only indirect integration coverage and no focused unit-style regression tests.  
  Suggested fix: extract handoff logic into a testable helper module or add shell integration cases per helper branch.

- `ralph.sh:2214`, `ralph.sh:2663`, `ralph.sh:2688`, `ralph.sh:2935`  
  Severity: medium  
  Description: key trust/control functions (`get_human_comment`, `validate_lead_review_json`, `parse_lead_review_json`, `run_task_closure_verification`) are not directly exercised by dedicated tests by name.  
  Suggested fix: add targeted integration tests for malformed control JSON, lead JSON disagreement, and verifier failures.

- `ralph.sh:3388`, `ralph.sh:3504`  
  Severity: medium  
  Description: shell benchmark writers/runners exist, but current direct coverage focuses on the end report, not the internal helper branches.  
  Suggested fix: add fixture-driven tests for benchmark helper edge cases.

# 7. Dead Code

## Medium
- `ralph.sh:592`  
  Severity: medium  
  Description: `handoff_unrelated_repo_backed_changes()` appears defined but never referenced in `ralph.sh`.  
  Suggested fix: remove it or wire it into handoff filtering with a focused test.

- `ralph.sh:838`  
  Severity: medium  
  Description: `is_completed_task_status()` appears defined but never referenced.  
  Suggested fix: remove it or replace duplicated completed-status checks with this helper.

- `ralph.sh:1383`, `ralph.sh:1970`, `ralph.sh:2811`, `ralph.sh:2858`  
  Severity: medium  
  Description: `clip_prompt_tokens()`, `extract_task_keywords()`, `task_scoped_name_only_between_refs()`, and `task_scoped_current_diff()` appear unreferenced in the shell script body.  
  Suggested fix: confirm they are truly unused, then delete or integrate them with tests.

## Low
- `scripts/ralph_bot.py:107`, `scripts/ralph_bot.py:127`, `scripts/ralph_bot.py:140`  
  Severity: low  
  Description: hot-reload helpers (`configure_module_runtime`, `load_bot_module_from_source`, `apply_hot_reload`) are weakly referenced and have no direct tests, which makes them look dead to static scans.  
  Suggested fix: either add a focused reload test or document the call path more explicitly.

