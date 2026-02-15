# V2 Final Validation Report
## Date: 2026-02-15

## V1 Finding Resolution

### F1: `except OSError` -> `except (OSError, RuntimeError)` at L2304

**Status: RESOLVED**

Verified at `_guardian_utils.py:2304`. The exception handler now reads:

```python
except (OSError, RuntimeError) as e:
```

This catches both `OSError` (disk I/O, NFS failures, permission errors) and `RuntimeError` (symlink loops from `Path.resolve()`). Previously, `RuntimeError` would propagate uncaught to the wrapper's top-level `except Exception` safety net. Now it is handled cleanly with a proper deny response and log message.

### T1: `test_exists_error_blocks_write` passes for wrong reason (dead mock)

**Status: RESOLVED**

The test at `test_advisory_failclosed.py:177-236` has been rewritten to use a subprocess monkeypatch approach. Key improvements:

1. Project is created WITHOUT the file (`files=[]`), so the file does NOT physically exist
2. Uses inline Python wrapper code (`wrapper_code`) that patches `Path.exists` to raise `OSError` selectively for CLAUDE.md paths
3. Pre-loads guardian config before patching to avoid config-loading interference
4. The deny can ONLY come from the fail-closed error handler (`file_exists = True` on exception at L2393-2395), not from the file actually existing

This directly exercises the `except Exception: file_exists = True` code path in the noDelete block.

---

## Source Code Verification

### ADVISORY-1: Variable Shadowing

**Location:** `_guardian_utils.py:2390-2392`

Verified. The noDelete block uses:
```python
nodelete_resolved = expand_path(file_path)
file_exists = nodelete_resolved.exists()
```

No shadowing of the outer `resolved = resolve_tool_path(file_path)` at L2303.

### ADVISORY-2: TOCTOU Fail-Closed

**Location:** `_guardian_utils.py:2389-2395`

Verified. The exists() check is wrapped in try/except:
```python
try:
    nodelete_resolved = expand_path(file_path)
    file_exists = nodelete_resolved.exists()
except Exception:
    log_guardian("WARN", f"Cannot verify existence for noDelete check: {path_preview}")
    file_exists = True  # Fail-closed: assume exists on error
```

- `except Exception` (broad catch) handles OSError, PermissionError, and any other failures
- `file_exists = True` on error means the write is denied (fail-closed)
- Log uses `path_preview` (truncated), no information leakage

### ADVISORY-3: Fail-Closed Normalization

**Location:** Multiple functions in `_guardian_utils.py`

All 10 sub-items verified:

| Sub-item | Function | Line | Status |
|----------|----------|------|--------|
| 3a | `expand_path()` | L954-971 | No try/except, raises on error |
| 3b | `normalize_path_for_matching()` | L1059-1084 | No try/except, raises on error |
| 3c | `resolve_tool_path()` | L2220-2239 | No except block, raises on error |
| 3d | `match_path_pattern()` | L1121 | `default_on_error` parameter (default=False) |
| 3e | `match_zero_access()` | L1203 | `default_on_error=True` (fail-closed for deny-list) |
| 3f | `match_read_only()` | L1217 | `default_on_error=True` (fail-closed for deny-list) |
| 3g | `match_no_delete()` | L1231 | `default_on_error=True` (fail-closed for deny-list) |
| 3h | `match_allowed_external_path()` | L1253 | Default False (fail-closed for allow-list) |
| 3i | `is_self_guardian_path()` | L2177-2214 | Two try/except blocks, both return True on error |
| 3j | `run_path_guardian_hook()` | L2302-2307 | `except (OSError, RuntimeError)` -> deny |

### V1 Security Minor Recommendation (RuntimeError)

Confirmed implemented. L2304 now catches `(OSError, RuntimeError)` instead of just `OSError`.

---

## Test File Verification

### `test_advisory_failclosed.py` (26 tests, 8 test classes)

**`test_exists_error_blocks_write` subprocess verification:**
- Uses subprocess with inline wrapper code (L195-219)
- NOT an in-process mock -- the monkeypatch runs inside the subprocess
- Patches `Path.exists` selectively for CLAUDE.md paths
- File does NOT exist on disk (`files=[]`) -- deny is from error handler only
- **Verdict: Properly tests the TOCTOU fail-closed exception path**

