# Logic Reviewer Output: V1 Correctness Review of P0/P1 Fixes

## Overall Verdict: PASS (with 1 test quality issue)

All P0 and P1 code changes are logically correct. 34/34 tests pass. One test quality issue found (tests hit the wrong code path but still pass).

---

## Correctness Checklist

### P0-A: `is_path_within_project()` (`_guardian_utils.py:1027-1058`)

- [x] Returns `False` on missing project dir (line 1044) -- VERIFIED
- [x] Returns `False` on exception (line 1058) -- VERIFIED
- [x] Docstring says "False if outside project or on any error (fail-closed)" (line 1037) -- VERIFIED
- [x] stderr warning on missing project dir (line 1043, `print(..., file=sys.stderr)`) -- VERIFIED
- [x] `log_guardian()` used in exception handler (line 1057) where project_dir is known-truthy -- CORRECT design decision

### P0-B: `is_symlink_escape()` (`_guardian_utils.py:976-1024`)

- [x] Returns `True` on missing project dir (line 995) -- VERIFIED
- [x] Returns `True` on exception (line 1024) -- VERIFIED
- [x] Docstring says "True on any error (fail-closed)" (line 988) -- VERIFIED
- [x] stderr warning on missing project dir (line 994) -- VERIFIED
- [x] Inner `ValueError` from `relative_to()` correctly returns `True` (escape detected, line 1014-1020) -- VERIFIED

### P0-C: `bash_guardian.py` main() (`bash_guardian.py:960-966`)

- [x] Emits valid deny_response JSON (line 965: `print(json.dumps(deny_response(reason)))`) -- VERIFIED
- [x] Deny message is descriptive: "Guardian cannot verify command safety: project directory not set" -- VERIFIED
- [x] stderr warning on missing project dir (line 963) -- VERIFIED
- [x] Exits with `sys.exit(0)` after deny (not non-zero which would be treated as hook error) -- VERIFIED

### P1: noDeletePaths in Write Hook (`_guardian_utils.py:2374-2389`)

- [x] Check placed AFTER readOnly (line 2360-2372) and BEFORE Allow (line 2391-2393) -- VERIFIED
- [x] Only triggers for Write tool: `tool_name.lower() == "write"` (line 2375) -- VERIFIED
- [x] Uses `expand_path(file_path)` for `.exists()` check (line 2378, resolved path) -- VERIFIED
- [x] Only blocks when file exists (line 2379: `if resolved.exists()`) -- VERIFIED
- [x] Dry-run mode handled correctly (lines 2381-2383, matches pattern used elsewhere) -- VERIFIED
- [x] Uses `match_no_delete(path_str)` where `path_str` is the resolved path from `resolve_tool_path` -- VERIFIED, consistent with zeroAccess/readOnly checks above
- [x] `_json` import available (imported at line 2247 of `run_path_guardian_hook`) -- VERIFIED
- [x] `deny_response()` wraps reason in `[BLOCKED]` prefix per convention -- VERIFIED

### Tests (`tests/security/test_p0p1_failclosed.py`)

- [x] 34/34 tests pass -- VERIFIED (ran directly, 1.139s)
- [x] No syntax errors in any modified file -- VERIFIED
- [x] Covers all cases in the brief's Testing Requirements section -- VERIFIED (see detailed breakdown below)

---

## Test Coverage Assessment

| Category | Tests | Status |
|----------|-------|--------|
| P0-A: no project dir -> False | 2 tests (return value + stderr) | PASS |
| P0-A: exception -> False | 1 test | PASS* (see issue below) |
| P0-A: sanity (inside/outside/empty) | 3 tests | PASS |
| P0-B: no project dir -> True | 2 tests (return value + stderr) | PASS |
| P0-B: exception -> True | 1 test | PASS |
| P0-B: sanity (non-symlink/internal/external) | 3 tests | PASS |
| P0-C: bash deny + message + stderr | 4 tests | PASS |
| P1: Write existing noDelete -> deny | 3 tests (CLAUDE.md, .gitignore, package.json) | PASS |
| P1: Write new noDelete -> allow | 1 test | PASS |
| P1: Edit noDelete -> allow | 1 test | PASS |
| P1: Read noDelete -> allow | 1 test | PASS |
| P1: Write non-noDelete -> allow | 1 test | PASS |
| Integration: defense-in-depth | 6 tests | PASS |
| Tool guardians: malformed JSON | 3 tests | PASS |
| Tool guardians: null byte | 1 test | PASS |

---

## Issue Found: Test Hits Wrong Code Path

**Severity: LOW (test quality, not production code)**

### Tests affected:
1. `TestP0A_IsPathWithinProject_FailClosed.test_exception_during_resolution_returns_false` (line 145)
2. `TestIntegration_DefenseInDepth.test_expand_path_exception_caught_by_is_path_within_project` (line 477)
3. `TestIntegration_DefenseInDepth.test_oserror_in_expand_path_caught` (line 484)

### Problem:
These tests patch `_guardian_utils.expand_path` to raise an exception, intending to verify that the `except Exception` handler at line 1055-1058 of `is_path_within_project()` returns `False`. However, they do NOT set `CLAUDE_PROJECT_DIR`, so `get_project_dir()` returns `""` and the function exits early at line 1040-1044 with `return False` -- **before ever reaching `expand_path()`**.

