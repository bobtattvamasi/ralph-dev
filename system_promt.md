## Context: Neuromesh + Ralph

I'm Bogdan, AI/fullstack engineer building neuromesh — a modular AI agent 
engine (vector+graph RAG, tracing, multi-app). 

I have an automated dev system called "ralph" that orchestrates codex CLI 
to execute tasks from tasks.json. It has 3 agent roles:
- Coder (codex exec, writes code)
- Tech Lead (codex exec, reviews diffs)  
- Orchestrator (ralph.sh, bash script)

Control: Telegram bot (scripts/ralph_bot.py)
Tasks: tasks.json (JSON, not markdown)
Progress: progress.md
Agent docs: AGENTS.md (index), AGENTS_CODER.md, AGENTS_LEAD.md

Current state: ralph works for small tasks (DIAG series passed).
Large tasks (P5-T01) caused codex to hang. Adding timeout + diagnostics.

Key files: ralph.sh, scripts/ralph_bot.py, tasks.json, AGENTS.md
Stack: Python 3.11, FastAPI, FAISS, NetworkX, Streamlit, SQLite
Tests: pytest, 101 passing

My goal: develop neuromesh by sending telegram commands, 
monitoring progress, and iterating on the plan — 
like the harness approach from Anthropic/OpenAI articles.