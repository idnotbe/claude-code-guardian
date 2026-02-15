# V1 Security Review Report
## Date: 2026-02-15
## Reviewer: v1-security (redo -- independent review by claude-opus-4-6)
## Scope: Security and correctness review of advisory fixes (ADVISORY-1, 2, 3)

---

## Verification Checklist

### Source Code Verification (all PASS)

| Check | Location | Expected | Verified |
|-------|----------|----------|----------|
| expand_path() has NO try/except | L954-971 | Exceptions propagate | PASS |
| normalize_path_for_matching() has NO try/except | L1059-1084 | Exceptions propagate | PASS |
| resolve_tool_path() has NO except block | L2220-2239 | OSError propagates | PASS |
| match_path_pattern() has default_on_error param | L1121 | default=False | PASS |
| match_zero_access passes default_on_error=True | L1203 | Fail-closed | PASS |
| match_read_only passes default_on_error=True | L1217 | Fail-closed | PASS |
| match_no_delete passes default_on_error=True | L1231 | Fail-closed | PASS |
| match_allowed_external_path uses default (False) | L1253 | Fail-closed for allow-list | PASS |
| is_self_guardian_path try/except returns True | L2177-2182 | Fail-closed (protect on error) | PASS |
| is_self_guardian_path active config try/except returns True | L2209-2213 | Fail-closed (protect on error) | PASS |
| run_path_guardian_hook try/except on resolve_tool_path | L2302-2307 | Deny on OSError | PASS |
| noDelete block uses nodelete_resolved (not resolved) | L2391 | No variable shadowing | PASS |
| noDelete block has fail-closed exists() check | L2389-2395 | file_exists=True on error | PASS |

### Caller Chain Verification (EXHAUSTIVE)

All callers of the modified functions have proper error handling:

**expand_path() callers (3 total in codebase):**
- `is_path_within_project()` (L1045): `except Exception` -> returns False (fail-closed: treated as outside project)
- `normalize_path_for_matching()` (L1076): Propagates (no try/except, by design per ADVISORY-3b)
- noDelete block in `run_path_guardian_hook()` (L2391): `except Exception` -> file_exists=True (fail-closed)

**normalize_path_for_matching() callers (3 total in codebase):**
- `match_path_pattern()` (L1141): `except Exception` -> returns default_on_error
- `is_self_guardian_path()` input path (L2179): `except Exception` -> returns True (fail-closed)
- `is_self_guardian_path()` active config path (L2210): `except Exception` -> returns True (fail-closed)

**resolve_tool_path() callers (1 total in codebase):**
- `run_path_guardian_hook()` (L2303): `except OSError` -> deny response + sys.exit(0)

**match_path_pattern() callers via deny-check functions in bash_guardian.py:**
- `match_zero_access()` at L1052: returns True on error (fail-closed)
- `match_read_only()` at L1060: returns True on error (fail-closed)
- `match_no_delete()` at L1078: returns True on error (fail-closed)
- `match_allowed_external_path()` at L522, L556, L563, L1069: returns None on error (fail-closed, path not allowed)

**bash_guardian.py does NOT call expand_path(), normalize_path_for_matching(), or resolve_tool_path() directly** -- confirmed via grep. It only uses higher-level matching functions.

### Dead Code Verification

- `normalize_path()` (L918-951): Confirmed dead code via grep. Only defined, never called anywhere in codebase. Still contains fail-open pattern (`return path` on error at L951). Should be deleted.

### Thin Wrapper Scripts Verification

All three wrappers (edit_guardian.py, read_guardian.py, write_guardian.py) follow identical defense-in-depth pattern:
1. Module-level `try: from _guardian_utils import ...` / `except ImportError` -> emits deny JSON (fail-closed)
2. `main()` calls `run_path_guardian_hook(tool_name)` -- single delegation
3. `__main__` block wraps `main()` in `try/except Exception` -> emits deny JSON (fail-closed)
4. Inner fallback: if `get_hook_behavior()` itself fails, hardcoded deny JSON is emitted

