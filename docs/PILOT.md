# Pilot Workflow

## Purpose
This document defines the first real-project test workflow for Ralph.

Current constraint:
- Ralph executes tasks already written in `tasks.json`
- manual planning is the supported workflow today
- `ralph analyze` and `ralph propose-tasks` are future automation ideas, not current commands

## Target Pilot Repo
Use a separate throwaway/simple webapp repo for the first pilot.

Why:
- the first test should isolate Ralph behavior from production risk
- a small webapp is easier to inspect by diff, logs, and task status
- throwaway scope makes it easier to stop quickly if runtime behavior is unclear

Recommended pilot characteristics:
- separate repository
- simple webapp or lightweight product slice
- clear git history
- small enough that one task diff can be reviewed manually

## Environment Setup
Install or update Ralph through `pipx` with Python 3.11+:

```bash
python3.11 -m pipx install --python python3.11 git+https://github.com/<OWNER>/<REPO>.git
```

Or, if testing from a local checkout:

```bash
cd /path/to/ralph-dev
python3.11 -m pipx install --force --python python3.11 .
```

## First Project Preparation
Inside the throwaway webapp repo:

```bash
ralph init
ralph status
ralph doctor
ralph verify
ralph next
ralph explain
```

What this should prove before any agent execution:
- installed CLI works from project cwd
- baseline files are present
- health/verification commands are readable
- queue state is understandable before runtime work starts

## Manual Planning Workflow
Manual planning is the supported path for the first pilot.

Current workflow:
1. Operator describes the project goal to ChatGPT.
2. ChatGPT helps break the project into phases and tasks.
3. Operator writes those tasks into `tasks.json`.
4. Operator reviews and commits `tasks.json`.
5. Ralph executes the backlog from `tasks.json`.

Important boundary:
- Ralph does not currently generate the project plan automatically
- Ralph does not currently create task proposals automatically
- `ralph analyze` is not a current command
- `ralph propose-tasks` is not a current command

## First Execution Rule
Do not start with unattended queue execution.

Run exactly one explicit task first:

```bash
ralph task <ID>
```

After that one task:
- inspect `git diff`
- inspect logs
- inspect `tasks.json` status changes
- inspect `progress.md`

Only after that review should you try:

```bash
ralph auto --safe
```

## Success Criteria
The first pilot is successful enough to continue when:
- CLI works from project cwd
- one explicit `ralph task <ID>` completes or blocks with a clear reason
- diff is scoped to the task `target_files`
- logs and `ralph status` output are readable
- `tasks.json` status and actual git diff tell the same story
- Telegram/bot observation can be used if it is configured

## Stop Criteria
Stop the pilot and inspect manually when:
- unrelated files are touched
- task status and git diff disagree
- failure reason is unclear
- internal package paths leak into user-facing output
- `ralph auto --safe` selects unexpected work

## Operator Notes
- Treat the first pilot as a supervised run, not a trust-the-queue run.
- Prefer a small initial task with tight `target_files`.
- Keep the first task easy to review by hand.
- If Telegram is configured, use it only as an observation/control surface, not as proof that the planning workflow is automated.

## What Comes Later
Future workflow areas, not current pilot assumptions:
- automatic project analysis
- automatic task generation
- richer pilot patterns after the first real-project test
- stronger hosted CI proof
