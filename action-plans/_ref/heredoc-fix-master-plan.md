---
status: done
progress: "완료. 커밋 4923946"
---

# Heredoc Fix Master Plan

## Objective
Fix heredoc false positives in bash_guardian.py - 3 fixes + TDD tests.

## Source Spec
Full spec: `/home/idnotbe/projects/claude-code-guardian/temp/guardian-heredoc-fix-prompt.md`

## Phase Structure

### Phase 1: Test Creation (test-writer)
- Create `tests/test_heredoc_fixes.py` with all test classes from spec
- Run tests to confirm they fail (TDD baseline)

### Phase 2: Implementation (implementer)
- Step 2: Fix `is_write_command()` - quote-aware via `_is_inside_quotes()`
- Step 3: Fix `split_commands()` - heredoc awareness + arithmetic bypass guard
- Step 4: Fix `main()` - reorder Layer 1 after Layer 2
- Each step verified with targeted test run

### Phase 3: Verification Round 1 (3 parallel reviewers)
- v1-accuracy: Code accuracy vs spec
- v1-security: Security invariant review
- v1-test-runner: Full test suite execution

### Phase 4: Verification Round 2 (3 parallel reviewers)
- v2-logic: Logic + edge case review
- v2-regression: Regression testing with existing suite
- v2-integration: Full integration + gemini consultation

## Files Modified
- `hooks/scripts/bash_guardian.py` (3 fixes)
- `tests/test_heredoc_fixes.py` (new - test file)

## Working Memory Files
- `action-plans/_ref/heredoc-fix-master-plan.md` (this file)
- `temp/heredoc-fix/phase1-tests.md` (test creation notes)
- `temp/heredoc-fix/phase2-implementation.md` (implementation notes)
- `temp/heredoc-fix/v1-*.md` (verification round 1 reports)
- `temp/heredoc-fix/v2-*.md` (verification round 2 reports)

## Status Tracker
- [x] Phase 1: Test file created
- [x] Phase 2: Fix 2 implemented (is_write_command)
- [x] Phase 2: Fix 1 implemented (split_commands)
- [x] Phase 2: Fix 3 implemented (main reorder)
- [x] Phase 3: Verification Round 1 complete
- [x] Phase 4: Verification Round 2 complete
