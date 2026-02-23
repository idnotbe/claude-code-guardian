# Tests Directory Structure Analysis

**Analyst**: structure-analyst
**Date**: 2026-02-22
**Scope**: `/home/idnotbe/projects/claude-code-guardian/tests/`

---

## 1. Directory Structure Overview

```
tests/
  _bootstrap.py           # Shared sys.path setup (finds repo root, adds hooks/scripts/)
  conftest.py             # Pytest bridge (auto-imports _bootstrap for pytest collection)

  # -- Root-level "foundation" tests (custom runner, NOT unittest) --
  test_guardian.py         # Phase 5 integration tests (custom TestResults class)
  test_guardian_utils.py   # Unit tests for _guardian_utils.py (custom TestResults class)

  # -- Root-level DUPLICATES of organized files (pre-migration copies) --
  test_guardian_p0p1_comprehensive.py  # Duplicate of core/test_p0p1_comprehensive.py
  test_guardian_v2fixes.py             # Duplicate of core/test_v2fixes.py
  test_guardian_v2fixes_adversarial.py # Duplicate of security/test_v2fixes_adversarial.py
  test_heredoc_fixes.py               # Pytest-native (uses pytest classes), heredoc tests

  # -- Organized subdirectories --
  core/                   # Comprehensive P0/P1/V2 test suites (unittest)
  security/               # Adversarial bypass and red-team tests (unittest + script)
  regression/             # Bug-specific regression tests (script + unittest)
  review/                 # Code review edge cases (print-based scripts)
  usability/              # False positive and usability checks (print-based scripts)
  patterns/               # Standalone regex verification scripts (print-based)
  _archive/               # Superseded tests (excluded from test runs)
```

## 2. Subdirectory Detail

### `core/` (3 files, ~344 unittest methods)

| File | Methods | Focus |
|------|---------|-------|
| `test_p0p1_comprehensive.py` | 180 | All P0 ship-blocker fixes (ReDoS, exactMatchAction, fail-close verdict), P1 improvements (git rm, redirect truncation, glob bracket, metadata write, tilde, flag-path), regression (split_commands, glob_to_literals, scan_protected_paths, is_write/delete_command, block/ask patterns, extract_paths, redirection, verdict aggregation), performance, integration, negative tests |
| `test_v2fixes.py` | 125 | V2 fixes F1-F10: fail-closed safety net, ln write pattern, clobber redirection, Pattern9 ReDoS, archive symlink, process substitution, path traversal, git global flags, schema default, boundary characters. Plus regression and performance. |
| `test_external_path_mode.py` | 39 | Enhancement 1+2: split allowedExternalPaths into Read/Write, extract_paths external path inclusion, zeroAccess on external paths, backward compatibility, deprecation warning, bash enforcement of read-only external paths |

**Naming convention**: `test_<feature_area>.py`
**Test style**: `unittest.TestCase` subclasses with `if __name__ == "__main__": unittest.main()`
**pytest compatible**: Yes (via conftest.py/_bootstrap.py)

### `security/` (7 files, ~286 unittest methods + 2 script files)

| File | Methods | Style | Focus |
|------|---------|-------|-------|
| `test_p0p1_failclosed.py` | 34 | unittest | Fail-closed on errors/missing config, subprocess integration tests for edit/read/write_guardian.py thin wrappers |
| `test_v2_adversarial.py` | 63 | unittest | Adversarial bypass attempts against P0+P1 fixes |
| `test_v2_crossmodel.py` | 20 | unittest | Cross-model (Codex/Gemini) red-team bypass attempts |
| `test_v2fixes_adversarial.py` | 143 | unittest | Adversarial testing of V2 fixes F1-F10 + V1 hotfixes |
| `test_advisory_failclosed.py` | 26 | unittest | Advisory fixes (normalization fail-closed, TOCTOU, variable shadowing) |
| `test_bypass_v2.py` | 0 (script) | print-based | Bypass vectors across zeroAccess/readOnly/noDelete tiers + tokenizer edge cases |
| `test_bypass_v2_deep.py` | 0 (script) | print-based | End-to-end layer tracing (Layer 0-4) for bypass vectors |

