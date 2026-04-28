# Ralph Decisions

## Existing decisions

| Decision | Context | Evidence in repo | Consequences | Revisit when |
| --- | --- | --- | --- | --- |
| Shell orchestrator is the primary runtime | Keep repo-local, low-overhead execution without backend service | `ralph.sh`, `README.md`, `ARCHITECTURE.md` | Fast to iterate, but monolithic and host-tool sensitive | When orchestration logic becomes too large to maintain safely |
| Telegram is the main control plane | Remote operator control is required | `scripts/ralph_bot.py`, `README.md` | Strong operator UX, but shared-file coordination is critical | When multiple operators or richer auth/routing are needed |
| Two-agent loop (`Coder` + `Tech Lead`) is core workflow | Separate implementation from review | `README.md`, `ralph.sh`, `templates/AGENTS_CODER.md`, `templates/AGENTS_LEAD.md` | Better gatekeeping than single-agent execution; more runtime complexity | When review quality or latency becomes a bottleneck |
| State is repo-local file state, not DB-backed | Portability and inspectability are favored | `MEMORY_SYSTEM.md`, `scripts/ralph_common.py` | Human-readable, easy to copy; races/drift must be managed | When concurrency or scale makes file coordination too fragile |
| Verification-before-closure is required | Runtime success is not enough | `docs/TRUST_LAYER.md`, `scripts/verify_task_closure.py` | Fewer false positives; more blocked/fix outcomes | When generic code-feature verification is stronger |
| Audit artifacts are a first-class truth layer | Need inspectable latest-run truth | `scripts/audit_artifact.py`, `docs/AUDIT_WORKFLOW.md` | Better diagnostics; more truth layers for operators to reason about | When operator surface can unify truth views |
| Re-audit is conservative and dry-run first | Historical backlog truth should not be mass-mutated automatically | `scripts/re_audit_tasks.py`, `docs/TRUST_LAYER.md`, `docs/STATUS_MODEL.md` | Safer trust restoration; more manual steps | When repo-truth heuristics are proven reliable |
| Memory is Markdown files in `.ralph/memory/` | Keep context editable and repo-local | `MEMORY_SYSTEM.md` | Simple and transparent; limited structure | When retrieval or scale demands richer storage |
| Prompt shaping uses narrow vs broad modes | Control token budgets and context relevance | `ralph.sh`, `scripts/check_prompt_budgets.py`, tests in `tests/test_integration.py` | Better budget discipline; complexity in prompt assembly | When prompt assembly moves to structured modules |
| High-risk tasks require human gate | Some changes should not auto-land | `ralph.sh` | Safer unattended runs; added operator latency | When risk scoring is better specified |

## Implied decisions
- Packaged CLI should behave the same as root repo runtime. Evidence: `src/ralph/cli.py`, `tests/test_cli_packaging.py`
- Shared mutation helpers should use file locks and atomic writes. Evidence: `scripts/ralph_common.py`
- `tasks.json` remains scheduler truth even when audit/re-audit disagree. Evidence: `docs/TRUST_LAYER.md`
- Operator-facing helper scripts are considered part of product surface, not just internal tooling. Evidence: `scripts/explain_task.py`, `scripts/reopen_tasks.py`, `scripts/bot_smoke_check.py`

## Conflicts / inconsistencies
- README says richer multi-project support is future work, but project registry and `/projects` `/switch` commands already exist.
  - Evidence: `README.md`, `scripts/manage_projects.py`, `scripts/ralph_bot.py`
- README says packaging remains future work, but packaged CLI and packaging tests already exist.
  - Evidence: `README.md`, `src/ralph/cli.py`, `tests/test_cli_packaging.py`
- Local instructions prefer Python 3.11+, but `pyproject.toml` only requires `>=3.9`.
  - Evidence: workspace instructions, `pyproject.toml`
- `ARCHITECTURE.md` describes `make test` as default verification gate, but this repo’s own `tasks.json` test command is syntax-check oriented.
  - Evidence: `ARCHITECTURE.md`, `tasks.json`
- `progress.md` says R1 complete and points to R2 next, but current `tasks.json` spans through R13 and current codebase is much broader.
  - Evidence: `progress.md`, `tasks.json`
- `MEMORY_SYSTEM.md` says `patterns.md` and `decisions.md` are placeholders, while trust/docs imply durable decision capture matters now.
  - Evidence: `MEMORY_SYSTEM.md`, `docs/TRUST_LAYER.md`

## Decisions needed next
- Officially define whether multi-project mode is MVP-supported or experimental.
- Decide whether `done` should remain writable for new successful tasks or whether only `verified_done` should be used.
- Decide whether packaged resources remain copied artifacts or are replaced with shared imports/build generation.
- Decide the minimum supported host environment for unattended macOS runs.
- Decide how strong generic implementation verification should be before auto-close is trusted broadly.
