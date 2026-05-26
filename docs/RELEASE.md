# Release Guide

## Scope
This document defines the first packaged release flow for Ralph before any
PyPI publishing.

Current release target:
- version `0.1.0` in `pyproject.toml`
- git tag `v0.1.0`
- install path via `pipx` from GitHub tag

PyPI publishing remains explicitly deferred until CI and tag flow are proven.

## Pre-Release Checks
Before creating the first release tag:
- confirm `pyproject.toml` still declares `version = "0.1.0"`
- confirm `requires-python = ">=3.11"` remains true
- confirm the installed CLI smoke path works with Python 3.11+
- confirm `ralph init` does not leak internal package paths
- confirm `ralph status`, `ralph doctor`, `ralph verify`, `ralph next`, and `ralph explain` work from a project-local cwd
- confirm build artifacts remain ignored and `src/ralph_dev.egg-info` is untracked
- confirm the branch intended for release has already been pushed to GitHub
- check whether GitHub Actions package smoke is available; if billing still blocks it, record that explicitly in release notes rather than treating it as a code failure

## Version Verification
Verify the packaged version directly from `pyproject.toml` before tagging:

```bash
python3.11 - <<'PY'
from pathlib import Path
import tomllib

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
```

Expected result for the first release:

```text
0.1.0
```

## Tag Creation Flow
Create the first release tag from the intended release commit:

```bash
git checkout dev/auto-pilot
git pull --ff-only
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

If the default merge branch changes before release, keep the same tag name but
create it from the approved release commit instead of assuming a branch name.

## Install From GitHub Tag With pipx
After the tag is pushed, verify the release install path from the GitHub tag:

```bash
python3.11 -m pipx install --python python3.11 \
  git+https://github.com/<OWNER>/<REPO>.git@v0.1.0
```

Optional reinstall when re-testing the same environment:

```bash
python3.11 -m pipx install --force --python python3.11 \
  git+https://github.com/<OWNER>/<REPO>.git@v0.1.0
```

Then smoke the installed console script against a project directory:

```bash
cd /path/to/project
ralph status
ralph doctor
ralph verify
ralph next
ralph explain
```

## Local Release Candidate Smoke
Use this fallback path while hosted GitHub Actions package smoke is blocked by
account billing.

This local smoke does not replace hosted cross-platform CI. It is only the
documented release-candidate fallback for the current billing-blocked period.

Run the exact local RC smoke commands:

```bash
python3.11 -m pytest tests/test_cli_packaging.py -q
python3.11 -m pytest tests/test_ralph_cli.py -q
python3.11 -m ralph.cli verify
python3.11 -m pipx install --force .
python3.11 -m pipx inject ralph-dev pytest --force
mkdir -p /tmp/ralph-release-smoke
cd /tmp/ralph-release-smoke
ralph init
git init
ralph status
ralph doctor
ralph verify
ralph next
ralph explain
```

Expected interpretation:
- local Python 3.11 release-candidate smoke passed
- packaged `pipx` reinstall path works locally
- `ralph init` smoke works in a fresh temp directory
- project-local `ralph status`, `ralph doctor`, `ralph verify`, `ralph next`, and `ralph explain` work after init
- hosted GitHub Actions and cross-platform CI proof are still missing until billing is unblocked or an explicit manual release decision is made

## Non-Goals
- no PyPI publish step yet
- no claim of native Windows PowerShell or cmd.exe runtime support yet
- no runtime code changes as part of the tag flow document itself
