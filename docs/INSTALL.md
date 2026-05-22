# Install Guide

Ralph supports Python 3.11+.
Python 3.9 is unsupported and not recommended.

## Preferred Install: pipx
`pipx` is the recommended way to install Ralph before it is published to PyPI.

If `pipx` is not installed:

```bash
python3.11 -m pip install --user pipx
python3.11 -m pipx ensurepath
```

Install Ralph from a Git URL:

```bash
python3.11 -m pipx install --python python3.11 git+https://github.com/<OWNER>/<REPO>.git
```

Install Ralph from a local checkout for development:

```bash
cd /path/to/ralph-dev
python3.11 -m pipx install --python python3.11 .
```

Upgrade or reinstall from a local checkout:

```bash
python3.11 -m pipx install --force --python python3.11 .
```

Upgrade from the Git-installed package name:

```bash
python3.11 -m pipx upgrade ralph-dev
```

Inject pytest for parity checks:

```bash
python3.11 -m pipx inject ralph-dev pytest
```

## Development Fallback: venv
If you prefer a local virtualenv during development:

```bash
python3.11 -m venv .venv
.venv/bin/pip install .
export PATH="$PWD/.venv/bin:$PATH"
```

You can then run:

```bash
ralph --help
```

## Daily Usage
From the target project directory:

```bash
cd /path/to/project
ralph status
ralph doctor
ralph verify
ralph next
ralph explain
```

`ralph groom`, `ralph tail`, and `ralph log` are also available from the project directory.

## When `--project-dir` Is Needed
Use `--project-dir` only when you run Ralph from outside the target project directory:

```bash
ralph status --project-dir /path/to/project
ralph doctor --project-dir /path/to/project
ralph verify --project-dir /path/to/project
ralph next --project-dir /path/to/project
ralph explain --project-dir /path/to/project
```

If you `cd /path/to/project` first, `--project-dir` is usually unnecessary.

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

## Cross-Platform Notes
- macOS and Linux are the primary supported installed-mode platforms.
- Windows is currently supported through CI smoke using a bash-capable environment such as Git Bash.
- Native PowerShell or cmd.exe runtime support is not claimed yet because Ralph still shells out to `bash`.

## Parity Check Dependency
`ralph doctor` and `ralph verify` run project-local shell parity checks when `tests/test_shell_parity.py` is present. Those parity checks require `pytest` in the same Ralph environment.

If pytest is missing, Ralph prints a clear message and skips the parity step instead of showing a raw Python traceback.

## Expected Project Files
Target projects should have:

- `tasks.json`
- `docs/ACTIVE_BACKLOG.md` for `ralph groom` and `ralph status`
- `logs/ralph_*.log` for `ralph tail` and `ralph log`
- `ralph.sh` for `ralph verify` if you want the project-local shell syntax check to run

`ralph.sh` is optional for normal operator use, but `ralph verify` checks it when present.

`docs/ACTIVE_BACKLOG.md` is optional for read-only operation, but `groom` is most useful when it exists.
