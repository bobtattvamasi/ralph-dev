# Project GPT Context

## Purpose
This file is the compact source pack entrypoint for ChatGPT Project / Custom
GPT usage.

It is meant to tell future assistant sessions the current truth about Ralph
without requiring every repo document to be uploaded as a source.

## Current Ralph Status
- Ralph is a project-agnostic AI execution layer for software delivery work.
- Ralph now works as an installed CLI-enabled system, not only as a repo-local shell flow.
- The bash runtime still matters: `ralph.sh` remains the runtime controller.
- Packaged runtime resources live under `src/ralph/resources/`.
- The installed CLI is the default operator entrypoint.
- Telegram is still supported, but only as an optional control/observation layer.

## Python And Install Baseline
- Python baseline is 3.11+.
- Do not assume local `python3` is valid for packaging or CLI checks because it may resolve to 3.9.
- Primary install/update path is `pipx`.

Current install/update flows:
- `python3.11 -m pipx install --python python3.11 git+https://github.com/<OWNER>/<REPO>.git`
- `python3.11 -m pipx install --python python3.11 .`
- `python3.11 -m pipx install --force --python python3.11 .`
- `python3.11 -m pipx upgrade ralph-dev`
- `python3.11 -m pipx inject ralph-dev pytest`

## Installed CLI Command Surface
Current supported operator commands:
- `ralph init`
- `ralph status`
- `ralph doctor`
- `ralph verify`
- `ralph next`
- `ralph explain`
- `ralph groom`
- `ralph log`
- `ralph tail`
- `ralph task <ID>`
- `ralph auto --safe`
- `ralph bot`

## Planning Model
- Ralph is task-driven.
- Ralph executes tasks already written in `tasks.json`.
- Current planning is manual/operator-guided.
- The operator describes the project goal to ChatGPT.
- ChatGPT helps create phases and tasks.
- The operator writes and commits `tasks.json`.
- Ralph executes the backlog from `tasks.json`.

Current non-capabilities:
- `ralph analyze` is not an implemented command.
- `ralph propose-tasks` is not an implemented command.
- Automatic project analysis is future workflow.
- Automatic task generation is future workflow.

## First Pilot Workflow
Current first real-project test model:
- choose a separate throwaway/simple webapp repo
- install or update Ralph through `pipx`
- run `ralph init`
- run `ralph status`
- run `ralph doctor`
- run `ralph verify`
- run `ralph next`
- run `ralph explain`
- write `tasks.json` through manual planning with ChatGPT
- run exactly one explicit `ralph task <ID>` first
- inspect `git diff`, logs, `tasks.json` status, and `progress.md`
- only then try `ralph auto --safe`

## Local RC Smoke Status
Local release-candidate smoke passed.

Known local checks:
- `python3.11 -m pytest tests/test_cli_packaging.py -q`
- `python3.11 -m pytest tests/test_ralph_cli.py -q`
- `python3.11 -m ralph.cli verify`
- `python3.11 -m pipx install --force .`
- `python3.11 -m pipx inject ralph-dev pytest --force`

## Current Limits And Honesty Rules
- GitHub Actions package smoke workflow exists, but hosted proof is currently blocked by billing.
- Hosted cross-platform CI proof is still missing.
- `v0.1.0` tag flow is documented, but release proof is still not complete.
- PyPI publishing is deferred.
- Native Windows support is not a current claim; bash-capable / Git Bash is the current ceiling.
- `build/`, `dist/`, and `*.egg-info` artifacts must not be committed.

## Project GPT Sources To Upload
Required:
- `docs/GPT_PROJECT_CONTEXT.md`
- `AGENTS.md`
- `AGENTS_CODER.md`
- `AGENTS_LEAD.md`
- `ARCHITECTURE.md`

Optional:
- `README.md`
- `docs/INSTALL.md`
- `docs/PILOT.md`
- `docs/SYSTEM_AUDIT.md`
- `docs/TELEGRAM.md`
- `docs/ACTIVE_BACKLOG.md`

## Do Not Upload By Default
- `tasks.json`
- `logs/`
- `build/`
- `dist/`
- `*.egg-info`

## Recommended Assistant Behavior
- Treat `README.md` as the public/operator entrypoint.
- Treat `ARCHITECTURE.md` and agent docs as the implementation/policy truth.
- Do not claim hosted CI is green.
- Do not claim PyPI release exists.
- Do not claim automatic planning/analyze/propose-task workflows exist.
- Prefer concise, operator-facing guidance over broad repo theory.
