# V1 Test Execution Report

**Executed by**: v1-testrun
**Date**: 2026-02-15
**Task**: #5 - [V1] Test execution and regression check (advisory fixes round)

---

## 1. New Advisory Tests (`tests/security/test_advisory_failclosed.py`)

**Result: 26/26 PASSED**

```
Ran 26 tests in 0.356s
OK
```

### Test Classes and Coverage:

| Class | Tests | Status |
|-------|-------|--------|
| `TestAdvisory1_VariableShadowing` | 1 | ALL PASS |
| `TestAdvisory2_TOCTOU_FailClosed` | 4 | ALL PASS |
| `TestAdvisory3_MatchPathPattern_DefaultOnError` | 4 | ALL PASS |
| `TestAdvisory3_DenyChecks_FailClosed` | 4 | ALL PASS |
| `TestAdvisory3_ExpandPath_FailClosed` | 3 | ALL PASS |
| `TestAdvisory3_NormalizePathForMatching_FailClosed` | 2 | ALL PASS |
| `TestAdvisory3_ResolveToolPath_FailClosed` | 2 | ALL PASS |
| `TestAdvisory3_IsSelfGuardianPath_FailClosed` | 3 | ALL PASS |
| `TestAdvisory3_RunPathGuardianHook_ResolveFailure` | 3 | ALL PASS |

---

## 2. P0/P1 Tests (`tests/security/test_p0p1_failclosed.py`)

**Result: 34/34 PASSED**

```
Ran 34 tests in 1.101s
OK
```

All original P0/P1 tests continue to pass. No regressions.

---

## 3. Core Tests (`tests/core/`)

| File | Tests | Passed | Failed | Status |
|------|-------|--------|--------|--------|
| `test_p0p1_comprehensive.py` | 180 | 180 | 0 | PASS |
| `test_external_path_mode.py` | 39 | 39 | 0 | PASS |
| `test_v2fixes.py` | 125 | 124 | 1 | 1 PRE-EXISTING FAILURE |

**Total Core: 344 tests, 343 passed, 1 pre-existing failure**

### Pre-existing failure in `test_v2fixes.py`:
- **Test**: `TestF2_LnWritePattern.test_ln_pattern_in_source`
- **Error**: `AssertionError: '\\bln\\s+' not found in source`
- **Cause**: Test checks for a specific regex pattern in `bash_guardian.py` source code, but the pattern syntax changed in a prior commit. This is a stale source-code-checking test.
- **Identical to prior round**: YES (same failure in `temp/teammate-test-executor-output.md`). NOT caused by advisory changes.

---

## 4. Security Tests (`tests/security/`)

| File | Tests | Passed | Failed | Status |
|------|-------|--------|--------|--------|
| `test_advisory_failclosed.py` | 26 | 26 | 0 | PASS (NEW) |
| `test_p0p1_failclosed.py` | 34 | 34 | 0 | PASS |
| `test_v2fixes_adversarial.py` | 143 | 143 | 0 | PASS |
| `test_v2_crossmodel.py` | 20 | 20 | 0 | PASS |

**Total Security (tested suites): 223 tests, 223 passed, 0 failures**

Note: `test_bypass_v2.py` and `test_v2_adversarial.py` were not in the requested test list. They have pre-existing failures documented in the prior round.

---

## 5. Regression Tests (`tests/regression/`)

| File | Tests | Passed | Failed | Status |
|------|-------|--------|--------|--------|
| `test_allowed_external.py` | 16 | 16 | 0 | PASS |
| `test_errno36_fix.py` | 41 | 41 | 0 | PASS |
| `test_errno36_e2e.py` | 16 | 16 | 0 | PASS |

**Total Regression: 73 tests, all passed, zero regressions**

---

## 6. Full Suite Summary

| Suite | Total Tests | Passed | Failed | New Failures |
|-------|-------------|--------|--------|--------------|
| Core | 344 | 343 | 1 | 0 |
| Security | 223 | 223 | 0 | 0 |
| Regression | 73 | 73 | 0 | 0 |
| **TOTAL** | **640** | **639** | **1** | **0** |

**Zero new failures introduced by advisory changes.**

The 1 failure is pre-existing (`test_ln_pattern_in_source`) and identical to the prior P0/P1 verification round.

---

## 7. Cross-Reference: Advisory Test Cases vs Advisory Plan

### ADVISORY-1: Variable shadowing

| Plan requirement | Test | Status |
|------------------|------|--------|
| Rename `resolved` to `nodelete_resolved` at L2382 | `test_nodelete_variable_not_shadowed` | PASS |

### ADVISORY-2: TOCTOU in exists() check

