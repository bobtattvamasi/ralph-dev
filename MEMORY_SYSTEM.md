# Ralph Memory System

## Purpose
Ralph keeps lightweight persistent memory across tasks so the agent loop does
not start from zero on every run.

## Memory Layers
- `core.md` — stable project context: architecture, stack, conventions, constraints
- `recent.md` — short history of the last approved tasks
- `patterns.md` — recurring error patterns and working fixes
- `decisions.md` — architectural and product decisions worth preserving

## Injection Policy
Before each coder run, Ralph reads and injects:
- `.ralph/memory/core.md`
- `.ralph/memory/recent.md`

This gives the coding agent project context plus short-term history.

## Update Policy
- `core.md` — maintained manually by project owners
- `recent.md` — updated automatically after approved tasks
- `patterns.md` — intended for recurring failure learnings
- `decisions.md` — intended for durable architecture decisions

## Current Implementation Status
- `core.md` and `recent.md` are actively used by `ralph.sh`
- `recent.md` is updated by `scripts/update_memory.py`
- `patterns.md` and `decisions.md` exist as placeholders and are not yet automatically maintained

## Design Constraints
- markdown files instead of a database
- repo-local storage for portability
- low operational overhead
- readable and editable by humans
