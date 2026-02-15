# V1 Logic and Coverage Review Report
## Date: 2026-02-15
## Reviewer: v1-logic (v1-logic-redo agent)

---

## Code Logic Verification

### ADVISORY-1: Variable Shadowing (nodelete_resolved)

**Location:** `_guardian_utils.py:2387-2406`

**Verdict: CORRECT**

The noDelete check block at L2391 uses `nodelete_resolved = expand_path(file_path)` and L2392 uses `nodelete_resolved.exists()`. The outer `resolve_tool_path` result at L2303 is assigned to `resolved` and subsequently extracted to `path_str = str(resolved)` at L2308. There is no name collision.

Before this fix, `resolved = expand_path(file_path)` would have overwritten the L2303 `resolved` variable. While in the current control flow this is not a runtime bug (because `path_str` is already extracted at L2308 and `resolved` isn't used again after the noDelete block), the fix is a correct defensive measure eliminating latent confusion and potential future bugs.

### ADVISORY-2: TOCTOU Fail-Closed

**Location:** `_guardian_utils.py:2389-2395`

**Verdict: CORRECT**

The `expand_path(file_path)` + `.exists()` calls in the noDelete block are wrapped in a `try/except Exception` that sets `file_exists = True` on error. This is correct fail-closed behavior:

1. `match_no_delete(path_str)` returns True (path matched pattern)
2. Try to resolve and check existence
3. On any exception -> `file_exists = True` (fail-closed: assume file exists)
4. If file exists -> deny the write

This correctly handles TOCTOU races (file deleted between check and use) and OS-level errors (NFS failures, permission errors, device not available, etc.).

### ADVISORY-3: Fail-Closed Normalization Helpers

**ADVISORY-3a: expand_path() (L954-971) -- CORRECT**

No try/except. Calls `Path(path).expanduser()`, optionally prepends project_dir, and calls `.resolve()`. OSError/PermissionError from `.resolve()` propagate to callers. The docstring correctly documents `Raises: OSError`. All callers handle exceptions appropriately (see Caller Completeness Check below).

**ADVISORY-3b: normalize_path_for_matching() (L1059-1084) -- CORRECT**

No try/except. Calls `expand_path(path)` which may raise, and exceptions propagate. Callers handle this via their own try/except blocks.

**ADVISORY-3c: resolve_tool_path() (L2220-2239) -- CORRECT**

No try/except. Calls `path.resolve()` which may raise OSError. The single caller in `run_path_guardian_hook` at L2302-2307 catches `OSError` and emits a deny response.

**ADVISORY-3d: match_path_pattern() default_on_error (L1121) -- CORRECT**

The `default_on_error` parameter (default=False) is returned from the `except Exception` block at L1187-1189. The semantics are:
- `True`: for deny-list checks (fail-closed = assume path matches the deny pattern)
- `False`: for allow-list checks (fail-closed = assume path does NOT match the allow pattern)

The docstring at L1133-1134 clearly explains this.

**ADVISORY-3e/f/g: match_zero_access/read_only/no_delete (L1192-1231) -- CORRECT**

All three pass `default_on_error=True`. On normalization error, the pattern is treated as matched -> path treated as protected -> access denied. Correct fail-closed for deny-lists.

**ADVISORY-3h: match_allowed_external_path (L1234-1259) -- CORRECT**

Uses default `default_on_error=False` (no kwarg). On normalization error, the pattern is NOT matched -> path is NOT treated as externally allowed -> falls through to "outside project" deny. Correct fail-closed for allow-lists.

**ADVISORY-3i: is_self_guardian_path (L2177-2214) -- CORRECT**

Two independent try/except blocks:
1. L2178-2182: Wraps `normalize_path_for_matching(path)` for input path. Returns `True` on error (fail-closed: can't verify it's NOT a guardian path -> protect it).
2. L2209-2213: Wraps `normalize_path_for_matching(active_config)` for active config path. Returns `True` on error (fail-closed: can't verify -> protect).

Both correctly return True on failure, causing the caller in `run_path_guardian_hook` (L2352) to deny the operation.

**ADVISORY-3j: run_path_guardian_hook resolve_tool_path catch (L2302-2307) -- CORRECT**

Catches `OSError` from `resolve_tool_path`, logs error, emits deny response, exits. Uses `Path(file_path).name` in deny message (safe).

---

## Test Coverage Analysis

### Test Class: TestAdvisory1_VariableShadowing (1 test)

- `test_nodelete_variable_not_shadowed`: Source code structural test. Parses the actual source file, finds the noDelete block, and checks for `nodelete_resolved` usage. Also verifies no bare `resolved = expand_path(` exists. **CORRECT** -- structural test catches regressions even if code is refactored. No early return risk (reads source directly).

### Test Class: TestAdvisory2_TOCTOU_FailClosed (4 tests)

- `test_exists_error_blocks_write`: **ISSUE** -- This test defines a mock `expand_side_effect` in the test process but runs the hook as a subprocess. The mock is NOT active in the subprocess. The test passes because the file physically exists (`files=["CLAUDE.md"]`), not because the TOCTOU exception path fires. The mock code is dead code.
  - **Impact**: Low. The TOCTOU exception path is a one-liner defensive fallback. The test still verifies the main noDelete deny behavior. To properly test the exception path, it would need the subprocess monkeypatch wrapper approach from `TestAdvisory3_RunPathGuardianHook_ResolveFailure`.
- `test_existing_nodelete_file_blocked`: Subprocess test. File exists + noDelete match -> deny. **CORRECT.** Exercises the `file_exists=True` -> deny branch.
- `test_new_nodelete_file_allowed`: Subprocess test. File does NOT exist + noDelete match -> `file_exists=False` -> allow. **CORRECT.** Exercises the "no deny" branch.
- `test_exists_returns_false_allows_write`: Same as above but for README.md. Slightly redundant but validates another noDelete pattern.

### Test Class: TestAdvisory3_ExpandPath_FailClosed (3 tests)

- `test_expand_path_raises_on_oserror`: Mocks `Path.resolve` -> OSError. Verifies `expand_path` raises. **CORRECT.** `Path.resolve` is the last call, no early returns to bypass.
- `test_expand_path_raises_on_permission_error`: Same with PermissionError. **CORRECT.**
- `test_expand_path_normal_operation`: Happy path. **CORRECT.**

### Test Class: TestAdvisory3_NormalizePathForMatching_FailClosed (2 tests)

- `test_normalize_raises_when_expand_path_fails`: Patches `_guardian_utils.expand_path` at module level. Verifies exception propagates from `normalize_path_for_matching`. **CORRECT.** The patch targets L1076.
- `test_normalize_normal_operation`: Happy path. **CORRECT.**

### Test Class: TestAdvisory3_MatchPathPattern_DefaultOnError (4 tests)

- `test_default_on_error_true_returns_true_on_exception`: Patches normalize to raise. Verifies True returned. **CORRECT.** Exercises L1187 except block.
- `test_default_on_error_false_returns_false_on_exception`: Same, False. **CORRECT.**
- `test_default_on_error_default_is_false`: No kwarg provided. **CORRECT.**
- `test_normal_matching_unaffected`: Both True/False kwargs produce same correct match result on normal paths. **CORRECT.**
- **No early return risk**: `normalize_path_for_matching` at L1141 is the first operation in the try block.

### Test Class: TestAdvisory3_DenyChecks_FailClosed (4 tests)

- `test_match_zero_access_failclosed`: Sets up config with real patterns, patches normalize to raise. Verifies `match_zero_access` returns True. **CORRECT.** Config is loaded (non-empty pattern list), `any()` calls `match_path_pattern` which triggers the error -> `default_on_error=True` -> returns True.
- `test_match_read_only_failclosed`: Same pattern. **CORRECT.**
- `test_match_no_delete_failclosed`: Same pattern. **CORRECT.**
- `test_match_allowed_external_failclosed`: Verifies returns None on error. **CORRECT.** Default `default_on_error=False` -> all patterns return False -> `any()` returns False -> returns None.
- **Critical detail verified**: All four tests set up real guardian config (copying `guardian.default.json`), so the pattern lists are non-empty and the `any()` loop actually iterates.

### Test Class: TestAdvisory3_IsSelfGuardianPath_FailClosed (3 tests)

- `test_normalization_error_returns_true`: Patches normalize to always raise. Verifies True returned. **CORRECT** -- hits L2178-2182 first try/except.
- `test_active_config_normalization_error_returns_true`: Uses `selective_fail` (counter-based) to let first normalize succeed but fail second. Mocks `get_active_config_path` to return a value. **CORRECT** -- hits L2209-2213 second try/except.
  - **Verified**: First call (L2179) succeeds. The input path `{tmpdir}/somefile.txt` does NOT match any SELF_GUARDIAN_PATHS (loop at L2194-2204 completes without match). `get_active_config_path` returns non-None, so L2210 is reached. Second normalize call raises -> returns True.
- `test_normal_operation`: Non-guardian path returns False. **CORRECT.**

### Test Class: TestAdvisory3_ResolveToolPath_FailClosed (2 tests)

- `test_resolve_raises_on_oserror`: Mocks `Path.resolve` -> OSError. **CORRECT.**
- `test_normal_resolution`: Happy path. **CORRECT.**

### Test Class: TestAdvisory3_RunPathGuardianHook_ResolveFailure (3 tests)

- Uses subprocess wrapper that monkeypatches `resolve_tool_path` to raise OSError in child process. Clever and correct approach.
- `test_write_guardian_resolve_failure_denies`: Verifies Write hook denies on resolve failure. **CORRECT.**
- `test_read_guardian_resolve_failure_denies`: Verifies Read hook denies. **CORRECT.**
- `test_edit_guardian_resolve_failure_denies`: Verifies Edit hook denies. **CORRECT.**
- **No early return risk**: Hook input is well-formed, tool_name matches, file_path is valid string. Execution reaches L2302 `resolve_tool_path` call.

---

## Caller Completeness Check

### expand_path() -- 3 callers, all in _guardian_utils.py

| Line | Caller | Exception Handling | Verdict |
|------|--------|-------------------|---------|
| L1045 | `is_path_within_project()` | `except Exception` at L1053 -> returns `False` (fail-closed) | SAFE |
| L1076 | `normalize_path_for_matching()` | No catch -- propagates upward (by design) | SAFE (callers handle) |
| L2391 | noDelete block in `run_path_guardian_hook()` | `except Exception` at L2393 -> `file_exists = True` (fail-closed) | SAFE |

Confirmed: no callers in bash_guardian.py or thin wrapper scripts.

### normalize_path_for_matching() -- 3 callers, all in _guardian_utils.py

| Line | Caller | Exception Handling | Verdict |
|------|--------|-------------------|---------|
| L1141 | `match_path_pattern()` | `except Exception` at L1187 -> returns `default_on_error` | SAFE |
| L2179 | `is_self_guardian_path()` (input path) | `except Exception` at L2180 -> returns `True` (fail-closed) | SAFE |
| L2210 | `is_self_guardian_path()` (active config) | `except Exception` at L2211 -> returns `True` (fail-closed) | SAFE |

Confirmed: no callers in bash_guardian.py or thin wrapper scripts.

### resolve_tool_path() -- 1 caller

| Line | Caller | Exception Handling | Verdict |
|------|--------|-------------------|---------|
| L2303 | `run_path_guardian_hook()` | `except OSError` at L2304 -> emits deny JSON | SAFE (with finding F1 below) |

### match_path_pattern() -- 5 callers, all in _guardian_utils.py

| Line | Caller | default_on_error | Semantically Correct? |
|------|--------|-----------------|----------------------|
| L1203 | `match_zero_access()` | `True` | YES -- deny-list, fail-closed |
| L1217 | `match_read_only()` | `True` | YES -- deny-list, fail-closed |
| L1231 | `match_no_delete()` | `True` | YES -- deny-list, fail-closed |
| L1253 | `match_allowed_external_path()` (write) | `False` (default) | YES -- allow-list, fail-closed |
| L1257 | `match_allowed_external_path()` (read) | `False` (default) | YES -- allow-list, fail-closed |

### bash_guardian.py indirect callers

`bash_guardian.py` calls `match_zero_access` (L1052), `match_read_only` (L1060), `match_no_delete` (L1078), and `match_allowed_external_path` (L522, L556, L563, L1069). These are the public API -- all correctly configured with `default_on_error` internally. No direct calls to `expand_path`, `normalize_path_for_matching`, or `resolve_tool_path`.

### Thin wrappers (edit_guardian.py, read_guardian.py, write_guardian.py)

All call only `run_path_guardian_hook(tool_name)` which handles all error paths. Each wrapper has a top-level `except Exception` block that emits deny (fail-closed).

**All callers are handled. No unguarded call sites exist.**

---

## Edge Case Analysis

### Covered in code (not all explicitly tested):

| Edge case | Handling | Location |
|-----------|----------|----------|
| Empty string path | `if not file_path:` -> allow (legitimate for some tools) | L2283-2288 |
| None/non-string path | `isinstance(file_path, str)` check -> deny | L2290-2293 |
| Null bytes | Explicit `\x00` check -> deny | L2296-2299 |
| Malformed JSON | `JSONDecodeError` -> deny | L2260-2264 |
| Very long paths (>PATH_MAX) | OSError (ENAMETOOLONG) from `.resolve()`, caught by all relevant try/except blocks | Propagation chain |
| Unicode paths | Handled natively by `pathlib.Path`. Invalid encoding raises `OSError` or subclass, caught by `except Exception` | All callers |

### Partially covered:
- **TOCTOU exception path**: The `except Exception: file_exists = True` branch (L2393-2395) is not directly tested via the correct subprocess approach. See test issue T1 below.

### Not covered (low priority):
- **Symlink loops in resolve_tool_path**: See Finding F1 below. `RuntimeError` from `Path.resolve()` on symlink loops is not caught by `except OSError` at L2304.

### Dead code observation:
- `normalize_path` function at L918-951 still exists with fail-open behavior (L948-951 returns original path on error). However, it has **zero callers** anywhere in the codebase. It is dead code. Consider removing to avoid confusion, but it poses no security risk.

---

## Findings

### F1: RuntimeError gap in resolve_tool_path catch (Pre-existing, not a regression)

**Location**: `run_path_guardian_hook()` L2302-2307

```python
try:
    resolved = resolve_tool_path(file_path)
except OSError as e:
    ...deny...
```

`Path.resolve()` raises `RuntimeError` (not `OSError`) on symlink loops. The `except OSError` will not catch it. In practice, the uncaught exception would propagate to the top-level `except Exception` in the thin wrapper scripts, which emit deny. So this is ultimately fail-closed, but through the crash handler rather than the clean deny path.

**Severity**: Low. Pre-existing issue, exotic edge case, ultimately still fail-closed.
**Recommendation**: Change to `except (OSError, RuntimeError) as e:` for cleanliness.

### T1: test_exists_error_blocks_write mock not applied in subprocess

**Location**: `TestAdvisory2_TOCTOU_FailClosed.test_exists_error_blocks_write`

The test creates a Python mock for `expand_path` but runs the hook as a subprocess. Mocks do not cross process boundaries. The test passes because the file physically exists (created by `_setup_project_with_config`), not because the error handler sets `file_exists = True`.

**Impact**: The `except Exception: file_exists = True` code path at L2393-2395 is not tested. The test verifies the correct outcome (deny) but for the wrong reason.
**Recommendation**: Use the subprocess monkeypatch wrapper pattern (like `TestAdvisory3_RunPathGuardianHook_ResolveFailure._WRAPPER_TEMPLATE`) to properly test this path.

---

## Test Execution

All 26 tests pass:

```
$ python3 tests/security/test_advisory_failclosed.py
Ran 26 tests in 0.325s
OK
```

---

## Verdict

**PASS**

All three advisory fixes are logically correct and produce proper fail-closed behavior:

- **ADVISORY-1** (variable shadowing): Clean rename to `nodelete_resolved`. No logic impact. Structural test verifies.
- **ADVISORY-2** (TOCTOU fail-closed): `try/except Exception` with `file_exists = True` is correct. File-exists and file-not-exists paths both tested via subprocess.
- **ADVISORY-3** (fail-closed normalization): Exception propagation chain is complete. All callers handle errors. `default_on_error` usage is semantically correct (True for deny-lists, False for allow-lists). `is_self_guardian_path` has two independent try/except blocks both returning True. `run_path_guardian_hook` catches OSError from resolve and denies.

Two minor findings identified (neither are regressions from the advisory fixes):
- **F1** (Low): `except OSError` at L2304 should also catch `RuntimeError` for symlink loops
- **T1** (Medium): `test_exists_error_blocks_write` mock is dead code; test passes for the wrong reason
