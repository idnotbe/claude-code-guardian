# Phase 2 Implementation Report: Low-Severity Regex Hardening

## Summary

Applied 3 hardening fixes to 10 regex patterns across 4 files, plus added 5 new test cases.

## Three Hardening Changes Applied

### Fix 1: Leading whitespace (`  rm .claude/` not caught)
- `(?:^|` changed to `(?:^\s*|`
- Adds optional whitespace after start-of-string anchor

### Fix 2: Brace group (`{ rm .claude/; }` not caught)
- `[;|&` + backtick + `(]` changed to `[;|&` + backtick + `({]`
- Adds `{` to separator character class

### Fix 3: Quoted paths (`rm ".claude"` not caught)
- `[;&|)` + backtick + `]` changed to `[;&|)` + backtick + `'\"  ]`
- Adds `'` and `"` to terminator character class

## Files Changed

| # | File | Patterns Changed | Format |
|---|------|-----------------|--------|
| 1-3 | `assets/guardian.default.json` (lines 17, 21, 25) | .git, .claude, _archive | JSON (`\\s`, `\\b`) |
| 4-6 | `hooks/scripts/_guardian_utils.py` (lines ~374, 378, 382) | .git, .claude, _archive (fallback) | Python raw (`\s`, `\b`) |
| 7-8 | `tests/test_guardian_utils.py` (lines ~56, 58) | .git, .claude | Python raw (`\s`, `\b`) |
| 9-10 | `tests/test_guardian.py` (lines ~98, 100) | .git, _archive | Python raw (`\s`, `\b`) |

## New Test Cases Added

In `tests/test_guardian_utils.py` `test_block_patterns()`:

1. `("  rm .claude/config", True, "leading spaces before rm must be blocked")`
2. `("\trm .claude/config", True, "leading tab before rm must be blocked")`
3. `("{ rm .claude/x; }", True, "brace group rm must be blocked")`
4. `('rm ".claude/config"', True, "quoted path must be blocked")`
5. `("rm '.claude/config'", True, "single-quoted path must be blocked")`

## Test Results

### test_guardian_utils.py: 130/130 passed
All new test cases pass. All existing tests pass.

### test_guardian.py: 51/51 passed (1 skipped - Windows only)
All existing tests pass with hardened patterns.

### Core + Security suites: 627 passed, 3 failed, 1 error
3 pre-existing failures (all `ln` symlink pattern-related, not changed by this PR):
- `test_ln_pattern_in_source`
- `test_ln_symlink_not_detected`
- `test_ln_symlink_gap`

1 pre-existing error (pytest fixture incompatibility in `test_bypass_v2.py`).

None of these failures are related to the hardening changes.

## Not Changed (as specified)

- `bash_guardian.py` `is_delete_command()` - already anchored differently
- SQL DELETE pattern in `guardian.default.json` (~line 147) - SQL-specific
- `del\s+` ask pattern in `guardian.default.json` (~line 91) - safe as-is
