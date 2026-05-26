# AGENTS.md — Ralph Dev

## Read First
- `ARCHITECTURE.md` — execution model, orchestration, runtime, and state
- `docs/BACKLOG_POLICY.md` — backlog policy, status semantics, and active lane rules
- `MEMORY_SYSTEM.md` — memory layers and update policy
- `tasks.json` — roadmap and task source of truth
- `progress.md` — lightweight narrative history only, not authoritative task truth

## General Rules
1. `ralph.sh` must stay project-agnostic.
2. All bash script paths use `$RALPH_DIR`.
3. All project paths use `$PROJECT_DIR`.
4. Python baseline is 3.11+.
5. No external Python dependencies except `dotenv`.
6. Bash changes must pass `bash -n ralph.sh`.
7. Python changes must pass `python3 -c "import ast; ast.parse(...)"` where applicable.
8. Packaged runtime resources live under `src/ralph/resources/` and must stay aligned with repo runtime behavior.
9. Installed CLI and package-distribution work should prefer repo-local resources and console-script paths over machine-level assumptions.
10. Prefer repo-local state and configuration over machine-level assumptions.
11. Prefer narrow task execution over broad repo exploration: start from the known hot zone and expand only when evidence requires it.
12. Treat the runtime Tester phase as the authoritative test owner. Coder and Lead do not own full-suite execution.
13. Coder should rely on the eventual Tester report for authoritative verification and should not assume ad hoc full-test runs replace runtime evidence.
14. Lead should review diff plus tester evidence and should not demand full-suite proof unless the task acceptance explicitly requires it.

## Notes
- Ralph attaches to any repo that contains `tasks.json`.
- Telegram bot is the main human control surface.
- Installed CLI/package work should use `tests/test_cli_packaging.py` and `tests/test_ralph_cli.py` as the primary hot zone for coverage.
- Persistent memory lives in `.ralph/memory/`.
- The effective execution pipeline is `Coder -> Tester -> Lead -> Verifier -> Finalizer`.