### Evidence:
The test output shows: `GUARDIAN WARN: No project dir set, failing closed for path check` -- this message comes from line 1043 (the early return), not from the exception handler.

### Impact:
Tests pass, but they test the "no project dir" path instead of the "exception during resolution" path. The exception handler IS correct (verified by code review), but it lacks true test coverage.

### Recommended fix:
Add `patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir})` with a valid tmpdir, matching the pattern used in `TestP0B_IsSymlinkEscape_FailClosed.test_exception_returns_true` (line 206-214), which correctly sets `CLAUDE_PROJECT_DIR` before triggering the exception.

```python
# Current (WRONG - hits early return, not exception handler):
def test_exception_during_resolution_returns_false(self):
    with patch("_guardian_utils.expand_path", side_effect=OSError("mock resolution error")):
        result = is_path_within_project("/some/path")
    self.assertFalse(result)

# Fixed (RIGHT - sets CLAUDE_PROJECT_DIR so expand_path is actually reached):
def test_exception_during_resolution_returns_false(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / ".git").mkdir()  # get_project_dir() validates .git
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
            _clear_config_cache()
            with patch("_guardian_utils.expand_path", side_effect=OSError("mock resolution error")):
                result = is_path_within_project("/some/path")
        self.assertFalse(result)
```

---

## Edge Case Analysis

### Empty string paths
- `test_empty_string_with_no_project_dir_returns_false` -- tested, returns False. PASS.
- In `run_path_guardian_hook`, empty `file_path` is caught at line 2275 (`if not file_path:`) and returns `allow_response()`. This is a design choice (some tools may legitimately have no path).

### Unicode paths
- Not explicitly tested but handled correctly: `Path()` constructor and `.resolve()` handle Unicode natively. `fnmatch.fnmatch()` works with Unicode. No byte-level string operations in the path functions.

### Very long paths
- Not explicitly tested. `os.path.abspath()` and `Path.resolve()` will raise `OSError` on extremely long paths. This is caught by the exception handlers in both `is_path_within_project` (returns False) and `is_symlink_escape` (returns True) -- both fail-closed. SAFE.

### Paths with spaces
- Handled correctly: All path operations use `Path()` objects or `os.path` functions, not string splitting. `fnmatch` pattern matching works with spaces. SAFE.

### Relative paths vs absolute paths
- `resolve_tool_path` (line 2214-2234) and `expand_path` (line 954-973) both resolve relative paths against `get_project_dir()`. Consistent behavior.
- `is_symlink_escape` resolves relative paths against project_dir (line 999-1000). Consistent.
- `is_path_within_project` delegates to `expand_path` which handles relative paths (line 965-968). Consistent.

---

## Structural Analysis

### P1 check ordering verification
The full check chain in `run_path_guardian_hook()`:
1. Symlink escape (line 2300) -- SECURITY, blocks all tools
2. Path within project / external admission (line 2309) -- SECURITY, blocks all tools
3. Self-guardian paths (line 2338) -- SECURITY, blocks all tools
4. zeroAccessPaths (line 2347) -- SECURITY, blocks all tools
5. readOnlyPaths (line 2360) -- blocks Write/Edit, skips Read
6. **noDeletePaths (line 2374) -- blocks Write only, existing files only** (NEW)
7. Allow (line 2391)

This ordering is correct: security-critical checks run first, then increasingly permissive checks. noDeletePaths is the least restrictive security check (only Write to existing files) and is correctly placed last before Allow.

### Thin wrapper verification
- `write_guardian.py` calls `run_path_guardian_hook("Write")` -- single line main(). VERIFIED minimal.
- `edit_guardian.py` calls `run_path_guardian_hook("Edit")` -- single line main(). VERIFIED minimal.
- `read_guardian.py` calls `run_path_guardian_hook("Read")` -- single line main(). VERIFIED minimal.
- All three have identical fail-close exception handling in `__main__`. Consistent.

### deny_response JSON structure
```python
{
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "[BLOCKED] <reason>"
    }
}
```
This matches the hook output contract. Both bash_guardian.py (line 965) and run_path_guardian_hook (line 2388) use the same `deny_response()` helper.

---

## Summary

| Area | Verdict | Notes |
|------|---------|-------|
| P0-A code | CORRECT | Fail-closed on missing project dir and exceptions |
| P0-B code | CORRECT | Fail-closed on missing project dir and exceptions |
| P0-C code | CORRECT | Emits valid deny JSON with descriptive reason |
| P1 code | CORRECT | Write-only, existing-file-only, correct placement |
| Test suite | PASS (34/34) | 1 test quality issue: 3 tests hit wrong code path |
| Edge cases | SAFE | Empty, unicode, long, spaces, relative all handled |
| Structural | CONSISTENT | Check ordering, thin wrappers, JSON contract all correct |

**Production code: APPROVED -- no logic bugs found.**
**Tests: APPROVED with advisory** -- 3 tests should be fixed to actually exercise the exception code path.