This means even if `run_path_guardian_hook()` raises an exception NOT caught by its internal `except OSError` (e.g., RuntimeError from symlink loops), the wrapper's safety net catches it and denies. Defense in depth is correct.

---

## Findings

### ADVISORY-1: Variable Shadowing -- PASS

The noDelete check block (L2387-2406) correctly uses `nodelete_resolved`:
```python
nodelete_resolved = expand_path(file_path)
file_exists = nodelete_resolved.exists()
```
The outer `resolved = resolve_tool_path(file_path)` at L2303 is no longer shadowed. The outer `resolved` is used at L2308 (`path_str = str(resolved)`) and throughout subsequent checks.

### ADVISORY-2: TOCTOU Fail-Closed -- PASS

The noDelete exists() check (L2389-2395):
```python
try:
    nodelete_resolved = expand_path(file_path)
    file_exists = nodelete_resolved.exists()
except Exception:
    log_guardian("WARN", f"Cannot verify existence for noDelete check: {path_preview}")
    file_exists = True  # Fail-closed
```
- On exception: `file_exists = True` (fail-closed, blocks the write)
- Log uses `path_preview` (truncated), not raw path
- Catches broad `Exception` covering both OSError and PermissionError

### ADVISORY-3: Fail-Closed Normalization -- PASS (all 10 sub-items)

| Sub-item | Function | Verified Behavior |
|----------|----------|-------------------|
| 3a | expand_path() | No try/except, OSError propagates |
| 3b | normalize_path_for_matching() | No try/except, calls expand_path(), exception propagates |
| 3c | resolve_tool_path() | No except block, path.resolve() OSError propagates |
| 3d | match_path_pattern() | default_on_error=False (default), returns default_on_error on Exception |
| 3e | match_zero_access() | default_on_error=True -- True on error means "is in deny list" = deny |
| 3f | match_read_only() | default_on_error=True -- same logic |
| 3g | match_no_delete() | default_on_error=True -- same logic |
| 3h | match_allowed_external_path() | default_on_error=False (default) -- False on error = not in allow list = deny |
| 3i | is_self_guardian_path() | Two try/except blocks, both return True on error = protect |
| 3j | run_path_guardian_hook() | except OSError -> deny_response + exit |

**Polarity verification**: The `default_on_error` parameter semantics are correct:
- For deny-list checks: `True` means "assume the path IS in the deny list" -> operation blocked
- For allow-list checks: `False` means "assume the path is NOT in the allow list" -> operation blocked
- Both result in fail-closed behavior, just through different mechanisms

---

## Error Message Information Leakage Check -- PASS

All deny responses use `Path(file_path).name` (filename only) or generic messages. No full paths, stack traces, or internal state exposed to users via stdout.

| Deny Response Location | Content | Leaks Info? |
|------------------------|---------|-------------|
| L2263 | "Invalid hook input (malformed JSON)" | No |
| L2276 | "Invalid tool input structure" | No |
| L2292 | "Invalid file path type" | No |
| L2298 | "Invalid file path (contains null byte)" | No |
| L2306 | "Cannot resolve file path: {Path(file_path).name}" | No (name only) |
| L2319 | "Symlink points outside project: {Path(file_path).name}" | No (name only) |
| L2348 | "Path is outside project directory" | No |
| L2357 | "Protected system file: {Path(file_path).name}" | No (name only) |
| L2370 | "Protected file (no access): {Path(file_path).name}" | No (name only) |
| L2384 | "Read-only file: {Path(file_path).name}" | No (name only) |
| L2402 | "Protected from overwrite: {Path(file_path).name}" | No (name only) |

**Minor finding (LOW)**: Log message at L2181 uses raw `path` instead of `truncate_path(path)`:
```python
log_guardian("WARN", f"Cannot normalize path for self-guardian check: {path}")
```
This goes to log file only (not stdout/user) so it is not an information leakage vulnerability, but inconsistent with the pattern used elsewhere. Should be harmonized.

