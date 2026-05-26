# Ralph

Ralph is a project-agnostic AI execution layer for software delivery work.
It gives an operator-facing CLI for running an existing task backlog through an
AI-assisted workflow instead of treating the repository as a one-off prompt.

Ralph is useful when you already know what work should be done, want that work
tracked in `tasks.json`, and want a repeatable operator flow for checking repo
state, selecting the next task, and running scoped agent work.

## What Problem Ralph Solves
Ralph is meant for repositories where ad hoc prompting is no longer enough.
It adds:

- a project-local task backlog in `tasks.json`
- an installed CLI for operator workflows
- a runtime pipeline that can execute agent work against one task at a time
- a consistent way to inspect backlog state before and after agent runs

Ralph does not replace project planning by itself. It executes a task workflow
once the operator has prepared tasks and project context.

## Current Status
Ralph is at a local release-candidate smoke stage for installed CLI usage.

What is working now:
- install via `pipx` with Python 3.11+
- `ralph init` for bootstrapping a new project
- project-local `ralph status`, `ralph doctor`, `ralph verify`, `ralph next`, and `ralph explain`
- installed CLI usage without leaking internal package paths
- local release-candidate smoke for packaging and operator commands
- manual/operator-guided planning with ChatGPT helping define phases and tasks

What is not proven yet:
- hosted GitHub Actions package smoke is currently blocked by billing
- hosted cross-platform CI proof is still missing
- PyPI publishing is intentionally deferred

## Install
Ralph supports Python 3.11+.
Python 3.9 is unsupported.

Install with `pipx` from GitHub:

```bash
python3.11 -m pip install --user pipx
python3.11 -m pipx ensurepath
python3.11 -m pipx install --python python3.11 git+https://github.com/<OWNER>/<REPO>.git
```

Install from a local checkout:

```bash
cd /path/to/ralph-dev
python3.11 -m pipx install --python python3.11 .
```

## Update
Reinstall from a local checkout after pulling changes:

```bash
cd /path/to/ralph-dev
git pull --ff-only
python3.11 -m pipx install --force --python python3.11 .
```

Upgrade a GitHub-installed package:

```bash
python3.11 -m pipx upgrade ralph-dev
```

Install from a release tag:

```bash
python3.11 -m pipx install --python python3.11 \
  git+https://github.com/<OWNER>/<REPO>.git@v0.1.0
```

More detail:
- [docs/INSTALL.md](docs/INSTALL.md)
- [docs/RELEASE.md](docs/RELEASE.md)

## New Project
Use Ralph in a new project when you want it to create the baseline files and
show the next operator steps.

```bash
ralph init demo-project
cd demo-project
```

After init:
- review the generated docs and config files
- create or refine `tasks.json`
- run `ralph status`
- run `ralph doctor`
- run `ralph next` and `ralph explain` before starting agent execution

## Existing Project
Use Ralph in an existing project by running it from the project directory that
contains `tasks.json`.

```bash
cd /path/to/project
ralph status
ralph doctor
ralph verify
ralph next
ralph explain
```

If you are outside the target repo, use `--project-dir`:

```bash
ralph status --project-dir /path/to/project
ralph doctor --project-dir /path/to/project
ralph verify --project-dir /path/to/project
```

## tasks.json
Ralph needs tasks to run.

Today that means:
- the target project needs a `tasks.json`
- task creation is manual or operator-guided
- task quality matters because Ralph executes what is written there

Ralph does not currently promise automatic project analysis or automatic task
generation as a default workflow. That is future workflow territory unless it
is explicitly implemented and documented later.

## Core Commands
Read-only or low-risk operator commands:
- `ralph status` — summarize project and backlog state
- `ralph doctor` — run operator health checks for the target project
- `ralph verify` — run verification-oriented checks for the target project
- `ralph next` — show the next candidate task
- `ralph explain` — explain task selection
- `ralph groom` — read backlog-facing docs and surface operator context
- `ralph log` — inspect runtime logs
- `ralph tail` — tail current or recent runtime output

Commands that execute or start agent work:
- `ralph task <ID>` — run one explicit task
- `ralph auto --safe` — run the safe unattended queue
- `ralph bot` — start the optional Telegram control/observation layer

Bootstrap command:
- `ralph init` — create the Ralph baseline for a new project

## Command Examples
Bootstrap a new project:

```bash
ralph init demo-project
```

Inspect an existing project:

```bash
cd /path/to/project
ralph status
ralph doctor
ralph verify
```

Inspect task selection:

```bash
ralph next
ralph explain
```

Run one task:

```bash
ralph task R26-10
```

Run safe unattended work:

```bash
ralph auto --safe
```

## What Is Intentionally Not Ready Yet
- no PyPI publishing workflow yet
- no claim that hosted GitHub Actions package smoke is green today
- no hosted cross-platform CI proof yet
- no claim of native Windows PowerShell or `cmd.exe` runtime support
- no claim that Ralph automatically analyzes a repo and generates a full task plan
- no claim that commands like `ralph analyze` or `ralph plan` exist

## Related Docs
- [docs/INSTALL.md](docs/INSTALL.md) — install and day-to-day usage
- [docs/RELEASE.md](docs/RELEASE.md) — release tag flow and local RC smoke
- [docs/PACKAGING_PLAN.md](docs/PACKAGING_PLAN.md) — packaging model and install path
- [docs/PILOT.md](docs/PILOT.md) — first real-project test and manual planning workflow
- [docs/SYSTEM_AUDIT.md](docs/SYSTEM_AUDIT.md) — implemented vs future capability audit
- [docs/TELEGRAM.md](docs/TELEGRAM.md) — optional Telegram control/observation reference
- [docs/ACTIVE_BACKLOG.md](docs/ACTIVE_BACKLOG.md) — current stage and release blockers
- [ARCHITECTURE.md](ARCHITECTURE.md) — execution model and runtime architecture
