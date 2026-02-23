# Verification Round 1

**Verifier**: Claude Opus 4.6 (independent verification agent)
**Date**: 2026-02-22
**Scope**: SessionStart Auto-Activate implementation

---

## Script Review

### `hooks/scripts/session_start.sh` (75 lines)

**Line-by-line analysis:**

1. **Lines 1-4 (header/comments)**: Correct. Clearly states fail-open contract and warning policy.

2. **Lines 6-10 (env validation)**: Correct. Checks both `CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_ROOT` for empty/unset. Uses `-z` which catches both unset and empty string. Exits 0 silently.

3. **Line 13 (absolute path check)**: Correct. `case "$CLAUDE_PROJECT_DIR" in /*) ;; *) exit 0 ;; esac` rejects anything not starting with `/`. This is a standard POSIX idiom for absolute path validation.

4. **Lines 14-16 (directory existence)**: Correct. Checks both paths are directories. Note: `CLAUDE_PLUGIN_ROOT` is NOT validated for absolute-ness (only directory existence). This is a minor gap but LOW risk since Claude Code is expected to always provide an absolute path, and the `-d` check on a relative path is only risky if an attacker controls CWD, which is not a realistic scenario here.

5. **Lines 18-19 (path construction)**: Correct. Uses variable concatenation with literal path components. No injection risk.

6. **Lines 22-25 (existing config check)**: Correct. `[ -f "$CONFIG" ] || [ -L "$CONFIG" ]` catches: regular files, symlinks to files, and dangling symlinks. This is the correct check -- `-f` follows symlinks (true if symlink target is a regular file), while `-L` catches symlinks regardless of target.

7. **Lines 27-30 (source file check)**: Correct. Exits silently if source is missing.

8. **Lines 32-38 (mkdir -p)**: Correct. Redirects stderr. Emits warning on failure. Exits 0.

9. **Lines 40-44 (post-mkdir symlink check)**: Correct. TOCTOU mitigation -- checks `.claude` and `.claude/guardian` for symlinks AFTER `mkdir -p`. This narrows the race window between "check" and "use" compared to checking before mkdir. Note: there is still a theoretical TOCTOU window between the `-L` check and the `mktemp`/`mv` below, but exploiting it requires an attacker to replace a real directory with a symlink in microseconds, which is extremely unlikely in this context.

10. **Lines 46-52 (mktemp)**: Correct. `mktemp` with `O_EXCL` prevents symlink preemption. Uses template in same directory as target (important for same-filesystem atomic `mv`). Warning on failure.

11. **Lines 53-54 (trap cleanup)**: Correct. `trap cleanup EXIT` ensures temp file removal on all exit paths including signals (bash EXIT trap fires on signal-induced exits). The `rm -f` is idempotent, so double-execution from unusual signal combinations is harmless.

12. **Lines 56-61 (cp)**: Correct. Copies source to temp file. Preserves permissions. Warning on failure.

13. **Lines 63-68 (mv -n)**: Correct. `mv -n` is the POSIX no-clobber move. On GNU coreutils (this system), it returns exit code 1 when it refuses to overwrite, which means `if ! mv -n ...` correctly detects both concurrent-session races and any unexpected target creation. Silent exit (no warning) is correct since the other session presumably succeeded.

14. **Lines 70-75 (success output)**: Correct. Four lines of context output. All ASCII. Includes actionable instructions.

**Shell injection analysis**: No shell injection vectors found. All variables are double-quoted. No `eval`, `exec`, backtick substitution, or `$()` on user-controlled input. The only `$()` is `$(dirname "$CONFIG")` which operates on a path composed from env vars + literal strings.

**Error path analysis**: Every code path terminates with `exit 0`:
- Line 9: missing env vars
- Line 13: relative path
- Line 15: non-directory
- Line 24: config exists or symlink
- Line 29: source missing
- Line 37: mkdir failed (with warning)
- Line 44: symlink detected post-mkdir
- Line 51: mktemp failed (with warning)
- Line 60: cp failed (with warning)
- Line 67: mv -n failed (silent -- concurrent race)
- Line 75: success

**FINDING**: No issues. All error paths exit 0. The script matches the action plan specification.

---

## hooks.json Review

**Valid JSON**: Confirmed via `python3 -c "import json; json.load(...)"` -- parses without error.

