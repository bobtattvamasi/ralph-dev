# Ralph Roadmap

## Now
- Finish hardening trust-layer and closure verification for generic implementation tasks.
- Remove remaining root/resource drift described in `BRITTLENESS_AUDIT.md`.
- Stabilize macOS shell/runtime behavior and host-tool assumptions.
- Keep task schema, packaged resources, and integration tests in sync.
- Clarify current multi-project support level in docs vs code.

## Next
- Stronger verification rules for code-feature/config tasks. Evidence: `docs/TASK_VERIFICATION_POLICY.md`
- Shared parser / verifier / bot implementations instead of duplicated packaged copies. Evidence: `BRITTLENESS_AUDIT.md`
- Better operator tooling around explain/reopen/re-audit workflows. Evidence: `scripts/explain_task.py`, `scripts/reopen_tasks.py`
- Centralized config/defaults and reduced shell magic-number spread. Evidence: `scripts/ralph_common.py`, `BRITTLENESS_AUDIT.md`
- More direct tests for notification, memory update, prompt-budget tooling, benchmark helpers. Evidence: `BRITTLENESS_AUDIT.md`

## Later
- Richer multi-project support. Evidence: `README.md`, `scripts/manage_projects.py`
- More advanced retrieval/routing. Evidence: `README.md`
- Parallel execution. Evidence: `tasks.json` phase planning mentions R4 parallel ideas
- Production-readiness features from later phases R5-R13
- Conversational/chat mode and self-evolution workflows from later phases

## Open questions
- Should `verified_done` fully replace `done` for new completions?
- Is multi-project mode officially supported or still experimental?
- Should packaged resources continue as copied files or become imported modules?
- What is the authoritative minimum host environment for overnight runs on macOS?
- How strong should automatic closure verification become before human review is mandatory?

## Suggested priority order

| Priority | Item | Why | Dependencies | Risk | Suggested first task |
| --- | --- | --- | --- | --- | --- |
| P0 | Remove root/resource drift | Current architecture can behave differently in repo vs packaged mode | None | High | Unify `scripts/extract_json.py` and `scripts/verify_task_closure.py` with packaged copies |
| P0 | Harden auto mode environment checks | Overnight runs depend on host tools and shell behavior | None | High | Add preflight command that validates `python3`, `git`, `codex`, `gtimeout`, shell requirements |
| P1 | Expand verification for generic implementation tasks | Current verifier is partial and trust depends on it | Trust-layer base already exists | High | Add explicit code-feature verification rules in `scripts/verify_task_closure.py` |
| P1 | Clarify multi-project support contract | Docs and code currently disagree | Registry code already exists | Medium | Document supported MVP behavior for `scripts/manage_projects.py` and `/projects` |
| P1 | Reduce monolithic shell logic | `ralph.sh` is large and hard to reason about | Need parity tests | Medium | Extract prompt/review/verification helpers into Python modules |
| P2 | Improve operator truth surfaces | Three truth layers are powerful but cognitively heavy | Audit tools already exist | Medium | Add a consolidated explain/report command |
| P2 | Strengthen notification and control-path observability | Hidden bot/control failures degrade unattended use | Shared helpers exist | Medium | Add tests and stderr/log surfacing for `scripts/ralph_notify.py` and control parse failures |
| P2 | Stabilize timing-sensitive integration tests | Long-term CI confidence depends on this | Existing tests | Medium | Reduce reliance on file markers and wall-clock sleeps in `tests/test_integration.py` |

