# Session Notes - 2026-03-02

## What happened
- /auto mode tested end-to-end: 5/5 tasks completed successfully
- Fixed 3 critical hanging bugs in ralph.sh execution pipeline
- Root causes: tee PID loss, bash wait on background codex, cat blocking on open FD

## Current state
- ralph.sh: fully synchronous codex execution via gtimeout
- ralph_bot.py: UTF-8 safe log reading, safe /stop with child kill
- All 18 unit tests passing
- /auto successfully completes full task cycle

## Known limitations
- /tail shows stale file when codex is running synchronously (no live streaming)
- gtimeout required (brew install coreutils on macOS)

## Next steps
- Apply ralph to real project (geoceph.ai frontend)
- Add live progress streaming during codex exec
- Add /cost tracking per session

# Session Notes - 2026-03-03 (Planning)

## Research findings applied
- Perplexity analysis of multi-agent orchestration best practices (2025-2026)
- Key sources: Anthropic context engineering, Factory.ai, Nubank/Devin, Spotify agents, Amazon eval

## Decisions made
- Keep sequential pipeline (coder→lead), correct for our use case
- Add .ralph/memory/ system for cross-task context (highest ROI improvement)
- Add circuit breaker (3 failures → stop) and exponential backoff
- Add model routing: simple→codex-mini, complex→codex-max
- Add agent_suitable field for task classification
- Vector DB and parallel execution deferred to R4 (future)
- Magentic/group-chat patterns not needed at current scale

## Priority order for implementation
1. R1-14: Exponential backoff + rate limit detection (blocker for overnight runs)
2. R1-13: Circuit breaker (prevent runaway failures)
3. R3-08: Memory system (highest ROI for agent quality)
4. R3-09: Structured task summaries (feeds memory system)
5. R3-10: Model routing + complexity field (free optimization)
6. R2-01..R2-09: Bot UX improvements
7. R3-11: Agent-suitable classification
8. R4-05, R4-06: Vector DB, parallel (future)

## Current state
- 40-task wasteland calculator completed successfully
- 10-task polish batch completed
- /stop now properly resets state (fixed this session)
- Git safety (GIT_EDITOR=true) added to codex subshells
- Orphan PID cleanup on bot startup added
- Graceful stop with 30s timeout implemented
