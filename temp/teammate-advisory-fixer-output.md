# Advisory Fixer Output

## Date: 2026-02-15

## Summary

All 3 advisory fixes implemented in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`.

## Changes Made

### ADVISORY-1: Variable shadowing (L2382)
- **Renamed** `resolved = expand_path(file_path)` to `nodelete_resolved = expand_path(file_path)` in the noDelete check block
- Eliminates shadowing of the outer `resolved = resolve_tool_path(file_path)` variable
- Combined with ADVISORY-2 fix below

### ADVISORY-2: TOCTOU fail-closed (L2378-2393)
- **Wrapped** `expand_path()` + `.exists()` in try/except
- On exception: `file_exists = True` (fail-closed -- assumes file exists if check fails)
- Logs warning with `path_preview` for debugging
- Preserves exists() check for normal operation (new files matching noDelete are still allowed if no error)

### ADVISORY-3: Fail-closed normalization helpers (10 sub-items)

| Sub-item | Function | Change | Lines |
|----------|----------|--------|-------|
| a | `expand_path()` | Removed try/except, exceptions propagate | L954-971 |
| b | `normalize_path_for_matching()` | Removed try/except, exceptions propagate | L1059-1084 |
| c | `resolve_tool_path()` | Removed except block, OSError propagates | L2220-2239 |
| d | `match_path_pattern()` | Added `default_on_error` parameter (default=False) | L1121 |
| e | `match_zero_access()` | Passes `default_on_error=True` | L1203 |
| f | `match_read_only()` | Passes `default_on_error=True` | L1217 |
| g | `match_no_delete()` | Passes `default_on_error=True` | L1231 |
| h | `match_allowed_external_path()` | No change needed (default False is correct) | -- |
| i | `is_self_guardian_path()` | Added try/except around both `normalize_path_for_matching` calls, returns True on error | L2177-2214 |
| j | `run_path_guardian_hook()` | Added try/except around `resolve_tool_path`, emits deny on OSError | L2302-2307 |

### NOT changed (per instructions)
- `normalize_path()` (L918-951) -- dead code, never called

## Security Analysis

| Function | Before (error) | After (error) | Impact |
|----------|---------------|---------------|--------|
| `expand_path` | returns Path(raw) -- fail-open | raises -- caller handles | Callers must handle |
| `normalize_path_for_matching` | returns raw string -- fail-open | raises -- caller handles | Callers must handle |
| `match_path_pattern` (deny context) | returns False -- fail-open | returns True -- fail-closed | Block on error |
| `match_path_pattern` (allow context) | returns False -- fail-closed | returns False -- fail-closed | No change |
| `match_zero_access` | returns False -- fail-open | returns True -- fail-closed | Block on error |
| `match_read_only` | returns False -- fail-open | returns True -- fail-closed | Block on error |
| `match_no_delete` | returns False -- fail-open | returns True -- fail-closed | Block on error |
| `match_allowed_external_path` | returns None -- fail-closed | returns None -- fail-closed | No change |
| `is_self_guardian_path` | returns False -- fail-open | returns True -- fail-closed | Protect on error |
| `resolve_tool_path` | returns raw Path -- fail-open | raises OSError -- caller denies | Deny on error |
| noDelete exists() check | uncaught exception -- crash? | file_exists=True -- fail-closed | Block on error |

## Test Results

### test_p0p1_comprehensive.py: 180/180 PASS
### test_p0p1_failclosed.py: 34/34 PASS
### test_bypass_v2.py: 84/101 PASS (17 failures are PRE-EXISTING known issues, not regressions)

Pre-existing failures in bypass_v2:
- 9 tokenizer issues (heredoc, extglob, subshell, etc.)
- 3 zero-access scan bypasses (char class, glob, hex encoding)
- 3 read-only false positives (chmod/chown/touch detected as write)
- 2 no-delete bypasses (redirect truncation, git rm)

None of these are related to the advisory fixes.
