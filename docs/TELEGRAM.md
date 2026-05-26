# Telegram Control Layer

## Purpose
Telegram is an optional control/observation layer for Ralph.

Current role:
- the installed CLI is the default operator surface
- Telegram is useful for remote control, observation, and lightweight repo status checks
- local smoke, pilot setup, and first-run validation should still start from the CLI

## Setup
The bot reads project-local `.env` values.

Required variables from `.env.example`:
- `RALPH_TELEGRAM_TOKEN`
- `RALPH_TELEGRAM_CHAT_ID`

The bot loads `.env` from the target project directory and expects `tasks.json`
to exist there.

Start the bot from project cwd:

```bash
cd /path/to/project
ralph bot
```

Or point it at another project explicitly:

```bash
ralph bot --project-dir /path/to/project
```

Project resolution in the bot runtime is:
- `--project-dir`
- then `RALPH_PROJECT_DIR` if present
- then current working directory

If the target project has no `tasks.json`, the bot exits with an error.

## CLI Vs Telegram
- CLI is the default operator surface.
- Telegram is the optional remote control/observation layer.
- Use CLI for install smoke, `ralph init`, `ralph status`, `ralph doctor`, `ralph verify`, `ralph next`, and `ralph explain`.
- Use Telegram when you need to watch or steer a running repo remotely.

## Command Groups Found In Bot Code

### Status / Read-Only
- `/status` — current state
- `/tasks [phase]` — task list
- `/plan` — phase plan summary
- `/projects` — list registered projects
- `/switch <project>` — switch active project context
- `/help` — primary command help
- `/hidden` — secondary command help
- `/cost` — today's token usage
- `/stats` — runtime metrics
- `/limits` — budget and limit summary

### Logs / Progress / Inspection
- `/log [N]` — last N lines from Ralph execution log
- `/progress` — narrative progress log
- `/tail [N]` — last N lines of live Codex output
- `/diff` — last commit changes
- `/audit <task_id>` — trust audit summary
- `/audit_last [N]` — recent audit artifacts
- `/trust_report` — trust-layer report
- `/ask <question>` — repo-local assistant question

### Execution / Control
- `/start <task_id>` — run one task
- `/phase <phase>` — run one phase
- `/auto` — run all
- `/stop` — stop after current task
- `/stop now` — kill immediately
- `/pause` — pause before next step
- `/resume` — resume after pause
- `/exit` — stop Ralph and the bot
- `/timeout <seconds>` — override timeout for next run
- `/reload` — hot-reload bot handlers

### Backlog / Task Mutation
- `/add <phase> <title>` — append a pending task
- `/rm <task_id>` — remove a task
- `/done <task_id>` — mark task done
- `/redo <task_id> [notes]` — reopen a task for another pass
- `/comment <text>` — save note for the next attempt

### Other Implemented Command
- `/article <topic|new>` — generate article draft

## Safety Notes

### Execution And Repo-State Risk
- `/start <task_id>` changes repo state because it runs task execution.
- `/phase <phase>` can run multiple tasks and should be treated as broader than a one-task trial.
- `/auto` can run multiple tasks and is riskier than explicit single-task execution.
- `/exit` is an operational stop, not a read-only status command.

### Control-Signal Risk
- `/stop`, `/stop now`, `/pause`, and `/resume` are control signals written into runtime state/control files.
- `/timeout <seconds>` changes the next-run execution behavior and should be treated as an operator override.
- `/reload` changes the live bot handler layer and is operational, not informational.

### Backlog Mutation Risk
- `/add` and `/rm` mutate `tasks.json`.
- `/redo` changes task status and reopens work.
- `/comment` changes the next-attempt operator guidance path.
- `/done <task_id>` directly mutates task status and can bypass parts of the normal trust/review flow because it marks the task done without running the standard runtime execution pipeline.

### Observation-Only Preference For Pilot Work
For the first pilot:
- prefer CLI for setup and first-task execution
- use Telegram mainly for observation or explicit remote control
- do not treat Telegram mutation commands as a substitute for reviewing `git diff`, `tasks.json`, `progress.md`, and logs

## Recommended Usage For First Pilot
1. Use CLI first: `ralph init`, `ralph status`, `ralph doctor`, `ralph verify`, `ralph next`, `ralph explain`.
2. Run exactly one explicit CLI task first: `ralph task <ID>`.
3. Review diff, logs, and status locally.
4. Add Telegram only if you need remote observation or remote stop/pause/resume control.

## References
- [README.md](../README.md)
- [INSTALL.md](INSTALL.md)
- [SYSTEM_AUDIT.md](SYSTEM_AUDIT.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
