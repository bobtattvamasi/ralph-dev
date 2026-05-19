# Packaging Audit

## Purpose
This audit summarizes the current installed-mode dependency shape for the Stage `R24` packaging polish effort.

The main question is whether each CLI command can run from an arbitrary working directory when Ralph is installed as a console script, and which inputs still come from the target project rather than the Ralph source checkout.

## Command Dependency Matrix

### `ralph next`
- Packaged resource: `src/ralph/resources/scripts/next_task.py`
- Project-local file: `tasks.json`
- Repo-root only: none
- Optional project-local file: none

### `ralph explain`
- Packaged resource: `src/ralph/resources/scripts/next_task.py`
- Project-local file: `tasks.json`
- Repo-root only: none
- Optional project-local file: none

### `ralph doctor`
- Packaged resource: `src/ralph/resources/scripts/next_task.py`
- Project-local file: `tasks.json`
- Project-local file: `tests/test_shell_parity.py`
- Repo-root only: none
- Optional project-local file: none

### `ralph groom`
- Project-local file: `docs/ACTIVE_BACKLOG.md`
- Project-local file: `docs/BACKLOG_POLICY.md`
- Repo-root only: none
- Optional project-local file: `docs/BACKLOG_POLICY.md`

### `ralph status`
- Packaged resource: `src/ralph/resources/scripts/next_task.py`
- Project-local file: `tasks.json`
- Project-local file: `docs/ACTIVE_BACKLOG.md`
- Repo-root only: none
- Optional project-local file: `docs/ACTIVE_BACKLOG.md`

### `ralph tail`
- Project-local file: `logs/ralph_*.log`
- Repo-root only: none
- Optional project-local file: none

### `ralph log`
- Project-local file: `logs/ralph_*.log`
- Repo-root only: none
- Optional project-local file: none

### `ralph verify`
- Packaged resource: `src/ralph/resources/ralph.sh`
- Project-local file: `ralph.sh`
- Project-local file: `tests/test_shell_parity.py`
- Repo-root only: none
- Optional project-local file: `ralph.sh`
- Optional project-local file: `tests/test_shell_parity.py`

### `ralph auto --safe`
- Packaged resource: `src/ralph/resources/ralph.sh`
- Project-local file: `tasks.json`
- Project-local file: `progress.md`
- Project-local file: `.ralph/memory/recent.md`
- Repo-root only: none
- Optional project-local file: `.ralph/memory/recent.md`

### `ralph task <ID>`
- Packaged resource: `src/ralph/resources/ralph.sh`
- Project-local file: `tasks.json`
- Project-local file: `progress.md`
- Project-local file: `.ralph/memory/recent.md`
- Repo-root only: none
- Optional project-local file: `.ralph/memory/recent.md`

## Installed-Mode Risks
- `doctor` still assumes a project-local `tests/test_shell_parity.py`; if the target project does not carry that file, the smoke fails rather than downgrading to a packaged equivalent.
- `verify` is now installed-mode aware, but it still needs a project-local `ralph.sh` and `tests/test_shell_parity.py` to exercise the full check set.
- `status` and `next` are packaged-resource backed, but they still depend on a valid project `tasks.json` and on `next_task.py` understanding that project layout.
- `groom` assumes the target project carries `docs/ACTIVE_BACKLOG.md`; `docs/BACKLOG_POLICY.md` is only a hint if present.
- `tail` and `log` are intentionally project-local and need real runtime logs in the target project.
- The installed smoke matrix still mixes repo-local development fixtures and true external-project use, so regressions can hide if only one of those shapes is exercised.
- Packaged resource parity is still an ongoing risk surface because `src/ralph/resources` mirrors repo-root helper scripts.
- `pyproject.toml` packages the resource tree via `tool.setuptools.package-data`, so any new helper added to runtime paths must stay in that list.

## Next Implementation Tasks
1. Tighten the installed smoke matrix so each command has an explicit fixture shape and the current optional project-local behavior is documented in the test itself.
2. Add a resource-bundling audit test that fails if any command path reaches for an unbundled helper script.
3. Reduce the remaining repo-local assumptions in the packaging tests by splitting pure package-entrypoint checks from project-fixture checks.

## Notes
- The installed `ralph` console script is already the intended entrypoint.
- The current focus is command discoverability and bundled resource parity, not new runtime policy.