| Plan requirement | Test | Status |
|------------------|------|--------|
| Write to existing noDelete file -> BLOCKED | `test_existing_nodelete_file_blocked` | PASS |
| Write to new noDelete file -> ALLOWED (exists()=False path) | `test_new_nodelete_file_allowed` | PASS |
| Write to new noDelete file -> ALLOWED (alternative) | `test_exists_returns_false_allows_write` | PASS |
| expand_path raises OSError in noDelete check -> BLOCKED (fail-closed) | `test_exists_error_blocks_write` | PASS |
| Original P0/P1 noDelete tests unaffected | 8 tests in `test_p0p1_failclosed.py` | ALL PASS |

**Note**: Plan originally proposed removing exists() entirely, then revised to "keep exists() with fail-closed error path". Tests confirm the adopted approach: exists() is retained, but errors fail-closed (block).

### ADVISORY-3: Fail-open normalization helpers

| Plan requirement | Test | Status |
|------------------|------|--------|
| `match_path_pattern` default_on_error=True returns True on exception | `test_default_on_error_true_returns_true_on_exception` | PASS |
| `match_path_pattern` default_on_error=False returns False on exception | `test_default_on_error_false_returns_false_on_exception` | PASS |
| `match_path_pattern` default is False (backward compat) | `test_default_on_error_default_is_false` | PASS |
| Normal matching unaffected | `test_normal_matching_unaffected` | PASS |
| `match_zero_access` fails-closed on error | `test_match_zero_access_failclosed` | PASS |
| `match_read_only` fails-closed on error | `test_match_read_only_failclosed` | PASS |
| `match_no_delete` fails-closed on error | `test_match_no_delete_failclosed` | PASS |
| `match_allowed_external_path` fails-closed on error (returns None) | `test_match_allowed_external_failclosed` | PASS |
| `expand_path` raises on OSError (no fallback to raw path) | `test_expand_path_raises_on_oserror` | PASS |
| `expand_path` raises on PermissionError | `test_expand_path_raises_on_permission_error` | PASS |
| `expand_path` normal operation unaffected | `test_expand_path_normal_operation` | PASS |
| `normalize_path_for_matching` raises when expand_path fails | `test_normalize_raises_when_expand_path_fails` | PASS |
| `normalize_path_for_matching` normal operation unaffected | `test_normalize_normal_operation` | PASS |
| `resolve_tool_path` raises on OSError | `test_resolve_raises_on_oserror` | PASS |
| `resolve_tool_path` normal resolution unaffected | `test_normal_resolution` | PASS |
| `is_self_guardian_path` fails-closed on normalization error | `test_normalization_error_returns_true` | PASS |
| `is_self_guardian_path` fails-closed on active config error | `test_active_config_normalization_error_returns_true` | PASS |
| `is_self_guardian_path` normal operation unaffected | `test_normal_operation` | PASS |
| `run_path_guardian_hook` denies on resolve_tool_path failure (Write) | `test_write_guardian_resolve_failure_denies` | PASS |
| `run_path_guardian_hook` denies on resolve_tool_path failure (Read) | `test_read_guardian_resolve_failure_denies` | PASS |
| `run_path_guardian_hook` denies on resolve_tool_path failure (Edit) | `test_edit_guardian_resolve_failure_denies` | PASS |

**Plan listed 11 new tests needed. Actual implementation has 26 tests covering all 11 requirements plus additional edge cases (normal operation sanity checks, PermissionError, active config path errors).**

---

## 8. Comparison with P0/P1 Round Baseline

| Metric | P0/P1 Round | Advisory Round | Delta |
|--------|-------------|----------------|-------|
| Total tests run | 778+ | 640 | N/A (different test list) |
| New test failures | 0 | 0 | No change |
| Pre-existing failures | 20+ | 1 | N/A (fewer pre-existing suites tested) |
| Core test_p0p1_comprehensive | 180/180 | 180/180 | No change |
| Core test_external_path_mode | 39/39 | 39/39 | No change |
| Core test_v2fixes | 124/125 | 124/125 | No change (same pre-existing failure) |
| Regression tests | 73/73 | 73/73 | No change |
| test_v2fixes_adversarial | 143/143 | 143/143 | No change |
| test_v2_crossmodel | 20/20 | 20/20 | No change |

---

## 9. SyntaxWarning Note

One non-fatal SyntaxWarning observed in `test_v2fixes_adversarial.py:339`:
```
SyntaxWarning: invalid escape sequence '\.'
```
This is a docstring issue (unescaped backslash), not a test failure. It was present in the prior round as well.

---

## 10. Conclusion

**VERDICT: PASS - All advisory changes verified, zero regressions introduced.**

- All 26 new advisory tests pass
- All pre-existing test suites show identical results before and after advisory changes
- All advisory plan requirements have corresponding test coverage (26 tests for 11 planned)
- ADVISORY-1: Variable shadowing fix verified (1 test)
- ADVISORY-2: TOCTOU fix with fail-closed error path verified (4 tests)
- ADVISORY-3: Fail-closed normalization helpers verified (21 tests)
- Zero new failures across 640 tests
- 1 pre-existing failure unchanged (stale source-code-checking test in test_v2fixes.py)
