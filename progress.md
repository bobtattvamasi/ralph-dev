# Ralph Dev — Progress Log

## Current State
- **Phase**: R1 (Stability) ✅ COMPLETE
- **Completed**: R0-01, R0-02, R0-03, R0-04, R1-01, R1-02, R1-03, R1-04, R1-05
- **Next**: R2-01 (/plan command)

## Session Log

### 2026-02-26 — Initial setup
- R0-01: Created ralph-dev repo structure (manual)
- R0-02: Made ralph.sh project-agnostic (RALPH_DIR/PROJECT_DIR)
- R0-03: Added AGENTS.md and .gitignore
- R0-04: Created test-ralph-app (minimal Python project, 3 tests, ralph-init works)
- R1-01: Bot supports --project-dir arg and RALPH_PROJECT_DIR env var
- R1-02: Per-task timeout from tasks.json (default 180s, gtimeout uses task.timeout)
- R1-03: Added /cost command (token usage + cost estimate from daily logs)
- R1-04: /log shows ralph execution log tail, added /progress for progress.md
- R1-05: Added /tail command (live codex output with freshness indicator)
- R1 Phase Complete — all stability tasks done
