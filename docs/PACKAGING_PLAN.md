# Packaging Plan

## Goal
Stage `R24` is `Packaging Polish`.

The goal is to make Ralph reliable as an installed terminal tool, not only as a repo-local development checkout.

## Target Install And Use Flow
Preferred operator flow:
- install Ralph into a dedicated `venv`
- or install Ralph via `pipx`
- expose the `ralph` console script from the installed package
- run `ralph` from an arbitrary project directory that contains `tasks.json`
- use `--project-dir` consistently whenever the target project is not the current shell cwd

Expected properties:
- packaged resources resolve without depending on repo cwd
- `ralph` works when invoked outside the Ralph source repository
- the installed console script is the canonical entrypoint
- project-scoped operations read the target repo through `--project-dir`

## Target Operator Examples
Example install flows:
- `python3 -m venv .venv && .venv/bin/pip install .`
- `pipx install .`

Example usage from another project directory:
- `ralph status --project-dir /path/to/project`
- `ralph doctor --project-dir /path/to/project`
- `ralph auto --safe --project-dir /path/to/project`
- `ralph task R20-22 --project-dir /path/to/project`

## Console Script Expectations
The installed `ralph` console script should:
- dispatch through the packaged Python entrypoint
- use packaged resources rather than assuming repo-root relative paths
- preserve exit codes from wrapped commands
- keep operator commands read-only unless the wrapped runtime command is intentionally stateful

## Current Smoke Matrix
Current command surface to smoke in installed mode:
- `ralph doctor`
- `ralph status`
- `ralph verify`
- `ralph next`
- `ralph explain`
- `ralph groom`
- `ralph tail`
- `ralph log`
- `ralph auto --safe`
- `ralph task <ID>`

What each smoke should prove:
- `doctor`: packaged command can run basic repo health checks
- `status`: packaged command can summarize git state, task counts, duplicate IDs, and next auto-safe state
- `verify`: packaged command can run shell syntax checks and shell parity
- `next` / `explain`: installed selector path works without repo-root hacks
- `groom`: packaged command can read docs from the target project
- `tail` / `log`: installed command can discover and read runtime logs
- `auto --safe`: console script can delegate to packaged runtime safely
- `task <ID>`: explicit task execution path works through the installed entrypoint

## Repo-Local Vs Installed-Mode Gaps
### Packaged Resource Paths
Gaps to close:
- confirm every CLI path resolves through packaged resources
- avoid accidental dependence on checkout-relative paths
- verify `resource_path(...)` coverage for all shipped helpers

### Scripts Bundled Under `src/ralph/resources`
Gaps to close:
- confirm required scripts are actually bundled under packaged resources
- keep packaged copies in parity with the repo-root sources they mirror
- identify any CLI path that still assumes a root-level script exists next to the checkout

### Root-Level Helper Scripts
Current risk:
- some development workflows still use root-level helper scripts directly
- installed mode should not rely on those root-level files being importable or adjacent to the package

Required outcome:
- either package the required helper
- or make the console command clearly repo-local only

### Docs Availability
Current risk:
- `groom` depends on `docs/ACTIVE_BACKLOG.md`
- operators may run the installed tool against projects where docs are missing or stale

Required outcome:
- document which docs are expected in the target project
- keep missing-doc behavior explicit and readable

### Tests Coupled To `REPO_ROOT`
Current risk:
- some packaging tests still exercise the source repository directly
- that can hide installed-mode issues when the package accidentally falls back to repo-root files

Required outcome:
- expand installed-mode tests to prefer packaged resources over `REPO_ROOT`
- keep a clear split between repo-local development tests and installed-package smoke tests

## Stage R24 Exit Criteria
Stage `R24` is complete when:
- Ralph installs cleanly into `venv` and `pipx`
- the `ralph` console script works from arbitrary project directories
- packaged resources cover the required helper scripts for the current operator surface
- installed-mode smoke tests pass for `doctor`, `status`, `verify`, `next`, `explain`, `groom`, `tail`, `log`, `auto --safe`, and `task <ID>`
- command behavior does not depend on being launched from the Ralph source repo
- docs explain the supported installed workflow and `--project-dir` expectations

## Non-Goals For R24
- changing runtime policy
- changing `ralph.sh` task semantics
- redesigning task selection
- bootstrap/kickoff product generation
- new product-factory features

## Next Implementation Areas
- packaging smoke coverage hardening
- resource bundling audit
- installed-mode path cleanup
- console script UX polish for `--project-dir`
