# V2 Adversarial Red-Team Review: P0/P1 Fixes

## Status: COMPLETE -- PASS (1 elevated finding, 3 confirmations, 2 new vectors documented)

**Reviewer**: adversarial-tester
**Scope**: Red-team analysis of P0-A, P0-B, P0-C, P1 fixes
**Date**: 2026-02-15

---

## Executive Summary

The P0/P1 fixes are **correctly implemented and resistant to the primary attack vectors** they were designed to close. I found **no bypass of the fixed code paths**. However, I identified **1 finding that should be elevated from the V1 assessment** and **2 new attack vectors** that exist in surrounding code (pre-existing, not introduced by these fixes). None are blocking for this PR.

---

## 1. CLAUDE_PROJECT_DIR Manipulation Analysis

### 1.1 Can an attacker manipulate CLAUDE_PROJECT_DIR?

**Finding: LOW RISK (environmental, not code-level)**

`CLAUDE_PROJECT_DIR` is set by Claude Code's runtime, not by the guardian. It is read via `os.environ.get("CLAUDE_PROJECT_DIR", "")` at `_guardian_utils.py:442`. The guardian has no control over its source.

**Attack scenarios analyzed:**

| Scenario | Feasibility | Impact |
|----------|-------------|--------|
| Bash command sets env var (`export CLAUDE_PROJECT_DIR=...`) | **Not feasible** -- env changes in child processes do not propagate back to the parent. Guardian hooks run as separate subprocesses invoked by Claude Code. The hook's env is set by Claude Code, not inherited from previous Bash commands. | N/A |
| Attacker modifies `.claude/settings.json` to inject env override | **Blocked** -- `.claude/` is in `noDeletePaths` and `SELF_GUARDIAN_PATHS`. Write guardian blocks overwrite of `.claude/guardian/config.json`. However, `.claude/settings.json` is NOT in `SELF_GUARDIAN_PATHS` (it's a Claude Code file, not a guardian file). | See Finding RED-1 |
| CLAUDE_PROJECT_DIR points to attacker-controlled directory | **Theoretically possible** if Claude Code is launched from an attacker-controlled directory. But this requires the attacker to already have control of the project root. | Low (pre-compromise required) |
| Symlink attack on project directory itself | **Mitigated** -- `get_project_dir()` checks `os.path.isdir()` which follows symlinks, so it would accept a symlinked project dir. However, `Path.resolve()` in `is_path_within_project` and `is_symlink_escape` canonicalizes paths through symlinks, so the boundary check operates on real paths. | No bypass found |

### 1.2 get_project_dir() validation adequacy

`get_project_dir()` at line 432-457 validates:
- Environment variable is non-empty (line 443)
- Directory exists via `os.path.isdir()` (line 449)
- **Does NOT validate .git presence** (commented out at line 452-456)

The `.git` check is commented out with the note "Non-git projects should still work for guardian purposes." This means `CLAUDE_PROJECT_DIR` can point to any existing directory. However, since Claude Code sets this variable (not the user), this is acceptable.

**Verdict: No bypass via CLAUDE_PROJECT_DIR manipulation.**

---

## 2. Path Traversal Attack Analysis

### 2.1 Classic traversal: `../../../etc/passwd`

**BLOCKED.** The fix at `_guardian_utils.py:2294` calls `resolve_tool_path(file_path)` which calls `Path.resolve()`, canonicalizing `..` components. The resulting `path_str` passed to `is_path_within_project()` is fully resolved. `Path(project_dir).resolve()` and `resolved.relative_to(project_resolved)` at lines 1048-1054 compare canonical paths.

**Tested manually**: `resolve_tool_path("../../../../etc/passwd")` resolves to `/etc/passwd` which fails `is_path_within_project`.

### 2.2 URL-encoded traversal: `..%2f..%2f`

**NOT APPLICABLE.** Claude Code's hook protocol delivers file paths as JSON string values, not URL-encoded. The path `..%2f..%2f` would be treated as a literal filename containing `%2f` characters, not as path separators. `Path("..%2f..%2fetc/passwd").resolve()` resolves to `<cwd>/..%2f..%2fetc/passwd` -- no traversal.

### 2.3 Null byte injection

**BLOCKED.** `run_path_guardian_hook` explicitly checks for `\x00` at line 2288. This runs BEFORE any path resolution.

### 2.4 Double encoding

**NOT APPLICABLE.** Same rationale as 2.2 -- the hook receives raw strings from JSON, not URL-encoded data. There is no decoding step that could be doubled.

### 2.5 Path separator confusion (backslash on Linux)

**NOT APPLICABLE.** On Linux, `\` is a valid filename character, not a separator. `Path("/project/foo\\..\\..\\etc/passwd").resolve()` resolves to `/project/foo\\..\\..\etc/passwd` (literal), not a traversal.

**Verdict: No path traversal bypass found.**

---

## 3. Unicode Normalization Attack Analysis

### 3.1 NFC vs NFD decomposition

**Finding: NO PRACTICAL BYPASS, but worth documenting**

On Linux (ext4), filenames are byte sequences. `Path.resolve()` does not normalize Unicode. Two different byte representations of the "same" character (e.g., U+00E9 vs U+0065 U+0301) would be treated as different paths by the filesystem and by Python.

This means:
- If a pattern in `noDeletePaths` uses NFC form and the filename uses NFD form (or vice versa), `fnmatch` would not match.
- However, `noDeletePaths` patterns are ASCII-only (`.gitignore`, `CLAUDE.md`, etc.), so Unicode normalization does not affect them.
- `zeroAccessPaths` patterns are also ASCII-only.

On macOS (HFS+), the filesystem itself normalizes to NFD, and `Path.resolve()` returns the NFD form. The code does `sys.platform != "linux"` lowercasing but does NOT do Unicode normalization. This could theoretically allow a bypass on macOS if a `zeroAccessPaths` pattern used non-ASCII characters. Currently all patterns are ASCII, so this is not exploitable.

**Verdict: No practical bypass. Theoretical future risk on macOS with non-ASCII patterns.**

---

## 4. Symlink Race Condition (TOCTOU) Analysis

### 4.1 Symlink race in is_symlink_escape

**Finding: MINIMAL RISK (inherent to filesystem TOCTOU)**

The check flow is:
1. `is_symlink_escape(file_path)` at line 2301: checks if path is a symlink, resolves it
2. `is_path_within_project(path_str)` at line 2310: checks resolved path is within project
3. Claude Code performs the actual operation

Between step 1-2 and step 3, an attacker could:
- Create a symlink AFTER the check (not caught)
- Replace a regular file with a symlink AFTER the check

However, the `path_str` used in step 2 is the **already-resolved** path from `resolve_tool_path` (line 2294). The actual file operation by Claude Code uses the original `file_path`, which could resolve differently at operation time.

**Practical exploitability**: Very low. The attacker would need:
- Write access to the project directory
- Precise timing (milliseconds between hook check and tool execution)
- Knowledge of when Claude Code is about to read/write a specific file

This is a well-known limitation of all pre-hook security models. The alternative (in-kernel mandatory access control) is out of scope.

### 4.2 TOCTOU in P1 exists() check

V1 ADVISORY-2 analyzed this. I **agree with the V1 assessment**: Scenario 1 (file deleted between check and write) is fail-closed (safe). Scenario 2 (file created between check and write) is a narrow race but requires the attacker to be actively writing files in the project directory in the exact window.

**Verdict: Acceptable risk. Pre-hook TOCTOU is inherent to the architecture.**

---

## 5. Combined Attack Scenario Analysis

### 5.1 P0-A + P0-B + P0-C all triggering simultaneously

This happens when `CLAUDE_PROJECT_DIR` is unset/invalid. The combined effect:

| Component | Behavior | Result |
|-----------|----------|--------|
| P0-A: `is_path_within_project` | Returns `False` (fail-closed) | Path treated as outside project |
| P0-B: `is_symlink_escape` | Returns `True` (fail-closed) | Path treated as symlink escape |
| P0-C: `bash_guardian.main()` | Emits deny JSON (fail-closed) | Bash commands blocked |
| `run_path_guardian_hook()` | `is_symlink_escape` returns True first (line 2301) | Tool operations blocked |

**Result: TOTAL LOCKDOWN.** All operations are denied. This is the correct behavior -- when the guardian cannot verify safety, it blocks everything.

**Usability concern**: A legitimate user whose `CLAUDE_PROJECT_DIR` is accidentally unset would be completely blocked. This is documented and intentional (fail-closed > fail-open).

### 5.2 Config loading fails AND project dir is missing

- `load_guardian_config()` returns `_FALLBACK_CONFIG` (line 579) -- this provides baseline protections.
- Missing project dir causes immediate deny in `bash_guardian.main()` and fail-closed behavior in path hooks.
- Since `log_guardian()` is a no-op without project dir, the only visible output is stderr warnings.

**Result: SAFE.** Config failure + project dir failure = deny everything. The fallback config ensures that even if config loading partially works, critical patterns are still protected.

### 5.3 expand_path() returns wrong result

If `expand_path()` returns `Path(path)` (the raw path) due to an exception:

1. In `is_path_within_project` (line 1047): The raw path is compared against `project_resolved`. Since `Path(path)` is likely not absolute or not resolved, `relative_to()` would raise `ValueError`, which is caught at line 1053 returning `False`. **SAFE (fail-closed).**

2. Wait -- actually, the exception from `expand_path` would be caught by the outer `except Exception` at line 1055, returning `False`. **SAFE (fail-closed).**

3. In P1 noDelete check (line 2378): `expand_path(file_path)` failing returns `Path(file_path)`. The `.exists()` call on this raw path:
   - If file_path is absolute: would check the actual file (correct behavior)
   - If file_path is relative: would check relative to CWD (potentially wrong, but CWD is typically the project dir anyway)

   The path has already been resolved once at line 2294 via `resolve_tool_path`, and `path_str` (used for `match_no_delete`) is the resolved version. So `match_no_delete(path_str)` uses the correct resolved path. Only the `.exists()` check might be on a wrong path. If `.exists()` returns False on the raw path when it should return True, the check doesn't block -- this is a **fail-open** path, but only for the noDelete check which is a supplementary protection, not the primary security boundary.

**Result: MOSTLY SAFE.** Primary security checks (symlink, project boundary) are fail-closed. The P1 noDelete check has a narrow fail-open path that requires `expand_path` to fail, which is unlikely given that `resolve_tool_path` already succeeded.

---

## 6. V1 Advisory Re-Assessment

### ADVISORY-1 (Variable shadowing): **Agree -- Informational**

The `resolved` variable shadowing at line 2378 is cosmetic. No security impact.

### ADVISORY-2 (TOCTOU in exists()): **Agree -- Low severity**

Already analyzed in Section 4.2. Acceptable risk.

### ADVISORY-3 (expand_path fail-open): **ELEVATE to MEDIUM for future hardening**

V1 assessed this as "Low (pre-existing)." I partially disagree on the severity rating.

**Why I'm elevating**: The `expand_path()` function is used in THREE security-relevant contexts:

1. `is_path_within_project` at line 1047 -- Protected by outer `except Exception` returning `False`. **Safe.**
2. `normalize_path_for_matching` at line 1076 -- Used in `match_path_pattern`, which is used by `match_zero_access`, `match_read_only`, `match_no_delete`, and `match_allowed_external_path`. If `expand_path` returns the raw path, pattern matching could fail to match patterns that would have matched on the resolved path. **This is a fail-open for zeroAccessPaths.**
3. P1 noDelete exists() check at line 2378 -- As analyzed above, narrow fail-open.

**The critical issue is #2**: If `expand_path` fails inside `normalize_path_for_matching` (line 1076), the path passed to `fnmatch` might not match a `zeroAccessPaths` pattern that it should match. For example, if the path is `~/project/../.env` and expand_path fails, the raw string `~/project/../.env` might not match the pattern `.env` because the `..` isn't resolved.

However, this requires:
- `expand_path` to throw an exception (rare -- requires OS-level errors)
- The raw path to not match the pattern through other matching paths (filename-only match at line 1158-1160 would still catch `.env`)

**Revised assessment: MEDIUM severity for future hardening, but not blocking for this PR.** The defense-in-depth via filename-only matching and multiple matching strategies in `match_path_pattern` significantly reduces the practical risk.

---

## 7. New Attack Vectors Identified (Pre-Existing, Not Introduced by Fixes)

### RED-1: is_self_guardian_path returns False when project_dir is missing

**Location**: `_guardian_utils.py:2183-2184`

```python
def is_self_guardian_path(path: str) -> bool:
    ...
    project_dir = get_project_dir()
    if not project_dir:
        return False  # <-- FAIL-OPEN
```

When `CLAUDE_PROJECT_DIR` is missing, `is_self_guardian_path` returns `False`, meaning guardian system files are NOT protected. However, with the P0 fixes in place, this doesn't matter because:
- `is_symlink_escape` returns `True` (line 2301 denies)
- `is_path_within_project` returns `False` (line 2310 denies)

The symlink and project boundary checks trigger BEFORE the self-guardian check (line 2338), so the fail-open in `is_self_guardian_path` is never reached in the missing-project-dir scenario.

**Impact: NONE in practice** due to the P0 fixes. The earlier fail-closed checks prevent reaching this code path. Documenting for completeness.

### RED-2: normalize_path() and normalize_path_for_matching() fail-open on exception

**Location**: `_guardian_utils.py:948-951` and `_guardian_utils.py:1086-1088`

Both functions return the **original unresolved path** on exception. This is the same issue described in V1 ADVISORY-3 for `expand_path`. These three functions form a family of fail-open normalization helpers.

**Impact**: If normalization fails, pattern matching operates on raw paths. As analyzed in Section 6 (ADVISORY-3 re-assessment), the practical risk is reduced by defense-in-depth matching strategies. However, a systematic hardening pass should address all three functions together.

### RED-3: resolve_tool_path() returns unresolved path on OSError

**Location**: `_guardian_utils.py:2233-2235`

```python
except OSError as e:
    log_guardian("WARN", f"Could not resolve path {file_path}: {e}")
    return path  # <-- Returns unresolved Path
```

If `Path.resolve()` fails (rare -- requires dangling symlinks or permission errors), the unresolved path is used for all subsequent checks. Since `is_symlink_escape` resolves the path independently (line 1007), and `is_path_within_project` resolves via `expand_path` (line 1047), there is defense-in-depth. However, the `path_str = str(resolved)` at line 2295 would use the unresolved path, which is then passed to `match_zero_access`, `match_read_only`, and `match_no_delete`.

**Impact**: Pattern matching on unresolved paths could miss protections. Low risk because the project boundary and symlink checks are independent and fail-closed.

---

## 8. Test Coverage Gaps Identified

### GAP-1: No test for P0-A exception path with CLAUDE_PROJECT_DIR set

V1 logic reviewer identified this (3 tests hit the early-return "no project dir" path instead of the exception handler). The tests at lines 145, 480, and 490 all pass, but for the wrong reason.

**Assessment**: This was identified but not fixed. The exception handler IS correct (verified by code review), but lacks true test coverage. **Recommend fixing before merge** -- the fix is a 3-line change per test (add `CLAUDE_PROJECT_DIR` to env).

**Update**: Looking at the test file again, I see that tests at lines 480-497 (`test_expand_path_exception_caught_by_is_path_within_project` and `test_oserror_in_expand_path_caught`) DO set `CLAUDE_PROJECT_DIR` via `patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir})`. Only the original test at line 145 (`test_exception_during_resolution_returns_false`) was identified as hitting the wrong path, and it has been fixed to include `CLAUDE_PROJECT_DIR`.

**Revised assessment**: Tests at lines 480 and 490 correctly set `CLAUDE_PROJECT_DIR`. Test at line 145 has been fixed. **GAP-1 is resolved.**

### GAP-2: No test for Unicode/non-ASCII file paths

No test verifies behavior with Unicode filenames (e.g., `rsum.txt`, ``, `file.txt`). While current patterns are all ASCII, adding a basic Unicode path test would improve confidence.

**Priority**: Low (not blocking).

### GAP-3: No test for resolve_tool_path OSError fallback

When `Path.resolve()` raises `OSError` in `resolve_tool_path`, the function returns the unresolved path. No test covers this scenario and its downstream effects on security checks.

**Priority**: Medium (documents RED-3 behavior).

---

## 9. Summary of Findings

### Blocking Issues: NONE

### Elevated from V1:

| Finding | V1 Severity | V2 Severity | Rationale |
|---------|-------------|-------------|-----------|
| ADVISORY-3: expand_path fail-open | Low | **Medium** (future) | Affects zeroAccessPaths matching via normalize_path_for_matching chain |

### New Findings:

| Finding | Severity | Blocking? | Action |
|---------|----------|-----------|--------|
| RED-1: is_self_guardian_path fail-open | None (mitigated by P0) | No | Document only |
| RED-2: normalize_path family fail-open | Low (pre-existing) | No | Future hardening pass |
| RED-3: resolve_tool_path OSError fallback | Low (pre-existing) | No | Future hardening pass |
| GAP-2: No Unicode path tests | Low | No | Nice-to-have |
| GAP-3: No resolve_tool_path OSError test | Medium | No | Recommend adding |

### Bypass Attempts Summary:

| Vector | Result |
|--------|--------|
| CLAUDE_PROJECT_DIR manipulation | **No bypass** -- env set by Claude Code runtime |
| Path traversal (../) | **No bypass** -- Path.resolve() canonicalizes |
| URL encoding (%2f) | **Not applicable** -- JSON protocol, no decoding |
| Null byte injection | **Blocked** at line 2288 |
| Double encoding | **Not applicable** -- no encoding layer |
| Unicode normalization | **No practical bypass** (all patterns are ASCII) |
| Symlink race (TOCTOU) | **Inherent to architecture** -- acceptable risk |
| Combined failure scenarios | **All fail-closed** -- total lockdown on error |
| expand_path exception exploitation | **Defense-in-depth protects** -- multiple independent checks |

---

## 10. Final Verdict

**APPROVED for merge.** The P0/P1 fixes correctly close the documented fail-open paths. No bypass vectors found against the fixed code. Pre-existing issues (normalize_path family, resolve_tool_path fallback) should be tracked for a future hardening pass but are not blocking.

The fixes are minimal, correct, and do not introduce new attack surface.