**All 26 tests have meaningful assertions:**

| Test | Assertion Type |
|------|---------------|
| `test_nodelete_variable_not_shadowed` | Source inspection: assertIn/assertNotIn |
| `test_exists_error_blocks_write` | assertEqual(decision, "deny") |
| `test_existing_nodelete_file_blocked` | assertEqual(decision, "deny") |
| `test_new_nodelete_file_allowed` | assertIn(decision, ("allow", None)) |
| `test_exists_returns_false_allows_write` | assertIn(decision, ("allow", None)) |
| `test_expand_path_raises_on_oserror` | assertRaises(OSError) |
| `test_expand_path_raises_on_permission_error` | assertRaises(PermissionError) |
| `test_expand_path_normal_operation` | assertIsInstance, assertTrue |
| `test_normalize_raises_when_expand_path_fails` | assertRaises(OSError) |
| `test_normalize_normal_operation` | assertIsInstance, assertIn |
| `test_default_on_error_true_returns_true_on_exception` | assertTrue |
| `test_default_on_error_false_returns_false_on_exception` | assertFalse |
| `test_default_on_error_default_is_false` | assertFalse |
| `test_normal_matching_unaffected` | assertTrue (x2) |
| `test_match_zero_access_failclosed` | assertTrue |
| `test_match_read_only_failclosed` | assertTrue |
| `test_match_no_delete_failclosed` | assertTrue |
| `test_match_allowed_external_failclosed` | assertIsNone |
| `test_normalization_error_returns_true` | assertTrue |
| `test_active_config_normalization_error_returns_true` | assertTrue |
| `test_normal_operation` | assertFalse |
| `test_resolve_raises_on_oserror` | assertRaises(OSError) |
| `test_normal_resolution` | assertIsInstance, assertTrue |
| `test_write_guardian_resolve_failure_denies` | assertEqual(decision, "deny") |
| `test_read_guardian_resolve_failure_denies` | assertEqual(decision, "deny") |
| `test_edit_guardian_resolve_failure_denies` | assertEqual(decision, "deny") |

All assertions are meaningful and specific. No vacuous pass-throughs.

---

## Test Suite Results

| Test Suite | File | Tests | Passed | Failed |
|-----------|------|-------|--------|--------|
| Advisory | `test_advisory_failclosed.py` | 26 | 26 | 0 |
| P0/P1 Fail-Closed | `test_p0p1_failclosed.py` | 34 | 34 | 0 |
| Core Comprehensive | `test_p0p1_comprehensive.py` | 180 | 180 | 0 |
| External Path Mode | `test_external_path_mode.py` | 39 | 39 | 0 |
| Regression: External | `test_allowed_external.py` | 16 | 16 | 0 |
| Regression: Errno36 | `test_errno36_fix.py` | 41 | 41 | 0 |
| Regression: Errno36 E2E | `test_errno36_e2e.py` | 16 | 16 | 0 |
| **TOTAL** | | **352** | **352** | **0** |

**Zero failures. Zero regressions.**

---

## Final Sign-Off

### APPROVED

All 3 advisory fixes are correctly implemented and tested:

1. **ADVISORY-1 (Variable Shadowing)**: `nodelete_resolved` replaces `resolved` in the noDelete block. No variable shadowing. Verified in source and by structural test.

2. **ADVISORY-2 (TOCTOU Fail-Closed)**: `expand_path()` + `.exists()` wrapped in `try/except Exception` with `file_exists = True` on error. Fail-closed behavior confirmed by subprocess test that exercises the actual exception path (file does not exist on disk, deny comes from error handler).

3. **ADVISORY-3 (Fail-Closed Normalization)**: All 10 sub-items verified. Exception propagation chain is complete. `default_on_error` polarity is correct (True for deny-lists, False for allow-lists). `is_self_guardian_path` has two independent try/except blocks both returning True. `run_path_guardian_hook` catches `(OSError, RuntimeError)` from `resolve_tool_path` and denies.

Both V1 findings are resolved:
- **F1**: `except OSError` broadened to `except (OSError, RuntimeError)` at L2304
- **T1**: `test_exists_error_blocks_write` rewritten with subprocess monkeypatch, tests the actual exception path

352 tests pass across 7 test suites with zero failures and zero regressions.
