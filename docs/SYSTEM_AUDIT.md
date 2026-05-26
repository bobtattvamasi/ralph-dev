# System Audit

## Purpose
This document is a release-stage audit of what Ralph can do today, what is
only documented, what is still missing, and what should be built next before a
real-project pilot.

Audit baseline:
- installed CLI through `pipx`
- Python 3.11+
- local release-candidate smoke passed
- hosted GitHub Actions package smoke still blocked by billing

## Current CLI Surface

| Command | Read-only | Writes project files | Executes agent/runtime work | Requires `tasks.json` | Requires `git` |
| --- | --- | --- | --- | --- | --- |
| `ralph init` | no | yes | no | no | no |
| `ralph status` | yes | no | no | yes | yes |
| `ralph doctor` | yes | no | no | yes | yes |
| `ralph verify` | yes | no | no | no | no |
| `ralph next` | yes | no | no | yes | no |
| `ralph explain` | yes | no | no | yes | no |
| `ralph groom` | yes | no | no | no | no |
| `ralph log` | yes | no | no | no | no |
| `ralph tail` | yes | no | no | no | no |
| `ralph task <ID>` | no | yes | yes | yes | yes |
| `ralph auto --safe` | no | yes | yes | yes | yes |
| `ralph bot` | no | yes | yes | yes | yes |

Notes:
- `ralph verify` checks the packaged `ralph.sh` and optional project-local shell parity files. It does not directly require `tasks.json`.
- `ralph groom` reads `docs/ACTIVE_BACKLOG.md` and optionally `docs/BACKLOG_POLICY.md`, not `tasks.json`.
- `ralph log` and `ralph tail` only need project-local `logs/ralph_*.log`.
- `ralph task <ID>`, `ralph auto --safe`, and `ralph bot` route into the runtime layer, so `git` and task backlog requirements are effectively runtime requirements rather than lightweight CLI-only checks.

## Supported Workflows

### 1. Install via pipx
Status: works and is locally smoke-validated.

Current supported path:
- install Ralph with `pipx`
- use Python 3.11+
- install from GitHub or a local checkout

What is proven:
- packaged resources resolve outside the repo root
- installed console script works for the current operator surface
- local reinstall/inject flow works for release-candidate smoke

What is not yet proven:
- hosted GitHub Actions package smoke
- hosted cross-platform CI

### 2. Initialize a New Project
Status: works.

Current supported path:
- run `ralph init <project-name>`
- Ralph writes the baseline files into the target directory
- the generated next steps point to `ralph task`, `ralph auto --safe`, and `ralph bot`

What this solves:
- new repo bootstrap into the Ralph operator workflow
- initial docs/templates/tasks scaffold

### 3. Initialize an Existing Project
Status: partially supported.

Current supported path:
- run `ralph init` inside an existing repo if you want Ralph baseline files added there
- then create or refine `tasks.json`
- then operate from project-local cwd with `ralph status`, `ralph doctor`, `ralph verify`, `ralph next`, and `ralph explain`

Current limitation:
- there is no dedicated existing-project import or analysis command
- task backlog preparation is still manual or operator-guided

### 4. Inspect Project Health
Status: works for the current read-only operator surface.

Current supported path:
- `ralph status`
- `ralph doctor`
- `ralph verify`
- `ralph next`
- `ralph explain`
- `ralph groom`
- `ralph log`
- `ralph tail`

What this covers:
- basic git/backlog visibility
- packaged/runtime shell verification
- queue explanation
- active backlog visibility
- log inspection

### 5. Run One Explicit Task
Status: supported, but not release-proven through hosted CI.

Current supported path:
- `ralph task <ID>`

What this means:
- Ralph hands execution to the runtime pipeline
- the task must already exist in `tasks.json`
- the workflow depends on repo-local runtime expectations, not just CLI packaging

### 6. Run Auto-Safe
Status: supported, but still a runtime-heavy workflow rather than a packaging-only one.

Current supported path:
- `ralph auto --safe`

What this means:
- Ralph selects safe work from the existing backlog
- the queue is intentionally narrow
- this is suitable only when the project backlog is already in a usable state

## What Is Implemented Vs Only Documented

### Implemented And Locally Proven
- installed CLI through `pipx`
- Python 3.11+ baseline
- `ralph init`
- `ralph status`
- `ralph doctor`
- `ralph verify`
- `ralph next`
- `ralph explain`
- `ralph groom`
- `ralph log`
- `ralph tail`
- package resource resolution outside repo root
- local release-candidate smoke path
- manual/operator-guided planning with ChatGPT feeding `tasks.json`

### Implemented But Not Fully Proven In Hosted CI
- installed package smoke in GitHub Actions workflow
- release tag flow for `v0.1.0`
- cross-platform confidence beyond local/macOS-oriented usage
- end-to-end operator confidence for a real-project pilot

### Only Documented Or Explicitly Deferred
- PyPI publishing
- hosted cross-platform CI confidence
- native Windows support outside a bash-capable environment

## Missing Or Incomplete Workflows

### Project Analysis Command
Missing.

There is no `ralph analyze` command and no equivalent implemented workflow for
repo inspection that produces an operator-facing assessment automatically.

### Automatic Task Proposal / Generation
Missing.

Ralph requires `tasks.json`, but task creation is still manual or
operator-guided. Automatic task generation is future work, not a current
system capability.

### Update Command
Missing.

Operators can update via `pipx install --force ...` or `pipx upgrade
ralph-dev`, but there is no dedicated `ralph update` command.

### Hosted CI Proof
Incomplete.

The package smoke workflow exists, but hosted GitHub Actions proof is still
blocked by account billing.

### Real-Project Pilot
Incomplete.

Local release-candidate smoke passed, but that is still not the same as a real
project using Ralph end-to-end under normal operator conditions.

### Windows Native Support
Missing.

Windows is currently treated as bash-capable / Git Bash only. Native
PowerShell or `cmd.exe` support is not a supported claim yet.

## Recommended Next Tasks
Priority order:

1. Unblock hosted GitHub Actions package smoke and capture the first hosted CI proof for the installed CLI path.
2. Prove the first `v0.1.0` release-tag flow end to end on top of the pushed branch, while keeping PyPI deferred.
3. Run a real-project pilot and document where operator workflow breaks, slows down, or needs clearer guardrails.
4. Design and implement a project analysis / task proposal workflow so new or existing repos do not depend entirely on manual `tasks.json` authoring.
5. Decide whether to add a dedicated update command or keep upgrade workflow external through `pipx`, then document the decision as product policy.

## References
- [README.md](../README.md)
- [INSTALL.md](INSTALL.md)
- [RELEASE.md](RELEASE.md)
- [PACKAGING_PLAN.md](PACKAGING_PLAN.md)
- [TELEGRAM.md](TELEGRAM.md)
- [ACTIVE_BACKLOG.md](ACTIVE_BACKLOG.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