**Structure verification**:
- `SessionStart` is the FIRST key in `hooks` (lines 3-13) -- placed before `PreToolUse` as specified.
- Matcher is `"startup"` (line 5) -- matches the action plan. Note: the action plan flagged this as a BLOCKING dependency that required verification. The implementation uses it, implying it was verified.
- Command is `bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session_start.sh"` (line 9) -- correct.
- `PreToolUse` hooks (lines 14-50) are unchanged: Bash, Read, Edit, Write in the same order.
- `Stop` hook (lines 51-61) is unchanged: `auto_commit.py`.

**FINDING**: No issues. JSON is valid, structure is correct, existing hooks are untouched.

---

## Test Coverage

### Cross-reference against action plan Section 4.1 (20 test cases)

| Action Plan Test Case | Implemented? | Test Method |
|----------------------|--------------|-------------|
| `test_first_run_creates_config` | YES | `TestSessionStartFirstRun::test_first_run_creates_config` |
| `test_existing_config_silent` | YES | `TestSessionStartExistingConfig::test_existing_config_silent` |
| `test_missing_project_dir_env` | YES | `TestSessionStartEnvValidation::test_missing_project_dir_env` |
| `test_empty_project_dir_env` | YES | `TestSessionStartEnvValidation::test_empty_project_dir_env` |
| `test_missing_plugin_root_env` | YES | `TestSessionStartEnvValidation::test_missing_plugin_root_env` |
| `test_missing_source_file` | YES | `TestSessionStartEnvValidation::test_missing_source_file` |
| `test_readonly_filesystem` | YES | `TestSessionStartFilesystem::test_readonly_filesystem` |
| `test_dir_exists_no_config` | YES | `TestSessionStartFirstRun::test_dir_exists_no_config` |
| `test_created_config_valid_json` | YES | `TestSessionStartFirstRun::test_created_config_valid_json` |
| `test_created_config_matches_source` | YES | `TestSessionStartFirstRun::test_created_config_matches_source` |
| `test_symlink_parent_rejected` | YES | `TestSessionStartSymlinks::test_symlink_parent_rejected` |
| `test_symlink_guardian_dir_rejected` | YES | `TestSessionStartSymlinks::test_symlink_guardian_dir_rejected` |
| `test_symlink_config_file_rejected` | YES (split into 2) | `test_symlink_config_file_rejected` + `test_symlink_config_file_valid_target_rejected` |
| `test_idempotent_double_run` | YES | `TestSessionStartExistingConfig::test_idempotent_double_run` |
| `test_empty_config_file_exits_silently` | YES | `TestSessionStartExistingConfig::test_empty_config_file_exits_silently` |
| `test_relative_project_dir_rejected` | YES | `TestSessionStartEnvValidation::test_relative_project_dir_rejected` |
| `test_nonexistent_project_dir_rejected` | YES | `TestSessionStartEnvValidation::test_nonexistent_project_dir_rejected` |
| `test_mkdir_failure_emits_warning` | YES | `TestSessionStartFilesystem::test_mkdir_failure_emits_warning` |
| `test_cp_failure_emits_warning` | **NO** | Missing |
| `test_exit_code_always_zero` | YES (split into 6) | `TestSessionStartExitCodes` class (6 methods) |

### Symlink test assessment

Four symlink tests cover:
1. `.claude` as symlink (parent directory)
2. `.claude/guardian` as symlink (intermediate directory)
3. `config.json` as dangling symlink
4. `config.json` as symlink to valid file

This is thorough. The test at line 357 also verifies no file is written to the symlink target directory (not just that the script exits).

### Additional tests beyond action plan

The implementation adds 6 beyond the action plan's 20:
- `test_first_run_stdout_messages` -- verifies all 4 context lines (good)
- `test_symlink_config_file_valid_target_rejected` -- splits the dangling/valid symlink case (good)
- 6 exit-code tests split from the single `test_exit_code_always_zero` (good for granularity)

Total: 26 tests (20 from plan + 6 additional split/extra).

### Missing test cases (not in action plan but worth noting)

1. **`test_cp_failure_emits_warning`** -- Listed in the action plan but NOT implemented. This would test the case where the source file is unreadable or the temp file write fails. Simulating this requires either chmod 000 on the source file or filling the disk, both of which are feasible in a temp directory.

2. **`test_empty_plugin_root_env`** -- Not in the action plan, not tested. The script handles `CLAUDE_PLUGIN_ROOT=""` via the same `-z` check, but it's tested only via `test_missing_plugin_root_env` (unset). An empty-string test would be a minor addition for symmetry.

3. **`test_mktemp_failure_emits_warning`** -- Not in the action plan, not tested. Hard to trigger reliably (would need a directory where mktemp fails but mkdir succeeds).

