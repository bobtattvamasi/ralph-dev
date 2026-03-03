## [0.4.0] - 2026-03-02

### Fixed
- Removed tee/process substitution that caused PID tracking loss
- Replaced background codex exec (& + wait) with fully synchronous gtimeout
- Removed blocking cat on codex output files (FD held open by child processes)
- Fixed UTF-8 decode crash in /log and /cost commands (errors='replace')
- Replaced setsid with macOS-compatible kill_tree (setsid not available on macOS)

### Removed
- scripts/run_codex.sh (intermediate wrapper, no longer needed)
- run_with_timeout() function from ralph.sh

### Architecture
- codex exec now runs synchronously: gtimeout --foreground --kill-after=10
- No background processes, no wait, no pipes
- /stop kills ralph.sh PID which gtimeout propagates to codex

## [0.5.0] - 2026-03-03 (Planning)

### Added
- 8 new tasks: circuit breaker, exponential backoff, memory system,
  structured summaries, model routing, agent classification, vector DB, parallel
- Enhanced task schema: complexity, required_context, agent_suitable fields
- Memory system design (.ralph/memory/)
- Research-backed architecture decisions documented

### Changed
- Task priorities reordered based on Perplexity research analysis
- AGENTS.md updated with memory system, circuit breaker, model routing docs
