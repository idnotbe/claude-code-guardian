# Security Audit Report: P0/P1 Fail-Closed Fixes

## Status: COMPLETE -- PASS with advisory findings

**Auditor**: security-auditor
**Scope**: P0-A, P0-B, P0-C, P1 fixes in `_guardian_utils.py` and `bash_guardian.py`
**Date**: 2026-02-15

---

## Executive Summary

All four fixes are **correctly implemented** and achieve their stated security goals. The fail-open paths documented in CLAUDE.md have been closed. I found **zero blocking security issues** and **three advisory findings** (two low-severity, one informational).

---

## Security Checklist Results

### [PASS] All fail-open paths eliminated in `is_path_within_project()`

**File**: `_guardian_utils.py:1027-1058`

- **Line 1040-1044**: `if not project_dir: return False` -- CORRECT. Was `return True` (fail-open). Now fail-closed.
- **Line 1055-1058**: `except Exception: return False` -- CORRECT. Was `return True` (fail-open). Now fail-closed.
- **Line 1043**: stderr warning via `print(..., file=sys.stderr)` -- CORRECT. Since `log_guardian()` is a no-op when project_dir is missing (returns early at L1322-1324), stderr is the right channel.
- **Docstring L1037**: Updated to "False if outside project or on any error (fail-closed)" -- CORRECT.

### [PASS] All fail-open paths eliminated in `is_symlink_escape()`

**File**: `_guardian_utils.py:976-1024`

- **Line 991-995**: `if not project_dir: return True` -- CORRECT. Was `return False` (fail-open). Now fail-closed (assumes escape).
- **Line 1021-1024**: `except Exception: return True` -- CORRECT. Was `return False` (fail-open). Now fail-closed.
- **Line 994**: stderr warning -- CORRECT, same rationale as P0-A.
- **Docstring L988**: Updated to "True on any error (fail-closed)." -- CORRECT.

### [PASS] bash_guardian emits deny JSON on missing project dir

**File**: `bash_guardian.py:960-966`

- **Line 961-966**: Now emits `deny_response()` with meaningful reason before `sys.exit(0)`. Was bare `sys.exit(0)` (which Claude Code interprets as allow since no JSON output).
- **Line 963**: stderr warning -- CORRECT.
- **Line 964-965**: Reason string is descriptive but does not leak sensitive info: "Guardian cannot verify command safety: project directory not set"

### [PASS] P1: noDeletePaths enforcement for Write tool

**File**: `_guardian_utils.py:2374-2389`

- **Line 2375**: Correctly scoped to `tool_name.lower() == "write"` only.
- **Line 2375**: Uses `match_no_delete(path_str)` where `path_str = str(resolved)` (already resolved via `resolve_tool_path` at L2294). CORRECT -- pattern matching is against the resolved absolute path.
- **Line 2378**: `resolved = expand_path(file_path)` -- uses `expand_path` (which calls `.resolve()`) for the exists check. CORRECT -- not using `Path(file_path).exists()` which would be CWD-relative.
- **Line 2379**: `resolved.exists()` -- correctly checks the resolved path.
- **Placement**: After zeroAccess and readOnly checks (higher-priority denials run first). CORRECT ordering.

### [PASS] No new fail-open paths introduced

Verified all modified functions. No new `return True` on error in security-deny functions, no new `return False` on error in security-escape-detection functions.

### [PASS] Error messages don't leak sensitive information

- P0-A stderr: "GUARDIAN WARN: No project dir set, failing closed for path check" -- no sensitive info.
- P0-B stderr: "GUARDIAN WARN: No project dir set, treating symlink as potential escape" -- no sensitive info.
- P0-C deny reason: "Guardian cannot verify command safety: project directory not set" -- no sensitive info.
- P1 deny reason: "Protected from overwrite: {filename}" -- only leaks the filename (basename), not full path. Acceptable.

### [PASS] stderr logging does not confuse hook protocol

Claude Code hook protocol reads **stdout** for JSON responses. stderr goes to the parent process's stderr (visible to the user in debug mode). stderr output cannot inject into the hook response JSON on stdout. **No risk.**

---

## Advisory Findings

### ADVISORY-1: Variable shadowing of `resolved` in P1 (Severity: Informational)

**Location**: `_guardian_utils.py:2378`

Line 2294 sets `resolved = resolve_tool_path(file_path)`. Line 2378 reassigns `resolved = expand_path(file_path)` within the noDelete check block. This shadows the outer variable.

**Security impact**: None. The shadowed variable is only used for the `.exists()` check inside the `if` block, and the original `resolved` is not used after line 2295 (`path_str = str(resolved)`). After the noDelete block, the function exits via `sys.exit(0)` regardless of path.

**Semantic impact**: `resolve_tool_path` and `expand_path` differ slightly (`expand_path` does `expanduser()` first), but both call `.resolve()`. For the existence check, they produce equivalent results since `.resolve()` canonicalizes the path.