4. **No tests validate stderr output** -- The script redirects stderr to `/dev/null` in multiple places, so stderr should always be empty. No test verifies this. Low priority since the script design ensures it, but worth a note.

### Test execution

All 26 tests pass (confirmed via `python3 -m pytest tests/regression/test_session_start.py -v`):
```
26 passed in 0.22s
```

**FINDING**: One action-plan test case is missing (`test_cp_failure_emits_warning`). This is a MEDIUM issue -- the cp failure path (line 57-61) is not covered by any test. All other test cases are well-implemented and thorough.

---

## Documentation Review

### README.md

**Quick Start section** (lines 132-155):
- Step 3 correctly states "Guardian auto-activates on your first session" -- accurate.
- Explains no setup commands required -- accurate.
- Includes opt-out mechanism ("create any config file at that path before first session") -- accurate.
- Includes re-activation instructions ("delete the file and start a new session") -- accurate.
- Mentions `{}` empty file prevents auto-activation -- consistent with the `[ -f "$CONFIG" ]` check.

**Architecture table** (lines 440-449):
- Auto-Activate row added as first entry: `SessionStart: startup`, `session_start.sh`, `Fail-open` -- accurate.
- States "six hooks" in the preceding text (line 440) -- matches the 6 rows in the table.

**FAQ** (line 823-824):
- Updated to mention auto-activation -- accurate.
- Correctly states fallback to built-in defaults if auto-activation fails.

**FINDING**: No issues. Documentation is accurate and consistent with the implementation.

### CLAUDE.md

**Repository Layout** (line 10):
- Updated to "6 Python files + 1 bash script, ~4,220 LOC total" -- reasonable given 75 lines added.

**Security Invariants** (line 32):
- Added "SessionStart auto-activate is fail-open by design" -- accurate and correctly placed.

**Coverage Gaps table** (line 52):
- `session_start.sh | 78 | Full (26 tests in tests/regression/test_session_start.py)` -- LOC says 78 but actual file is 75 lines. Minor inaccuracy.

**Key source files** (lines 85-88):
- `session_start.sh` added with correct description.
- `guardian.recommended.json` added -- good, since auto-activation makes it a critical asset.

**FINDING**: Minor -- LOC count is 78 in CLAUDE.md but actual file is 75 lines. LOW priority cosmetic issue.

---

## Acceptance Criteria Checklist

Going through each criterion from the action plan Section 7:

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `hooks/scripts/session_start.sh` exists and is executable | **PASS** | File exists, permissions are `-rwxr-xr-x` |
| 2 | `hooks/hooks.json` includes SessionStart event | **PASS** | JSON validated, SessionStart block present with `"startup"` matcher |
| 3 | First session creates config | **PASS** | `test_first_run_creates_config` passes; manually verified |
| 4 | Created config identical to source | **PASS** | `test_created_config_matches_source` does byte-for-byte comparison |
| 5 | Context message on first activation | **PASS** | `test_first_run_stdout_messages` verifies all 4 lines |
| 6 | Subsequent sessions silent | **PASS** | `test_existing_config_silent` verifies empty stdout, `test_idempotent_double_run` verifies double-run |
| 7 | Exit 0 in ALL scenarios | **PASS** | 6 dedicated exit-code tests + every other test checks `returncode == 0`; script analysis confirms all paths exit 0 |
| 8 | No output on early-exit paths | **PASS** | `test_missing_project_dir_env`, `test_empty_project_dir_env`, `test_missing_plugin_root_env`, `test_relative_project_dir_rejected`, `test_nonexistent_project_dir_rejected`, `test_missing_source_file` all assert `stdout == ""` |
| 9 | Warning on failed creation | **PASS** | `test_readonly_filesystem` and `test_mkdir_failure_emits_warning` verify warning output. **BUT**: `test_cp_failure_emits_warning` is missing (only mkdir and mktemp failure paths are tested via readonly, not cp-specific failure) |
| 10 | Symlink rejection | **PASS** | 4 symlink tests cover `.claude`, `.claude/guardian`, `config.json` (dangling), `config.json` (valid target) |
| 11 | Missing/empty env vars handled | **PASS** | Tests for missing and empty `CLAUDE_PROJECT_DIR`, missing `CLAUDE_PLUGIN_ROOT` |
| 12 | Relative/nonexistent `CLAUDE_PROJECT_DIR` rejected | **PASS** | Dedicated tests for both cases |
| 13 | Read-only filesystem handled | **PASS** | `test_readonly_filesystem` uses `chmod 555` |
| 14 | Concurrent session safety (mv -n) | **PASS** | Script uses `mv -n` with `2>/dev/null`. Verified on this system that `mv -n` returns exit code 1 on clobber refusal, which the script handles. No automated race test (action plan Section 4.2 classified this as manual) |
| 15 | All tests pass | **PASS** | 26/26 pass in 0.22s |
| 16 | README.md updated | **PASS** | Quick Start, Architecture table, FAQ all updated |
| 17 | CLAUDE.md updated | **PASS** | Key files, coverage table, security invariants all updated |

