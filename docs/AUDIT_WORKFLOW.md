# Audit Workflow

## Purpose
Provide a repeatable way to inspect whether Ralph really completed a task.

## Planned Audit Artifact
Each task attempt should eventually produce a repo-local audit record with:
- task snapshot
- raw review path
- parsed review
- changed files
- verification result
- closure reason

## Planned Inspection Paths
- CLI: recent task audit
- CLI: single task audit
- Telegram: `/audit_last`
- Telegram: `/audit_task`
- Telegram: `/trust_report`

## Milestone 1
This iteration does not add audit commands yet.
It prepares the parser boundary so later audit data is meaningful.

## Minimal Audit Questions
- What did Tech Lead actually say?
- What did Ralph parse?
- Was the parsed review trustworthy?
- Did closure fail closed when review output was ambiguous?