**Naming convention**: `test_<threat_category>.py`
**Capacity**: HIGH - This is the go-to directory for any adversarial or bypass testing

### `regression/` (4 files, 28 unittest methods + 3 script files)

| File | Methods | Style | Focus |
|------|---------|-------|-------|
| `test_session_start.py` | 28 | unittest | SessionStart hook (session_start.sh) subprocess tests |
| `test_allowed_external.py` | 0 (script) | print-based | Regression tests for allowedExternalReadPaths/WritePaths |
| `test_errno36_e2e.py` | 0 (script) | print-based | End-to-end test for Errno 36 (ENAMETOOLONG) bash_guardian crash |
| `test_errno36_fix.py` | 0 (script) | print-based | Unit-level test for _is_path_candidate and Errno 36 fix |

**Naming convention**: `test_<bug_id>.py`
**Capacity**: MEDIUM - Good home for bug-specific regression tests

### `review/` (6 files, all print-based scripts)

| File | Focus |
|------|-------|
| `test_code_review.py` | glob_to_literals edge cases, _is_inside_quotes, split_commands |
| `test_code_review2.py` | glob_to_literals empty string bug, scan_protected_paths with edge literals |
| `test_v1code_deep.py` | Deep edge case analysis for V1-CODE review (F1 fail-closed, redirections, archive symlinks) |
| `test_v1code_f5_broken.py` | F5 (archive symlink) breakage investigation |
| `test_v1code_f5_f1.py` | F5 and F1 interaction analysis |
| `test_v1code_regex.py` | Regex pattern analysis for V1 code review |

**Test style**: All print-based scripts with manual verification (no assert or unittest)
**Capacity**: LOW - These are one-off code review artifacts; generally wouldn't add here

### `usability/` (8 files, all print-based scripts)

| File | Focus |
|------|-------|
| `test_codex_concerns.py` | is_write_command anchoring analysis (Codex review feedback) |
| `test_edge_cases.py` | F1 edge cases: --version/--help on write commands |
| `test_f1_deep.py` | F1 false positive rate on common developer commands |
| `test_f1_var_edge.py` | Variable resolution edge cases with F1 |
| `test_f4f7.py` | F4 ReDoS performance + F7 path traversal usability |
| `test_final_checklist.py` | Final checklist of mandatory commands from review |
| `test_preexisting.py` | Distinguish pre-existing vs V2-introduced false positives |
| `test_var_resolution.py` | Variable expansion interaction with F1 fail-closed |

**Test style**: All print-based scripts
**Capacity**: LOW for new files, but could accept converted unittest versions

### `patterns/` (8 files, all print-based scripts)

| File | Focus |
|------|-------|
| `verify_bypass.py` | Bypass pattern verification |
| `verify_env_boundary.py` | .env boundary character regex verification |
| `verify_git_rm_redos.py` | Git rm ReDoS verification |
| `verify_regex.py` | General regex pattern verification |
| `verify_sed_false_positive.py` | sed false positive analysis |
| `verify_sed_inplace.py` | sed -i detection verification |
| `verify_sudo_rm.py` | sudo rm pattern verification |
| `verify_write_patterns.py` | Write pattern regex verification |

**Naming convention**: `verify_<pattern_area>.py`
**Test style**: Pure regex/print scripts (no _bootstrap needed, no unittest)
**Capacity**: MEDIUM - Good for regex-specific verification

### `_archive/` (8 files, superseded)

Superseded test files kept for reference. Not collected by test runners.

Files: `test_guardian_bypass.py`, `test_p0_fixes.py`, `test_p1_5_detailed.py`, `test_p1_fixes.py`, `test_p1_layer1.py`, `test_scan_verify.py`, `test_security_verify.py`, `v1_sec_tests.py`

## 3. Root-Level Test Files in `tests/`

