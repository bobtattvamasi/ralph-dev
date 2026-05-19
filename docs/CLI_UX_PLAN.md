# CLI UX Plan

## Stage 2 Goal
Stage 2 turns Ralph into a convenient terminal operator tool.

The goal is not new runtime policy. The goal is a small, memorable command surface that wraps the existing scripts and makes safe operation, queue explanation, backlog grooming, and health checks easy to discover.

## Design Constraints
- keep `tasks.json` as the source of truth
- prefer thin wrappers over new orchestration logic
- do not duplicate business rules already implemented in `ralph.sh` or `scripts/*.py`
- keep operator commands explicit about safe vs manual execution

## Target Command Surface

### `ralph next`
Operator intent:
- ask what Ralph would run next
- inspect the current candidate without starting execution

Current mapping:
- `python3 scripts/next_task.py`

Status:
- wrapper-only

### `ralph explain`
Operator intent:
- explain why the safe queue is empty, blocked, or selecting a specific task
- replace the need to remember `--auto-safe --explain`

Current mapping:
- `python3 scripts/next_task.py --auto-safe --explain`

Status:
- wrapper-only

### `ralph groom`
Operator intent:
- show the current active backlog report and parking guidance
- make Stage-scoped backlog triage a single command

Current mapping:
- no single command today
- nearest inputs are `docs/ACTIVE_BACKLOG.md`, `docs/BACKLOG_POLICY.md`, and selective `tasks.json` inspection

Status:
- requires implementation

### `ralph doctor`
Operator intent:
- run a lightweight operator health check before unattended or manual work
- detect common local repo problems quickly

Current mapping:
- no single command today
- should wrap:
  - `git status --short`
  - shell parity check
  - `python3 -m json.tool tasks.json`
  - `python3 scripts/next_task.py --auto-safe --explain`

Status:
- requires implementation

### `ralph auto --safe`
Operator intent:
- run the unattended safe lane explicitly
- make the operator-facing command match current Stage 1 policy language

Current mapping:
- `./ralph.sh auto`

Status:
- wrapper-only

Notes:
- the wrapper should make it obvious that this is the safe unattended lane, not a broad “run everything” button

### `ralph task <ID>`
Operator intent:
- run one explicitly selected task
- support manual-only or supervised work without using raw runtime flags

Current mapping:
- `./ralph.sh task <ID>`

Status:
- wrapper-only

### `ralph verify`
Operator intent:
- run the focused verification flow for the current task or current branch context
- reduce the habit of ad hoc grep and scattered script calls

Current mapping:
- partial only
- current pieces exist in task-specific pytest commands and closure verification helpers, but there is no single operator command

Status:
- requires implementation

### `ralph status`
Operator intent:
- inspect current runtime state, queue state, and most recent task outcome
- replace ad hoc file peeks and log greps for common checks

Current mapping:
- partial only
- current information is split across `tasks.json`, runtime state files, and logs

Status:
- requires implementation

### `ralph tail`
Operator intent:
- tail the live Ralph log in a stable operator-friendly way

Current mapping:
- log tailing exists today as ad hoc shell usage

Status:
- wrapper-only

### `ralph log`
Operator intent:
- inspect recent log history without manually locating files

Current mapping:
- grep or tail in `logs/`

Status:
- future

## Command Classification
Wrapper-only commands:
- `ralph next`
- `ralph explain`
- `ralph auto --safe`
- `ralph task <ID>`
- `ralph tail`

Requires implementation:
- `ralph groom`
- `ralph doctor`
- `ralph verify`
- `ralph status`

Future:
- `ralph log`

## Stage 2 Exit Criteria
- common operator workflows do not require remembering raw script paths
- safe queue explanation is one command
- backlog grooming report is one command
- doctor command checks git clean, shell parity, JSON validity, and auto-safe explain
- explicit single-task execution is available through a stable operator command
- operator-facing commands distinguish unattended safe flow from manual task execution

## Recommended Implementation Order
1. Add wrapper commands that only expose existing functionality:
- `ralph next`
- `ralph explain`
- `ralph auto --safe`
- `ralph task <ID>`
- `ralph tail`

2. Add `ralph doctor` as the first multi-check operator command.

3. Add `ralph groom` around the active backlog report and backlog policy.

4. Add `ralph status` and `ralph verify` after operator workflows stabilize.

5. Add `ralph log` only if `tail` and `status` still leave a discovery gap.

## Non-Goals For Stage 2
- changing task selection policy
- changing verification semantics
- changing backlog statuses
- introducing new memory, Qdrant, or security-gate architecture
- replacing `tasks.json` as the primary source of truth
