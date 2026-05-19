# AGENTS.md — Ralph Dev

## Read First
- `ARCHITECTURE.md` — execution model, orchestration, runtime, and state
- `MEMORY_SYSTEM.md` — memory layers and update policy
- `tasks.json` — roadmap and task source of truth
- `progress.md` — lightweight narrative history only, not authoritative task truth

## General Rules
1. `ralph.sh` must stay project-agnostic.
2. All bash script paths use `$RALPH_DIR`.
3. All project paths use `$PROJECT_DIR`.
4. No external Python dependencies except `dotenv`.
5. Bash changes must pass `bash -n ralph.sh`.
6. Python changes must pass `python3 -c "import ast; ast.parse(...)"` where applicable.
7. Prefer repo-local state and configuration over machine-level assumptions.
8. Prefer narrow task execution over broad repo exploration: start from the known hot zone and expand only when evidence requires it.
9. Treat the runtime Tester phase as the authoritative test owner. Coder and Lead do not own full-suite execution.
10. Coder should rely on the eventual Tester report for authoritative verification and should not assume ad hoc full-test runs replace runtime evidence.
11. Lead should review diff plus tester evidence and should not demand full-suite proof unless the task acceptance explicitly requires it.

## Notes
- Ralph attaches to any repo that contains `tasks.json`.
- Telegram bot is the main human control surface.
- Persistent memory lives in `.ralph/memory/`.
- The effective execution pipeline is `Coder -> Tester -> Lead -> Verifier -> Finalizer`.
