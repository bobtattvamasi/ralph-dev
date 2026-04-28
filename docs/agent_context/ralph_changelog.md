# Ralph Changelog

## Sources checked
- `git log --oneline --decorate -20`
- `CHANGELOG.md`
- `progress.md`
- `README.md`
- `tasks.json`

## Timeline

| Date / Period | Change | Source |
| --- | --- | --- |
| 2026-02-26 | Initial repo setup, project-agnostic `ralph.sh`, docs, test project, bot project-dir support, per-task timeout, `/cost` | `progress.md`, `tasks.json` |
| 2026-03-02 | Runtime switched to synchronous `gtimeout --foreground`; PID/tee/background fixes; macOS-friendly cleanup path | `CHANGELOG.md` |
| 2026-03-03 | Planning sprint: expanded roadmap across R1.5-R8, memory/circuit-breaker/model-routing decisions | `progress.md`, `CHANGELOG.md`, `tasks.json` |
| 2026-03-12 to 2026-03-16 | Multiple R2-R9 tasks landed according to progress log; details incomplete in narrative | `progress.md` |
| 2026-03-18 | Added `scripts/explain_task.py`, `scripts/reopen_tasks.py`, `scripts/bot_smoke_check.py`; improved Telegram diagnostics | `CHANGELOG.md` |
| 2026-03-19 to 2026-03-24 | R11/R12/OPS stabilization work around final state truth, reporting, eval harness, orphan tmp cleanup | `progress.md` |
| 2026-03-28 to 2026-03-31 | OPS-09, OPS-10, R13 hardening around budgets, retries, rollback, config centralization | `progress.md` |
| 2026-04-10 | R19-02 accepted: shell syntax checks before `make test`, better out-of-scope interpretation | `progress.md` |
| Recent commits before current HEAD | JSON extraction/trust fixes, verification debug logs, macOS awk compatibility updates | `git log --oneline --decorate -20` |
| 2026-04-27 / 2026-04-28 snapshot | Recent commits include `a959aaa`, `efce8e7`, `671f79d`, `f6b9712` for awk compatibility, verifier logging, task/template alignment | `git log --oneline --decorate -20` |

## Recent meaningful changes
- Trust layer tightened with authoritative review parsing and fail-closed behavior. Evidence: `scripts/extract_json.py`, `docs/TRUST_LAYER.md`, recent git log
- Verification gained detailed `target_files` mismatch diagnostics. Evidence: `scripts/verify_task_closure.py`, recent git log
- Scope warning payload from task selection is now structured. Evidence: `scripts/next_task.py`
- macOS/BSD awk compatibility work is active in `ralph.sh` and packaged copy. Evidence: recent git log, `ralph.sh`

## Unknowns
- Full detailed changelog between many `wip(...)` commits is not reconstructable from current sources alone.
- `progress.md` is narrative and incomplete for many March tasks.
- No single authoritative dated architecture migration log exists beyond `CHANGELOG.md` and commit history.