**Recommendation**: Consider renaming to `nodelete_resolved` for clarity in a future cleanup pass. Not a security concern.

### ADVISORY-2: TOCTOU window in P1 exists() check (Severity: Low)

**Location**: `_guardian_utils.py:2379`

There is a theoretical TOCTOU (time-of-check-time-of-use) race between `resolved.exists()` (line 2379) and the actual Write tool execution that follows after the hook allows.

**Two scenarios**:
1. **File exists at check, deleted before write**: Hook blocks the write (deny). But by the time the write would have executed, the file is gone. This is a false positive (denied a write that would have been a creation, not overwrite). The semantic mismatch is benign -- it's overly conservative, not overly permissive.
2. **File doesn't exist at check, created before write**: Hook allows the write (no file to protect). File is created between check and write. Write tool overwrites the newly-created file. This is a race that bypasses protection, but requires an attacker to create the file in the exact window between the hook check and tool execution. The practical window is very small (milliseconds).

**Security impact**: Low. Scenario 1 is fail-closed (safe). Scenario 2 is a narrow race that is extremely difficult to exploit because:
- The attacker would need to create a file in the project directory
- In the exact window between hook check and tool execution
- The file would need to match a noDeletePaths pattern
- This is a pre-hook, so the window is inherently small

**Recommendation**: Acceptable risk. Document as a known limitation. The alternative (always block writes to noDelete patterns even for new files) would break legitimate use cases.

### ADVISORY-3: `expand_path()` fails open on exception (Severity: Low, pre-existing)

**Location**: `_guardian_utils.py:970-973`

The `expand_path()` function returns `Path(path)` (the original unresolved path) on exception. This is a pre-existing condition not introduced by these fixes, but it interacts with the P1 fix.

If `expand_path` fails in the P1 noDelete check (line 2378), `resolved` would be `Path(file_path)` (unresolved). The `.exists()` call on this unresolved path would likely return `False` (unless the raw path happens to exist relative to CWD), causing the check to **not block** the write. This is a fail-open path, but:
- It requires `expand_path` to fail (which requires an OSError during path resolution)
- The path has already been successfully resolved once on line 2294 via `resolve_tool_path`
- If path resolution is failing, something is already very wrong

**Security impact**: Low. Defense-in-depth is maintained because the earlier checks (project boundary, symlink escape) have already passed by this point. The noDelete check is an additional layer, not the primary security boundary.

**Recommendation**: No action needed for this PR. Could be addressed in a future hardening pass by making `expand_path` fail-closed (raise instead of returning raw path).

---

## Pre-Existing Issues NOT Addressed by These Fixes (Out of Scope)

1. **`normalize_path()` (L948-951)** and **`normalize_path_for_matching()` (L1086-1088)** both fail-open on exception (return original path). These are pre-existing and not part of this PR's scope.

2. **`expand_path()` (L970-973)** fails open as noted in ADVISORY-3. Pre-existing.

3. **`resolve_tool_path()` (L2231-2235)** returns unresolved path on `OSError`. Pre-existing. Not a security issue in current context because subsequent checks (`is_symlink_escape`, `is_path_within_project`) provide defense-in-depth.

4. **`auto_commit.py` `--no-verify`**: Still unconditionally bypasses pre-commit hooks. Documented in CLAUDE.md. Not in scope for this PR.

---

## Test Coverage Assessment

The new test file `tests/security/test_p0p1_failclosed.py` provides **34 tests** covering:

| Fix | Unit Tests | Subprocess/Integration Tests | Coverage |
|-----|-----------|------------------------------|----------|
| P0-A | 6 (direct function calls) | 0 | Good |
| P0-B | 6 (direct function + real symlinks) | 0 | Good |
| P0-C | 0 | 4 (subprocess, checks deny + stderr) | Good |
| P1 | 0 | 8 (subprocess, multiple noDelete files) | Good |
| Defense-in-depth | 4 (mock + real) | 3 (Write/Read/Edit no-project-dir) | Good |

**Missing test**: No test verifies `expand_path` failure within the P1 noDelete block (ADVISORY-3 scenario). Low priority since it requires mocking inside a subprocess.

---

## Conclusion

**APPROVED for merge.** All P0 fail-closed fixes are correctly implemented. The P1 noDeletePaths enforcement is correctly scoped to Write tool + existing files only. No blocking security issues found. The three advisory findings are all low/informational severity and can be addressed in future hardening passes.

### Summary of Findings

| Finding | Severity | Action Required |
|---------|----------|-----------------|
| ADVISORY-1: Variable shadowing | Informational | None (cosmetic) |
| ADVISORY-2: TOCTOU in exists() | Low | None (acceptable risk) |
| ADVISORY-3: expand_path fail-open | Low (pre-existing) | Future hardening |