| File | Status | Relationship |
|------|--------|-------------|
| `test_guardian.py` | UNIQUE | Phase 5 integration tests (custom runner, not unittest). Tests config loading/validation, block/ask patterns, path guardian rules, git integration, timeout, dry-run, Windows compat, response helpers, circuit breaker. |
| `test_guardian_utils.py` | UNIQUE | Unit tests for _guardian_utils.py (custom runner). Tests config, block/ask patterns, path matching, dry-run, evaluate_rules, response helpers, logging, path normalization, error handling, symlinks, fallback guardian, command length limit, ReDoS, newline injection, interpreter deletion. |
| `test_guardian_p0p1_comprehensive.py` | **DUPLICATE** of `core/test_p0p1_comprehensive.py` | Pre-migration copy with hardcoded paths; organized version uses _bootstrap |
| `test_guardian_v2fixes.py` | **DUPLICATE** of `core/test_v2fixes.py` | Pre-migration copy; organized version uses _bootstrap |
| `test_guardian_v2fixes_adversarial.py` | **DUPLICATE** of `security/test_v2fixes_adversarial.py` | Pre-migration copy; organized version uses _bootstrap |
| `test_heredoc_fixes.py` | UNIQUE | Pytest-native (uses `class TestHeredocSplitting:` without unittest.TestCase). Tests heredoc-aware split_commands, quote-aware is_write_command, heredoc-aware scan_protected_paths. |

## 4. Coverage Map by Feature/Function

### `bash_guardian.py` functions:

