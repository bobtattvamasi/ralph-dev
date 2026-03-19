# Re-audit Report

- Generated: 2026-03-19T06:39:17.861951+00:00
- Mode: apply
- Scope: last 20 completed tasks

## Summary
- Total checked: 20
- Verified: 4
- False positive: 2
- Partial: 3
- Unclear: 11
- Auto-applyable: 6

## Results
### R5-01
- Current status: done
- Classification: false positive
- Task class: script
- Reason: Expected script is missing: scripts/run_eval.py

### R5-02
- Current status: done
- Classification: false positive
- Task class: tests-only
- Reason: Expected test files or named tests are missing.

### R5-03
- Current status: done
- Classification: verified
- Task class: script
- Reason: Expected script paths exist in repository.

### R5-04
- Current status: done
- Classification: partial
- Task class: docs-only
- Reason: Some expected documents are missing: PROMPT_CHANGELOG.md

### R5-05
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R6-03
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R7-04
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R8-03
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R9-01
- Current status: verified_done
- Classification: verified
- Task class: command
- Reason: Command routing, handler alias, help text, and test evidence exist.

### R9-02
- Current status: done
- Classification: partial
- Task class: tests-only
- Reason: Some expected tests are missing: test_ask_command_timeout, test_chat_command_followup, test_chat_command_exit

### R9-05
- Current status: done
- Classification: partial
- Task class: tests-only
- Reason: Some expected tests are missing: test_full_cycle_approve, test_full_cycle_fix_then_approve, test_full_cycle_alert, test_full_cycle_timeout

### R10-01
- Current status: verified_done
- Classification: verified
- Task class: docs-only
- Reason: Expected documentation exists and matches required content checks.

### R10-02
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R10-03
- Current status: done
- Classification: unclear
- Task class: docs-only
- Reason: No explicit docs path found in task text.

### R10-04
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R10-05
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R10-06
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R10-07
- Current status: done
- Classification: unclear
- Task class: implementation
- Reason: Generic implementation task needs human review: repo truth is not strong enough.

### R10-08
- Current status: verified_done
- Classification: verified
- Task class: command
- Reason: Command routing, handler alias, help text, and test evidence exist.

### R10-09
- Current status: verified_done
- Classification: unclear
- Task class: reaudit-report
- Reason: Generic implementation task needs human review: repo truth is not strong enough.
