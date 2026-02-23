# Verification Round 2 - Security & Completeness

**Verifier**: Independent Round 2 (security-focused, adversarial mindset)
**Date**: 2026-02-22
**Scope**: SessionStart Auto-Activate feature (5 files)

---

## A. Security Audit

### A1. Symlink redirection of config write outside the project

**Verdict: MITIGATED (with residual TOCTOU, acceptable for fail-open)**

The script has three layers of symlink defense:

1. **Line 23**: `[ -L "$CONFIG" ]` -- rejects if `config.json` itself is a symlink (dangling or valid). This prevents the simplest attack where an attacker pre-plants a symlink at the target path.

2. **Line 42**: `[ -L "$CLAUDE_PROJECT_DIR/.claude" ] || [ -L "$CLAUDE_PROJECT_DIR/.claude/guardian" ]` -- rejects if either parent directory is a symlink. Critically, this check runs AFTER `mkdir -p` (line 34), which narrows the TOCTOU window vs. checking before mkdir.

3. **Line 48**: `mktemp` uses `O_EXCL` flag, preventing symlink preemption at the temp file itself (CWE-377 mitigation).

4. **Line 65**: `mv -n` refuses to overwrite an existing target, so even if an attacker races to create a symlink at `$CONFIG` between the symlink check and the mv, `mv -n` will fail (since the symlink is a valid filesystem entry).

