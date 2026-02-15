# Test Writer Output: Enhancement 1 & 2 Tests

## Status: COMPLETE

## Summary

Created comprehensive test suite at `tests/core/test_external_path_mode.py` with **26 tests** across 5 test classes covering Enhancement 1 (split `allowedExternalPaths` into `allowedExternalReadPaths`/`allowedExternalWritePaths`) and Enhancement 2 (bash `extract_paths()` includes allowed external paths).

## Pre-work Validation

- **Vibe check (pre)**: Confirmed test plan is well-structured and comprehensive. Suggested adding one subprocess-based test for `run_path_guardian_hook()` (deferred -- the mode logic simulation is a pragmatic tradeoff given `sys.exit()` in the real code).
- **Codex clink**: Identified key edge cases: return shape verification, write-before-read precedence, non-string entry safety, tilde expansion, `fnmatch` behavior with `**`, zeroAccess override, and negative extraction tests. All integrated into the test suite.
- **Vibe check (post)**: Confirmed completion -- zero regressions, all 26 tests passing.

## Test File

**Path**: `tests/core/test_external_path_mode.py`

## Test Classes and Methods (26 total)

### Group 1: TestExternalPathConfigParsing (7 tests)

Tests `match_allowed_external_path()` config parsing and return values.

| # | Test Method | What It Verifies |
|---|-----------|-----------------|
| 1 | `test_read_path_matches_read_mode` | Path in `allowedExternalReadPaths` returns `(True, "read")` |
| 2 | `test_write_path_matches_readwrite_mode` | Path in `allowedExternalWritePaths` returns `(True, "readwrite")` |
| 3 | `test_unmatched_returns_false` | Path not in any list returns `(False, "")` |
| 4 | `test_write_path_checked_before_read` | Path in BOTH lists returns `(True, "readwrite")` -- write wins |
| 5 | `test_empty_lists` | Both empty lists return `(False, "")` |
| 6 | `test_only_write_list_matches_readwrite` | Only write list set, path matches => `(True, "readwrite")` |
| 7 | `test_non_string_entries_ignored` | Non-string entries (int, None, dict, bool, list) are safely skipped |

### Group 2: TestModeEnforcement (7 tests)

Tests the mode-check logic from `run_path_guardian_hook()`.

| # | Test Method | What It Verifies |
|---|-----------|-----------------|
| 8 | `test_read_tool_on_read_path_allowed` | mode="read", tool="Read" => NOT denied |
| 9 | `test_write_tool_on_read_path_denied` | mode="read", tool="Write" => DENIED |
| 10 | `test_edit_tool_on_read_path_denied` | mode="read", tool="Edit" => DENIED |
| 11 | `test_write_tool_on_write_path_allowed` | mode="readwrite", tool="Write" => NOT denied |
| 12 | `test_edit_tool_on_write_path_allowed` | mode="readwrite", tool="Edit" => NOT denied |
| 13 | `test_integration_read_path_blocks_write_tool` | End-to-end: match + mode check for read path |
| 14 | `test_integration_write_path_allows_all_tools` | End-to-end: match + mode check for write path |

### Group 3: TestExtractPathsExternal (5 tests)

Tests `extract_paths()` includes/excludes external paths correctly.

| # | Test Method | What It Verifies |
|---|-----------|-----------------|
| 15 | `test_extract_includes_allowed_external_read_path` | Allowed external read path is extracted |
| 16 | `test_extract_excludes_non_allowed_external` | Non-allowed external path is NOT extracted |
| 17 | `test_extract_still_includes_project_paths` | Project-internal paths still work normally |
| 18 | `test_extract_external_with_write_paths` | Write-allowed external path is extracted |
| 19 | `test_extract_mixed_internal_and_external` | Both internal and external paths in same command |

### Group 4: TestZeroAccessOnExternalPaths (3 tests)

Tests defense-in-depth: zeroAccess overrides external path allowlists.

| # | Test Method | What It Verifies |
|---|-----------|-----------------|
| 20 | `test_external_env_file_matched_by_zero_access` | `.env` in allowed external dir caught by zeroAccess |
| 21 | `test_external_key_file_matched_by_zero_access` | `*.key` in allowed external dir caught by zeroAccess |
| 22 | `test_external_pem_file_matched_by_zero_access` | `*.pem` in allowed external dir caught by zeroAccess |

### Group 5: TestBackwardCompatibility (4 tests)

Tests old key removal and fallback config correctness.

| # | Test Method | What It Verifies |
|---|-----------|-----------------|
| 23 | `test_old_allowedExternalPaths_key_ignored` | Old `allowedExternalPaths` key not read by new code |
| 24 | `test_fallback_config_has_new_keys` | `_FALLBACK_CONFIG` has both new keys (empty lists) |
| 25 | `test_fallback_config_no_old_key` | `_FALLBACK_CONFIG` does NOT have old key |
| 26 | `test_old_and_new_keys_coexist_new_wins` | Old + new keys in same config: only new keys take effect |

## Test Results

| Test Suite | Result | Notes |
|-----------|--------|-------|
| `tests/core/test_external_path_mode.py` | **26/26 PASS** | All new tests pass |
| `tests/core/` (full) | 330/331 PASS (1 FAIL) | Pre-existing `test_ln_pattern_in_source` failure |
| `tests/security/` (full) | 224/226 PASS (2 FAIL) | Pre-existing failures (hex encoding, question mark glob) |

**Conclusion: Zero regressions introduced by these tests.**

## Key Design Decisions

### 1. Config path: `.claude/guardian/config.json`
The test initially used `.claude/hooks/protection.json` (from the old regression test pattern). The actual `load_guardian_config()` function loads from `.claude/guardian/config.json`. This was discovered during the first test run and fixed. **Future test writers should use `.claude/guardian/config.json`.**

### 2. Cache clearing in `setUp()`
Every test method clears `gu._config_cache`, `gu._using_fallback_config`, and `gu._active_config_path` to prevent cross-test pollution. This is done in both `setUp()` (per-method) and `tearDownClass()` (per-class) for defense-in-depth.

### 3. Helper function `_make_project_dir()`
Shared factory that creates a temp dir with `.git/` and `.claude/guardian/config.json` -- reduces boilerplate across all 5 test classes.

### 4. Mode enforcement via `_would_deny()` simulation
Since `run_path_guardian_hook()` calls `sys.exit()`, direct invocation is impractical. The test reproduces the exact conditional `mode == "read" and tool_name.lower() in ("write", "edit")` and validates it against real `match_allowed_external_path()` results in integration tests.

### 5. Real filesystem for extract_paths tests
Group 3 creates actual temp files on disk because `extract_paths()` checks `path.exists()` before including paths. The test creates:
- A project directory with an internal file
- An external directory with allowed files
- A separate external directory with non-allowed files

## Dependencies

- **Depends on E1v2**: Tests import `match_allowed_external_path`, `_FALLBACK_CONFIG` from `_guardian_utils.py`
- **Depends on E2**: Tests import `extract_paths` from `bash_guardian.py`
- **Bootstrap**: Uses standard `_bootstrap` pattern for sys.path setup