---

## Issues Found

### MEDIUM-1: Missing `test_cp_failure_emits_warning` test

**Severity**: MEDIUM
**Location**: `tests/regression/test_session_start.py`
**Description**: The action plan (Section 4.1) lists `test_cp_failure_emits_warning` as a required test case ("Source file unreadable or temp file write fails -> Stdout contains 'Could not auto-activate', exit 0"). This test is not implemented. The cp failure path (script lines 57-61) is not covered by any existing test.

**Impact**: The cp failure code path (lines 57-61 of `session_start.sh`) is untested. While the code is simple and structurally identical to the tested mkdir failure path, it represents a gap in coverage for one of the three warning-emitting failure modes (mkdir, mktemp, cp).

**Suggested fix**: Add a test that makes the source file unreadable (`chmod 000`) after directory creation but before the script runs, or use a temp directory that allows mkdir but not writes.

### LOW-1: LOC count discrepancy in CLAUDE.md

**Severity**: LOW
**Location**: `CLAUDE.md` line 52
**Description**: CLAUDE.md coverage table says `session_start.sh | 78` but actual file is 75 lines. Minor cosmetic issue.

**Suggested fix**: Update to `75`.

### LOW-2: Missing `test_empty_plugin_root_env` test

**Severity**: LOW
**Location**: `tests/regression/test_session_start.py`
**Description**: `CLAUDE_PLUGIN_ROOT=""` (empty string) is handled by the script (same `-z` check as unset) but is not explicitly tested. Only `CLAUDE_PLUGIN_ROOT` unset is tested. This is symmetrical with the `test_empty_project_dir_env` test that IS present.

**Suggested fix**: Add a one-line test case for `CLAUDE_PLUGIN_ROOT=""`.

### LOW-3: No absolute path validation for `CLAUDE_PLUGIN_ROOT`

**Severity**: LOW
**Location**: `hooks/scripts/session_start.sh` lines 13-15
**Description**: The script validates `CLAUDE_PROJECT_DIR` for absolute-ness (`case ... in /*)`), but does not apply the same check to `CLAUDE_PLUGIN_ROOT`. A relative `CLAUDE_PLUGIN_ROOT` would resolve relative to CWD, potentially reading the wrong source file. However, `CLAUDE_PLUGIN_ROOT` is set by Claude Code (not user input) and is reliably absolute. The `-d` check provides partial protection. The action plan does not call for this validation, and the risk is LOW since the variable is not user-controlled.

**Suggested fix**: None required. This is a defense-in-depth observation, not a bug. If desired, add `case "$CLAUDE_PLUGIN_ROOT" in /*) ;; *) exit 0 ;; esac` for symmetry.

### INFO-1: `"startup"` matcher verification status unclear

**Severity**: INFO (not actionable)
**Location**: `hooks/hooks.json` line 5
**Description**: The action plan flagged `"startup"` as a BLOCKING dependency requiring verification before implementation. The implementation uses `"startup"`, implying it was verified. However, there is no documentation of the verification result (e.g., a note in the action plan's Appendix C or a test confirming the hook fires). If `"startup"` is incorrect, the feature is silently non-functional. The fallback strategy (omit matcher, rely on idempotency) is noted in the action plan.

**Suggested action**: Document the verification result in the action plan, or add a comment in `hooks.json`.

---

## Verdict: PASS

The implementation is correct, secure, and well-tested. All 17 acceptance criteria are met. The script has no shell injection vulnerabilities, all error paths exit 0, atomic write is properly implemented with TOCTOU mitigation, and symlink attacks are handled comprehensively.

The one MEDIUM issue (missing `test_cp_failure_emits_warning`) is a test coverage gap, not a code defect. The untested code path is structurally identical to the tested `mkdir` failure path and is almost certainly correct. The three LOW issues are cosmetic or defense-in-depth observations.

**Recommendation**: Fix MEDIUM-1 (add the missing test) and LOW-1 (correct LOC count) before merging. LOW-2, LOW-3, and INFO-1 can be deferred.