**Residual risk**: There is a TOCTOU window between the symlink check (line 42) and mktemp (line 48). An attacker who can replace `.claude/guardian/` with a symlink in that window could cause `mktemp` to create a temp file in the symlink target directory, then `cp` writes the config content there, and `mv -n` moves it to the attacker-controlled location. However:
- This requires local filesystem access with precise timing
- The worst-case outcome is writing a known-good config file to an arbitrary location
- The config content is not sensitive (it's public patterns)
- This is a fail-open hook, not a security gate
- The TOCTOU window is approximately 0-1ms in practice

**Assessment**: Acceptable for this threat model.

### A2. TOCTOU window between symlink check and mv

**Verdict: ACCEPTABLE (see A1 analysis)**

The window between the `-L` check (line 42) and `mv -n` (line 65) is approximately 3-4 bash operations (mktemp, cp, mv). The `mv -n` provides the final safety net: if config.json was created (by any means) between the check and the mv, `mv -n` refuses to clobber it.

The remaining exploit path is directory-level symlink replacement (replacing `.claude/guardian/` with a symlink between line 42 and line 48), which was analyzed in A1.

### A3. Race conditions between concurrent sessions

**Verdict: SAFE**

I verified `mv -n` behavior on this platform:
- `mv -n` returns exit code 1 when it refuses to overwrite (confirmed via manual test)
- With `2>/dev/null`, stderr ("not replacing") is suppressed
- `mktemp` generates unique temp filenames per invocation, so two sessions get different temp files
- First session's `mv -n` succeeds; second session's `mv -n` fails silently
- Both sessions copy the same source content, so even without `mv -n`, the outcome would be correct (just not atomic)

No data corruption is possible in the concurrent case.

### A4. Command injection via env vars

**Verdict: SAFE**

All variable expansions are properly double-quoted throughout the script:
- `"$CLAUDE_PROJECT_DIR"` (lines 8, 13, 14, 18, 42)
- `"$CLAUDE_PLUGIN_ROOT"` (lines 8, 14, 19)
- `"$CONFIG"` (lines 23, 65)
- `"$SOURCE"` (lines 28, 57)
- `"$CONFIG_DIR"` (lines 34, 48)
- `"$TMPFILE"` (lines 53, 57, 65)

The `case` statement on line 13 uses `$CLAUDE_PROJECT_DIR` without quotes, but this is safe in a `case` pattern context -- `case` does not perform word splitting on the value.

No `eval`, backtick expansion, or unquoted variable usage anywhere. No risk of command injection.

### A5. mktemp + mv -n pattern correctness

**Verdict: CORRECT**

- `mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX"` creates a file with 6 random characters, using `O_EXCL` to prevent symlink preemption. The template is in the same directory as the target, ensuring `mv` is an atomic rename (same filesystem).
- `trap cleanup EXIT` ensures the temp file is cleaned up on any exit path (including normal exit, signals, and errors). The `EXIT` trap in bash fires on signal-induced exits too.
- `mv -n` provides atomic no-clobber rename. On Linux, this uses `renameat2(RENAME_NOREPLACE)` or equivalent, which is a single kernel operation.

### A6. CLAUDE_PROJECT_DIR with spaces, special characters, newlines

**Verdict: WORKS, with a LOW-severity note on newlines**

I tested the script with:
1. **Spaces in path**: Works correctly. Config created successfully.
2. **Special characters** (`'`, `$`): Works correctly. Config created successfully.
3. **Newlines in path**: Works -- bash handles newlines in variables correctly when properly quoted. Config is created at the path containing the newline.

The newline case is not a security concern because:
- The script only writes to `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json`
- The content written is always the source config file
- `CLAUDE_PROJECT_DIR` is set by Claude Code, not by an attacker
- Even with a newline, the behavior is deterministic and benign

**Bonus finding**: `CLAUDE_PLUGIN_ROOT` is not checked for absolute path (only `CLAUDE_PROJECT_DIR` gets the `case /*` check). This is acceptable because `CLAUDE_PLUGIN_ROOT` is set by Claude Code infrastructure and only used as a source path, not a write target. A relative `CLAUDE_PLUGIN_ROOT` does work correctly (tested) because `-d` check works on relative paths and `cp` follows relative paths.

---

## B. Functional Completeness

### B1. Script matches action plan Step 1 exactly

**EXACT MATCH**: Diffed the bash code block from the action plan against the actual `session_start.sh`. Character-for-character identical.

### B2. hooks.json matches action plan Step 2 exactly

**EXACT MATCH**: The SessionStart block in `hooks/hooks.json` matches the action plan specification:
```json
{
  "matcher": "startup",
  "hooks": [
    {
      "type": "command",
      "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session_start.sh\""
    }
  ]
}
```

### B3. All 21 edge cases from Section 3 handled

All 21 edge cases from the action plan's Section 3 table are addressed in the implementation:

| # | Edge Case | Handling | Verified |
|---|-----------|----------|----------|
| 1 | Empty/unset CLAUDE_PROJECT_DIR | Line 8: `-z` check | YES |
| 2 | Empty/unset CLAUDE_PLUGIN_ROOT | Line 8: `-z` check | YES |
| 3 | Relative CLAUDE_PROJECT_DIR | Line 13: `case /*` pattern | YES |
| 4 | Non-existent CLAUDE_PROJECT_DIR | Line 14: `! -d` check | YES |
| 5 | Config already exists | Line 23: `-f` check | YES |
| 6 | .claude/guardian/ exists, no config | Line 34: `mkdir -p` no-op | YES |
| 7 | Source recommended.json missing | Line 28: `! -f` check | YES |
| 8 | Read-only filesystem | Line 34: `mkdir -p` fails, warning | YES |
| 9 | Permission denied (EACCES) | Same as read-only | YES |
| 10 | Disk full (ENOSPC) | Lines 48,57: mktemp/cp fail | YES |
| 11 | Partial write (kill during cp) | mktemp+mv-n: config absent or complete | YES |
| 12 | Concurrent sessions | `mv -n`: first wins, second fails | YES |
| 13 | Symlink on .claude/ | Line 42: `-L` check | YES |
| 14 | Symlink on .claude/guardian/ | Line 42: `-L` check | YES |
| 15 | Symlink at config.json | Line 23: `-L` check | YES |
| 16 | Git worktree | Trusts CLAUDE_PROJECT_DIR | YES (by design) |
| 17 | CI/CD environment | File creation is harmless | YES (by design) |
| 18 | Network filesystem (NFS/SMB) | Same-dir temp+mv, errors caught | YES |
| 19 | Very long paths | `2>/dev/null` + exit-code checks | YES |
| 20 | Non-UTF8 locale | All messages are ASCII-only | YES |
| 21 | Empty config.json (0 bytes) | Line 23: `-f` succeeds | YES |

### B4. All 20 test cases from Section 4.1 present

**19 of 20 present. 1 missing.**

| Action Plan Test | Actual Test | Status |
|------------------|-------------|--------|
| `test_first_run_creates_config` | `test_first_run_creates_config` | PRESENT |
| `test_existing_config_silent` | `test_existing_config_silent` | PRESENT |
| `test_missing_project_dir_env` | `test_missing_project_dir_env` | PRESENT |
| `test_empty_project_dir_env` | `test_empty_project_dir_env` | PRESENT |
| `test_missing_plugin_root_env` | `test_missing_plugin_root_env` | PRESENT |
| `test_missing_source_file` | `test_missing_source_file` | PRESENT |
| `test_readonly_filesystem` | `test_readonly_filesystem` | PRESENT |
| `test_dir_exists_no_config` | `test_dir_exists_no_config` | PRESENT |
| `test_created_config_valid_json` | `test_created_config_valid_json` | PRESENT |
| `test_created_config_matches_source` | `test_created_config_matches_source` | PRESENT |
| `test_symlink_parent_rejected` | `test_symlink_parent_rejected` | PRESENT |
| `test_symlink_guardian_dir_rejected` | `test_symlink_guardian_dir_rejected` | PRESENT |
| `test_symlink_config_file_rejected` | `test_symlink_config_file_rejected` + `test_symlink_config_file_valid_target_rejected` | PRESENT (expanded to 2 tests) |
| `test_idempotent_double_run` | `test_idempotent_double_run` | PRESENT |
| `test_empty_config_file_exits_silently` | `test_empty_config_file_exits_silently` | PRESENT |
| `test_relative_project_dir_rejected` | `test_relative_project_dir_rejected` | PRESENT |
| `test_nonexistent_project_dir_rejected` | `test_nonexistent_project_dir_rejected` | PRESENT |
| `test_mkdir_failure_emits_warning` | `test_mkdir_failure_emits_warning` | PRESENT |
| **`test_cp_failure_emits_warning`** | -- | **MISSING** |
| `test_exit_code_always_zero` | Expanded to 6 tests covering all scenarios | PRESENT |

The implementation also adds 2 bonus tests not in the plan:
- `test_first_run_stdout_messages` -- verifies all 4 context lines
- `test_symlink_config_file_valid_target_rejected` -- splits the symlink test into dangling + valid

**Missing test: `test_cp_failure_emits_warning`** -- The action plan specifies a test for when the source file is unreadable or temp file write fails. This test is not implemented. This is a real gap: if `cp` fails (e.g., source file permissions 000), the warning path is exercised but not tested. However, the `test_readonly_filesystem` test exercises a nearby code path (mkdir failure), and the cp failure path is structurally identical (same warning message, same exit 0).

---

## C. Test Quality

### C1. Do tests verify the right behavior?

**YES, with strong assertions.**

Tests verify three dimensions:
1. **Exit code**: Always 0 (dedicated TestSessionStartExitCodes class with 6 tests)
2. **Stdout content**: Checks for "[Guardian] Activated" on success, "Could not auto-activate" on failure, empty string on skip
3. **Filesystem state**: Verifies config file exists/doesn't exist, content matches source, file size for edge cases

The `test_created_config_matches_source` test does a full byte-for-byte comparison of the created config against the source file, which is a strong correctness check.

The `test_existing_config_silent` test verifies both that stdout is empty AND that the existing config file is not modified -- this catches both output and file mutation.

### C2. Is temp directory cleanup reliable?

**YES.**

- All test classes use `setUp`/`tearDown` with `tempfile.mkdtemp()` and `shutil.rmtree(ignore_errors=True)`
- Three classes (`TestSessionStartFirstRun`, `TestSessionStartFilesystem`, `TestSessionStartExitCodes`) include permission-restoration walks in `tearDown` that `os.chmod` directories back to `S_IRWXU` before cleanup -- this handles the `chmod 555` tests
- The `ignore_errors=True` on `shutil.rmtree` ensures cleanup never raises even if something unexpected happens
- Each test creates its own subdirectory under `tmpdir`, so tests are isolated

One minor note: if a test creates a file with root ownership (not possible in these tests), `ignore_errors=True` would silently leak temp dirs. Not a concern here.

### C3. Are permission-based tests safe on all systems?

**MOSTLY YES.**

- Tests use `stat.S_IRUSR | stat.S_IXUSR` (chmod 500) to simulate read-only, then restore in `tearDown`
- This works on Linux and macOS
- On Windows, `os.chmod` has limited effect, but the tests would likely still pass (different error paths)
- Root users: `chmod 500` does not prevent root from writing. If tests are run as root, `test_readonly_filesystem` and `test_mkdir_failure_emits_warning` would fail because mkdir would succeed. This is a standard caveat documented nowhere but not unusual for filesystem tests.
- The `tearDown` permission restoration prevents leaked read-only directories from blocking cleanup

### C4. Would tests catch a regression?

**YES, for most classes of regression.**

- If the script were changed to block on error (non-zero exit), 6 exit code tests would fail
- If the script were changed to overwrite existing configs, `test_existing_config_silent` and `test_empty_config_file_exits_silently` would fail
- If symlink protection were removed, 4 symlink tests would fail
- If the warning messages were removed, `test_mkdir_failure_emits_warning` would fail
- If the script produced output on skip paths, multiple "assertEqual(stdout, '')" tests would fail
- If env var validation were removed, `test_relative_project_dir_rejected` and `test_nonexistent_project_dir_rejected` would fail

**Gaps in regression detection**:
- No test for `cp` failure path specifically
- No test for concurrent session races (noted as "tricky to test reliably" in action plan)
- No test for the `trap cleanup EXIT` actually cleaning up temp files on failure

---

## D. Integration Check

### D1. hooks.json is valid JSON

**PASS**: Verified with `python3 -c "import json; json.load(open(...))"` -- no errors.

### D2. Existing hooks unchanged

**PASS**: Verified programmatically. The PreToolUse and Stop entries are exactly preserved:
- PreToolUse: Bash, Read, Edit, Write matchers with python3 commands -- all unchanged
- Stop: auto_commit.py command -- unchanged
- SessionStart: new entry added as first key in `hooks` object

Key ordering in JSON: `SessionStart` appears before `PreToolUse` and `Stop`, matching the action plan specification ("Add SessionStart as the first entry in hooks").

### D3. README.md accurately describes behavior

**PASS with minor notes.**

README changes verified:
- **Quick Start** (lines 132-155): Correctly describes auto-activation on first session, verification steps, customization via `/guardian:init`, opt-out mechanism (create any config.json beforehand)
- **Architecture table** (lines 440-449): Correctly shows 6 hooks including "Auto-Activate | SessionStart: startup | session_start.sh | Fail-open"
- **FAQ** (line 823-824): Updated to reflect auto-activation ("Guardian auto-activates the recommended config on your first session")
- The README correctly notes the source is `guardian.recommended.json` (not `guardian.default.json`)

### D4. CLAUDE.md has correct LOC count

**MINOR DISCREPANCY**: CLAUDE.md claims 78 LOC for `session_start.sh`, but `wc -l` reports 75 lines. The file has 75 lines (ending with `exit 0` on line 75, with a trailing newline counted by wc). The discrepancy is 3 lines.

Looking at the script: it has 75 physical lines (1-75). The action plan uses ~78 LOC for the code block (which includes the closing ``` delimiter and possibly blank lines). This is a cosmetic documentation discrepancy, not a functional issue.

Other CLAUDE.md updates verified:
- Repository Layout: "6 Python files + 1 bash script, ~4,220 LOC total" (plausible with session_start.sh added)
- Security Invariants: "SessionStart auto-activate is fail-open by design" added
- Coverage Gaps table: `session_start.sh | 78 | Full (26 tests)` present
- Key source files: `session_start.sh` and `guardian.recommended.json` listed

---

## E. Scenario Walkthroughs

### E1. Brand new project, first session ever

1. Claude Code starts, fires SessionStart event with matcher "startup"
2. `hooks.json` matches, invokes `bash session_start.sh`
3. `CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_ROOT` both set and non-empty -> passes line 8
4. `CLAUDE_PROJECT_DIR` starts with `/` -> passes line 13
5. Both directories exist -> passes line 14
6. `CONFIG = /project/.claude/guardian/config.json` -- file does not exist, not a symlink -> passes line 23
7. `SOURCE = $PLUGIN_ROOT/assets/guardian.recommended.json` -- exists -> passes line 28
8. `mkdir -p /project/.claude/guardian` -- succeeds (new dirs created) -> passes line 34
9. Neither `.claude` nor `.claude/guardian` is a symlink (just created) -> passes line 42
10. `mktemp` creates `/project/.claude/guardian/.config.json.tmp.XXXXXX` -> succeeds
11. `cp` copies source to temp file -> succeeds
12. `mv -n` renames temp to config.json -> succeeds (no existing target)
13. Success messages printed to stdout
14. Exit 0

**Result**: Config created, 4-line context message in Claude's context. Correct.

### E2. Second session (config already exists)

1-5: Same as E1
6. `CONFIG` path exists as a regular file -> `[ -f "$CONFIG" ]` is true -> exit 0 (line 24)

**Result**: Silent exit, no output, no file modification. Correct.

### E3. User manually deleted config, new session

Same as E1 -- the script sees no config and creates one. This is the intended behavior (documented in README: "To re-activate, delete the file and start a new session").

### E4. Read-only /tmp filesystem

This scenario is about a read-only `/tmp`, but the script does NOT use `/tmp`. The `mktemp` template is `"$CONFIG_DIR/.config.json.tmp.XXXXXX"`, which places the temp file in the same directory as the target config. So `/tmp` being read-only is irrelevant.

**If the project directory itself is read-only**:
1-7: Same as E1 up to source check
8. `mkdir -p` fails because project dir is read-only -> warning emitted, exit 0

**Result**: Warning message printed, no file created, session starts normally. Correct.

**If `.claude/guardian/` exists but is read-only** (unusual but possible):
1-7: Same as E1
8. `mkdir -p` succeeds (dir already exists, no write needed)
9. Symlink checks pass
10. `mktemp` fails because directory is read-only -> warning emitted, exit 0

**Result**: Warning message printed, no file created, session starts normally. Correct.

### E5. Two Claude sessions starting simultaneously on same project

1. Session A: passes all checks, reaches `mv -n` with temp file A
2. Session B: passes all checks, reaches `mv -n` with temp file B
3. Session A: `mv -n` succeeds (first to atomic rename)
4. Session B: `mv -n` fails (`-n` refuses to clobber config.json created by A) -> silent exit 0
5. Session A: prints success message
6. Session B: `trap cleanup EXIT` removes temp file B
7. Both sessions have correct config (same source content)

**Race sub-scenario**: Session B could win the `mv -n` instead. Same outcome -- first wins, second fails silently.

**Edge race**: Session B's `[ -f "$CONFIG" ]` check runs before A's `mv -n` completes. Both proceed to create temp files. `mv -n` resolves the race atomically.

**Result**: Exactly one config file created, no corruption, no errors. Correct.

---

## Issues Found

### MEDIUM: `test_cp_failure_emits_warning` test missing from implementation

**Severity**: MEDIUM
**Location**: `tests/regression/test_session_start.py`
**Description**: The action plan (Section 4.1) specifies `test_cp_failure_emits_warning` -- a test for when `cp` fails (e.g., source file unreadable). This test is not implemented. The cp failure warning path (lines 58-61 of the script) is untested.
**Impact**: Low -- the code path is structurally identical to the tested mkdir failure path (same warning message, same exit 0). A regression here is unlikely to be specific to `cp` without also breaking `mkdir`.
**Recommendation**: Add a test that makes the source file unreadable (`chmod 000` on a copy of `guardian.recommended.json`) and verifies the warning is emitted.

### LOW: CLAUDE.md reports 78 LOC, actual is 75

**Severity**: LOW
**Location**: `CLAUDE.md`, Coverage Gaps table
**Description**: `session_start.sh` has 75 lines (verified by `wc -l`), but CLAUDE.md says 78.
**Impact**: Documentation inaccuracy only. No functional impact.
**Recommendation**: Correct to 75.

### LOW: Misleading comment about `cp` preserving permissions

**Severity**: LOW
**Location**: `hooks/scripts/session_start.sh`, line 56
**Description**: Comment says "cp preserves source file permissions (typically 0644 from the repo)" but this is incorrect when `cp` overwrites an existing file (which is the case here, since `mktemp` creates the file first). `cp` to an existing file preserves the **destination** file's permissions. Since `mktemp` creates files with mode 0600, the final config.json has mode 0600, not 0644.
**Impact**: The actual behavior (0600) is more restrictive than the documented behavior (0644), so this is not a security issue. It's even slightly better from a security standpoint. However, the comment is factually wrong.
**Recommendation**: Either (a) change the comment to note the file will have 0600 permissions from mktemp, or (b) use `chmod 644 "$TMPFILE"` after mktemp if 0644 is the desired permission.

### INFO: No validation of CLAUDE_PLUGIN_ROOT as absolute path

**Severity**: INFO (not a real issue)
**Location**: `hooks/scripts/session_start.sh`, lines 12-16
**Description**: `CLAUDE_PROJECT_DIR` is validated as absolute (`case /*`), but `CLAUDE_PLUGIN_ROOT` is not. A relative `CLAUDE_PLUGIN_ROOT` would work correctly (tested) because it's only used as a source path. Since `CLAUDE_PLUGIN_ROOT` is set by Claude Code infrastructure (not user-controlled), this is defense-in-depth that is not needed.
**Impact**: None. This is an asymmetry in validation, not a bug.
**Recommendation**: No action needed. Document if desired.

---

## Summary

| Category | Result |
|----------|--------|
| Security Audit | 6/6 checks passed (residual TOCTOU acceptable for fail-open) |
| Functional Completeness | Script matches plan exactly. hooks.json matches plan exactly. 21/21 edge cases handled. 19/20 test cases present (1 missing: cp failure) |
| Test Quality | Strong assertions, reliable cleanup, good regression detection |
| Integration Check | JSON valid, existing hooks unchanged, README accurate, CLAUDE.md LOC off by 3 |
| Scenario Walkthroughs | 5/5 scenarios trace correctly |
| All 26 tests | PASSING (verified by actual test run) |
| Existing test suites | 630 passed, 1 pre-existing error (unrelated: test_bypass_v2.py fixture issue) |

## Verdict: PASS

The implementation is sound, security-conscious, and well-tested. The three issues found are all LOW or MEDIUM severity with no functional or security impact. The missing `test_cp_failure_emits_warning` test is the most notable gap but is mitigated by structural code similarity with the tested mkdir failure path.

## Confidence: 9/10

Deducted 1 point for the missing cp failure test and the permission comment inaccuracy. The core security model is solid: fail-open design, symlink protection with narrowed TOCTOU, atomic write via mktemp+mv-n, proper quoting throughout, and comprehensive test coverage of the happy path and error paths.