---

## Test Coverage Assessment

The test file `tests/security/test_advisory_failclosed.py` (680 lines, 8 test classes, ~26 test methods) covers all three advisories:

| Test Class | Tests | What It Verifies |
|-----------|-------|-----------------|
| TestAdvisory1_VariableShadowing | 1 | Source code inspection: nodelete_resolved variable naming |
| TestAdvisory2_TOCTOU_FailClosed | 4 | Exists error blocks write, existing/new noDelete files |
| TestAdvisory3_ExpandPath_FailClosed | 3 | OSError/PermissionError propagation, normal operation |
| TestAdvisory3_NormalizePathForMatching_FailClosed | 2 | Error propagation, normal operation |
| TestAdvisory3_MatchPathPattern_DefaultOnError | 4 | True/False/default error returns, normal matching |
| TestAdvisory3_DenyChecks_FailClosed | 4 | All 4 deny-check functions with normalization errors |
| TestAdvisory3_IsSelfGuardianPath_FailClosed | 3 | Input path error, config path error, normal operation |
| TestAdvisory3_RunPathGuardianHook_ResolveFailure | 3 | Write/Read/Edit all deny on resolve failure (subprocess) |

**Test quality note**: `test_exists_error_blocks_write` (L177-206) sets up an expand_path mock but runs the guardian as a subprocess, which does not inherit the mock. The test still validates correct behavior because the file physically exists (created by `_setup_project_with_config(tmpdir, files=["CLAUDE.md"])`). The mock is dead code in this test but does not invalidate the assertion.

---

## Remaining Fail-Open Patterns in _guardian_utils.py

### Pre-existing (NOT introduced by advisory fixes)

1. **Dead `normalize_path()` (L918-951)** -- fail-open `return path` on error. Never called. Should be deleted.

2. **`except OSError` at L2304 is narrower than necessary**: `Path.resolve()` can raise `RuntimeError` (symlink loops), not just OSError. However, the wrapper scripts' top-level `except Exception` safety net catches this and denies. NOT a security gap, just imprecise.

3. **Auto-commit functions** (git_has_staged_changes L1654, ensure_git_config L1913, etc.) -- fail-open by design per CLAUDE.md: "Auto-commit is fail-open by design."

4. **`_safe_regex_search()` (L826-831)** -- returns None on regex errors. In bash_guardian, no-match for block patterns means allow. This is a config error scenario, not a bypass vector.

5. **`is_symlink_escape()` (L1019-1022)** and **`is_path_within_project()` (L1053-1056)** -- both already fail-closed (return True and False respectively on error). These were listed in CLAUDE.md "Known Security Gaps" but are already correctly implemented.

---

## Security Verdict

### PASS -- All 3 advisory fixes are correctly implemented

**ADVISORY-1 (Variable Shadowing)**: Fixed. `nodelete_resolved` replaces `resolved` in noDelete block. No variable shadowing.

**ADVISORY-2 (TOCTOU Fail-Closed)**: Fixed. exists() error path uses `file_exists=True` (fail-closed). The inherent TOCTOU race between pre-hook check and actual file write is an architecture limitation that cannot be resolved at this layer.

**ADVISORY-3 (Fail-Closed Normalization)**: Fixed. All 10 sub-items verified. Exception propagation chain: inner functions raise -> boundary functions catch and deny. `default_on_error` polarity is correct for every caller.

### No new fail-open paths introduced by the advisory fixes.

### Minor recommendations (non-blocking):
1. Delete dead `normalize_path()` function at L918-951 to prevent future accidental use
2. Broaden `except OSError` to `except (OSError, RuntimeError)` at L2304 for better error messages on symlink loops
3. Harmonize log message at L2181 to use `truncate_path(path)` instead of raw `path`
