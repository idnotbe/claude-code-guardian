# P0/P1 Fix Master Plan

> Created: 2026-02-15
> Team: guardian-p0p1-fix
> Status: IN PROGRESS

## Summary

Fix 4 security issues (P0-A, P0-B, P0-C, P1) in guardian hooks:
- **P0-A**: `is_path_within_project()` fails open on exception/missing project dir
- **P0-B**: `is_symlink_escape()` fails open on exception/missing project dir
- **P0-C**: `bash_guardian.py` exits with allow on missing project dir
- **P1**: `noDeletePaths` not enforced in Write tool hook (only Bash guardian checks it)

## Files to Modify

| File | Change |
|------|--------|
| `hooks/scripts/_guardian_utils.py` | P0-A: `is_path_within_project()` ~L1035-1051 |
| `hooks/scripts/_guardian_utils.py` | P0-B: `is_symlink_escape()` ~L976-1021 |
| `hooks/scripts/_guardian_utils.py` | P1: `run_path_guardian_hook()` add noDelete check ~L2366 |
| `hooks/scripts/bash_guardian.py` | P0-C: fail-closed on missing project dir ~L960-962 |
| `tests/security/test_p0p1_failclosed.py` | NEW: tests for all P0/P1 fixes |

## Team Structure

### Phase 1: Implementation (parallel)
- **p0-fixer**: P0-A + P0-B + P0-C code changes
- **p1-fixer**: P1 noDeletePaths code changes
- **test-author**: Write comprehensive tests

### Phase 2: Verification Round 1 (parallel)
- **security-auditor**: Security-focused code review
- **logic-reviewer**: Correctness and edge case review
- **test-executor**: Run all tests, check regressions

### Phase 3: Verification Round 2 (parallel)
- **adversarial-tester**: Red-team perspective, bypass attempts
- **semantic-checker**: Documentation and semantic consistency
- **final-validator**: Final test run and sign-off

## Communication Protocol
- All context exchange via files in `temp/`
- Direct messages contain only file path references
- Each teammate writes their output to `temp/teammate-{name}-output.md`

## Verification Requirements
- Each reviewer uses vibe-check skill
- Each reviewer uses pal clink for cross-model validation
- Each reviewer spawns subagents for independent analysis