| Function | Covered In |
|----------|-----------|
| `split_commands()` | core/test_p0p1 (17 tests), core/test_v2fixes, security/test_v2_adversarial, tests/test_heredoc_fixes |
| `is_write_command()` | core/test_p0p1 (15 tests), core/test_v2fixes (F2 ln), security/* (multiple), tests/test_heredoc_fixes |
| `is_delete_command()` | core/test_p0p1 (8 tests), core/test_v2fixes (F4, F8), security/* (multiple) |
| `extract_paths()` | core/test_p0p1 (10 tests), core/test_v2fixes (F1), core/test_external_path_mode, regression/test_errno36 |
| `extract_redirection_targets()` | core/test_p0p1 (3 tests), core/test_v2fixes (F3, F6) |
| `scan_protected_paths()` | core/test_p0p1 (9 tests), core/test_v2fixes (F10), security/test_bypass_v2, tests/test_heredoc_fixes |
| `glob_to_literals()` | core/test_p0p1 (14 tests), review/test_code_review |
| `_is_inside_quotes()` | core/test_p0p1 (4 tests), review/test_code_review |
| `_stronger_verdict()` | core/test_p0p1 (5 tests), core/test_v2fixes (F1) |
| `_is_within_project_or_would_be()` | core/test_v2fixes (F7), usability/test_f4f7 |
| `archive_files()` | core/test_v2fixes (F5) |

### `_guardian_utils.py` functions:

| Function | Covered In |
|----------|-----------|
| `load_guardian_config()` | tests/test_guardian.py, tests/test_guardian_utils.py, core/test_external_path_mode |
| `validate_guardian_config()` | tests/test_guardian.py, core/test_external_path_mode |
| `match_block_patterns()` | tests/test_guardian.py, tests/test_guardian_utils.py |
| `match_ask_patterns()` | tests/test_guardian.py, tests/test_guardian_utils.py |
| `match_zero_access()` | tests/test_guardian.py, tests/test_guardian_utils.py, core/test_external_path_mode, security/test_advisory |
| `match_read_only()` | tests/test_guardian.py, tests/test_guardian_utils.py, security/test_advisory |
| `match_no_delete()` | tests/test_guardian.py, tests/test_guardian_utils.py, security/test_advisory |
| `match_allowed_external_path()` | core/test_external_path_mode (12 tests), regression/test_allowed_external, security/test_advisory |
| `match_path_pattern()` | core/test_external_path_mode, security/test_advisory |
| `run_path_guardian_hook()` | security/test_p0p1_failclosed (subprocess integration) |
| `expand_path()` | security/test_p0p1_failclosed, security/test_advisory |
| `normalize_path_for_matching()` | tests/test_guardian.py, tests/test_guardian_utils.py, security/test_advisory |
| `is_path_within_project()` | tests/test_guardian_utils.py |
| `is_symlink_escape()` | tests/test_guardian_utils.py |
| `deny_response/ask_response/allow_response()` | tests/test_guardian.py, tests/test_guardian_utils.py |
| `evaluate_rules()` | tests/test_guardian_utils.py |
| `with_timeout()` | tests/test_guardian.py |
| `circuit breaker functions` | tests/test_guardian.py |

### Scripts with NO tests:

| Script | Status |
|--------|--------|
| `auto_commit.py` | **NO tests at all** (173 LOC) |
| `edit_guardian.py` | Basic subprocess integration in security/test_p0p1_failclosed |
| `read_guardian.py` | Basic subprocess integration in security/test_p0p1_failclosed |
| `write_guardian.py` | Basic subprocess integration in security/test_p0p1_failclosed |

### `session_start.sh`:
- Full coverage: 28 tests in `regression/test_session_start.py`

## 5. Coverage Gaps Where Root Files Could Fill

Based on the root-level test files (`test_*.py` in project root, not in `tests/`), potential coverage additions:

1. **Heredoc handling**: `tests/test_heredoc_fixes.py` is UNIQUE and covers heredoc-aware split_commands, quote-aware is_write_command, heredoc-aware scan_protected_paths. This content has NO equivalent in any subdirectory.
   - **Best destination**: `core/` (it tests core bash_guardian functions)

2. **Foundation integration tests**: `tests/test_guardian.py` and `tests/test_guardian_utils.py` are UNIQUE custom-runner tests that cover _guardian_utils.py functions not tested elsewhere (circuit breaker, with_timeout, logging, symlink functions, fallback guardian, etc.).
   - **Best destination**: Keep at root level (they use a different test runner paradigm) or convert to unittest and move to `core/`

3. **Root duplicates**: `test_guardian_p0p1_comprehensive.py`, `test_guardian_v2fixes.py`, `test_guardian_v2fixes_adversarial.py` are all duplicates with hardcoded paths. **Safe to delete** -- the organized versions in `core/` and `security/` are the maintained copies.

## 6. Subdirectory Capacity for New Tests

| Directory | Capacity | Rationale |
|-----------|----------|-----------|
| `core/` | **HIGH** | Natural home for comprehensive feature tests. Currently 3 files with clean naming. Could absorb heredoc tests, auto_commit tests. |
| `security/` | **HIGH** | Natural home for adversarial/bypass tests. Well-established with 7 files. |
| `regression/` | **HIGH** | Good for bug-specific regression tests. Currently only 4 files. |
| `review/` | LOW | One-off code review artifacts. Not recommended for new work. |
| `usability/` | MEDIUM | Could accept new false-positive tests. Currently all print-based. |
| `patterns/` | MEDIUM | Could accept regex verification scripts. |

## 7. Key Observations

1. **Two test paradigms coexist**: unittest.TestCase (core/, security/) and print-based scripts (review/, usability/, patterns/). The print-based scripts are not collected by `pytest` unless they have `assert` statements.

2. **Three root-level files are confirmed duplicates** with only path/import differences from the organized versions.

3. **`tests/test_heredoc_fixes.py`** is the only pytest-native file (uses `class TestHeredocSplitting:` without inheriting unittest.TestCase). It requires `pytest` to run.

4. **`auto_commit.py` has zero test coverage** -- this is the most significant coverage gap.

5. **The `_archive/` convention is well-established** for superseded tests.

6. **Naming is consistent within directories** but inconsistent across: `test_<feature>.py` in core, `test_<threat>.py` in security, `test_<bug>.py` in regression, `verify_<pattern>.py` in patterns.
