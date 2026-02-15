# Work Log: Remaining Issues Resolution

> Started: 2026-02-15
> Status: **COMPLETE**

## Issues Summary

### Issue 1: Tuple truthiness landmine (MEDIUM)
- **Problem**: `match_allowed_external_path()` returns `tuple[bool, str]` - always truthy even when `(False, "")`
- **Solution**: Change to `str | None` return type (Option A)
  - Return `"readwrite"` | `"read"` | `None`
  - `None` is falsy, mode strings are truthy = safe
- **Files**: `_guardian_utils.py`, `bash_guardian.py`, `test_external_path_mode.py`, **`test_allowed_external.py`** (CRITICAL FIND!)

### Issue 2: No deprecation warning for old `allowedExternalPaths` key (MEDIUM)
- **Problem**: Old config key silently ignored after migration
- **Solution**: Add deprecation warning in `validate_guardian_config()` — it returns error strings that get logged as WARN by `load_guardian_config()`. Use "DEPRECATED:" prefix.
- **Files**: `_guardian_utils.py`, `test_external_path_mode.py`

### Issue 3: Loose type hint `-> tuple` (LOW)
- **Becomes moot** — resolved by Issue 1 (return `str | None`)

---

## External Model Consensus

| Aspect | Codex (codex-5.3) | Gemini (gemini-3-pro) | My Decision |
|--------|-------|--------|-------------|
| Return type | `Literal["read","readwrite"] | None` | `Literal["read","readwrite"] | None` | `str | None` (simpler, codebase style) |
| Enum vs strings | Optional StrEnum | String Literals | Strings (matches project style) |
| Deprecation location | `load_guardian_config()` | `validate_guardian_config()` | `validate_guardian_config()` (already wired to logging) |
| Function rename | Consider `get_allowed_external_mode()` | No rename needed | No rename (scope creep) |
| Atomic update | Required | Required | Yes, all files in one pass |

## Caller Analysis (Issue 1) — VERIFIED via fresh grep

### Source callers (7 total):

| Location | Current Usage | New Usage |
|----------|--------------|-----------|
| `_guardian_utils.py:1221` | Function definition `-> tuple` | `-> str | None` |
| `_guardian_utils.py:2297` | `matched, ext_mode = match_allowed_external_path(path_str)` | `ext_mode = match_allowed_external_path(path_str)` |
| `_guardian_utils.py:2298` | `if matched:` | `if ext_mode is not None:` |
| `bash_guardian.py:522` | `match_allowed_external_path(str(suffix_path))[0]` | `match_allowed_external_path(str(suffix_path))` |
| `bash_guardian.py:556` | `match_allowed_external_path(str(p))[0]` | `match_allowed_external_path(str(p))` |
| `bash_guardian.py:563` | `match_allowed_external_path(str(path))[0]` | `match_allowed_external_path(str(path))` |
| `bash_guardian.py:1065-1066` | `ext_matched, ext_mode = ...; if ext_matched and ...` | `ext_mode = ...; if ext_mode == "read":` |

### Test callers (2 files):

1. **`tests/core/test_external_path_mode.py`** — 20+ assertions comparing to tuples
2. **`tests/regression/test_allowed_external.py`** — 9 callers using tuple unpacking (CRITICAL FIND from Codex!)

---

## Pre-Implementation Checks
- [x] Vibe check done — on track, 2 adjustments noted
- [x] External model consultation (clink) done — strong consensus
- [x] All callers identified — 7 source + 2 test files
- [x] Regression test file discovered (missed by issue doc!)

## Implementation Progress
- [x] Issue 1: Change return type in `_guardian_utils.py` — `str | None`
- [x] Issue 1: Update callers in `bash_guardian.py` — 4 sites
- [x] Issue 1: Update tests in `test_external_path_mode.py` — 18+ assertions
- [x] Issue 1: Update tests in `test_allowed_external.py` — 9 callers
- [x] Issue 2: Add deprecation warning in `validate_guardian_config()`
- [x] Issue 2: Add 3 deprecation tests in `test_external_path_mode.py`
- [x] All 39 external path tests pass
- [x] All 180 core tests pass
- [x] Security test failures (17) confirmed pre-existing

## Verification Round 1 Results

| Teammate | Perspective | Verdict | Action Items |
|----------|-------------|---------|-------------|
| Security | Fail-closed, edge cases | **ALL 7 CHECKS PASS** | Advisory: Literal type hint (deferred) |
| API Contract | All callers complete | **ALL PASS** | Found/fixed stale config path in regression test |
| Test Correctness | Assertion accuracy | **PASS w/3 fixes** | Tightened 3 `assertIsNotNone` to `assertEqual` -- DONE |

Post-V1 actions:
- [x] Tightened 3 weak assertions in zeroAccess tests
- [x] Regression test config path fix applied (16/16 pass)
- [x] 39/39 core tests still pass
- Note: `temp/e2e_integration_test.py` has stale API (non-production, not fixing)

## Verification Round 2 Results

| Teammate | Perspective | Verdict | Details |
|----------|-------------|---------|---------|
| Diff Completeness | Every caller updated? | **PASS** | Codex confirmed all 4 bash_guardian.py callers, _guardian_utils.py caller, deprecation warning, test updates. No unintended changes. |
| Semantic Equivalence | Truth tables identical? | **PASS** | Gemini confirmed identical behavior for all 3 input states (write match, read match, no match) across all caller patterns. |
| Full Test Run | All tests green? | **PASS** | 39/39 external path + 16/16 regression + 180/180 core tests. Codex independently ran smoke test and confirmed. |

## Verification Summary
- [x] Verification Round 1 (complete) -- 3 teammates, 3 action items resolved
- [x] Verification Round 2 (complete) -- 3 teammates, all PASS, zero action items
