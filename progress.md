# Ralph Dev — Progress Log

## Current State
- **Phase**: R0 (Setup)
- **Completed**: R0-01, R0-02, R0-03, R0-04, R1-01, R1-02
- **Next**: R1-03 (/cost command)

## Session Log

### 2026-02-26 — Initial setup
- R0-01: Created ralph-dev repo structure (manual)
- R0-02: Made ralph.sh project-agnostic (RALPH_DIR/PROJECT_DIR)
- R0-03: Added AGENTS.md and .gitignore
- R0-04: Created test-ralph-app (minimal Python project, 3 tests, ralph-init works)
- R1-01: Bot supports --project-dir arg and RALPH_PROJECT_DIR env var
- R1-02: Per-task timeout from tasks.json (default 180s, gtimeout uses task.timeout)
