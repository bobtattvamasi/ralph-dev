# Install Guide

## Install From Repo
Recommended local install:

```bash
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/ralph --help
```

`pipx` install:

```bash
pipx install .
ralph --help
```

## Use From Another Project
Run Ralph against any target project by pointing at that project directory:

```bash
ralph status --project-dir /path/to/project
ralph doctor --project-dir /path/to/project
ralph verify --project-dir /path/to/project
ralph next --project-dir /path/to/project
ralph explain --project-dir /path/to/project
```

## Smoke Checklist
For an installed toolchain, smoke these commands from a cwd outside the Ralph source tree:

- `ralph status`
- `ralph doctor`
- `ralph verify`
- `ralph next`
- `ralph explain`
- `ralph groom`
- `ralph tail`
- `ralph log`

## Parity Check Dependency
`ralph doctor` and `ralph verify` run project-local shell parity checks when `tests/test_shell_parity.py` is present. Those parity checks require `pytest` in the same Ralph environment.

If you installed Ralph into a `venv`, install pytest alongside it:

```bash
.venv/bin/pip install pytest
```

If you installed Ralph with `pipx`, inject pytest into the app environment:

```bash
pipx inject ralph-dev pytest
```

If pytest is missing, Ralph prints a clear message and skips the parity step instead of showing a raw Python traceback.

## Expected Project Files
Target projects should have:

- `tasks.json`
- `docs/ACTIVE_BACKLOG.md` for `ralph groom` and `ralph status`
- `logs/ralph_*.log` for `ralph tail` and `ralph log`
- `ralph.sh` for `ralph verify` if you want the project-local shell syntax check to run

`ralph.sh` is optional for normal operator use, but `ralph verify` checks it when present.

`docs/ACTIVE_BACKLOG.md` is optional for read-only operation, but `groom` is most useful when it exists.

## Notes
- Use `--project-dir` consistently whenever the target project is not the current shell cwd.
- Installed-mode commands should not depend on the Ralph source repository being the cwd.
