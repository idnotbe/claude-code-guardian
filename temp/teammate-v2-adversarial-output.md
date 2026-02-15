# V2 Adversarial Review Report
## Date: 2026-02-15
## Reviewer: v2-adversarial (claude-opus-4-6, independent adversarial review)

---

## Attack Vectors Analyzed

### AV-1: Exception Type Escape (RuntimeError from expanduser)

**Vector**: `Path.expanduser()` raises `RuntimeError` (not `OSError`) for unknown users (e.g., `~nonexistentuser12345/foo`). Can this bypass a catch that only handles `OSError`?

**Analysis**: Confirmed experimentally that `expand_path()` at L966 calls `expanduser()` which raises `RuntimeError` for unknown users. However, ALL callers that catch exceptions use `except Exception`, not `except OSError`:
- `is_path_within_project()` L1053: `except Exception` -> returns False (fail-closed)
- `match_path_pattern()` L1187: `except Exception` -> returns `default_on_error` (fail-closed)
- `is_self_guardian_path()` L2180, L2211: `except Exception` -> returns True (fail-closed)
- noDelete block L2393: `except Exception` -> `file_exists = True` (fail-closed)

The ONLY narrower catch is `run_path_guardian_hook()` L2304: `except (OSError, RuntimeError)`, but this catches from `resolve_tool_path()` which does NOT call `expanduser()` -- it uses `Path(file_path)` + `.resolve()` only. And L2304 was already broadened to `except (OSError, RuntimeError)` after V1 review.

**Result**: NOT EXPLOITABLE. All exception handlers use `except Exception` or `except (OSError, RuntimeError)` as appropriate.

### AV-2: RuntimeError from Symlink Loops in resolve_tool_path

**Vector**: `Path.resolve()` raises `RuntimeError` (not `OSError`) for symlink loops.

**Analysis**: Confirmed experimentally: `Path.resolve()` raises `RuntimeError: Symlink loop from '/path'` on Linux. The handler at L2304 was broadened to `except (OSError, RuntimeError)` after V1 review. Even without this fix, the thin wrapper scripts' top-level `except Exception` at `__main__` would catch it and emit deny (defense in depth).

**Result**: NOT EXPLOITABLE. L2304 explicitly catches `RuntimeError` since V1 fix.

### AV-3: TOCTOU Between exists() Check and Write

**Vector**: An attacker deletes a file between the `exists()` check (L2392) and the actual file write by Claude Code.

**Analysis**: If file exists at check time -> `file_exists = True` -> deny. Claude Code receives deny and does not write. If file is deleted BEFORE the check -> `file_exists = False` -> write allowed. The noDelete semantic is "don't overwrite existing protected files", not "prevent file creation" (tested by `test_new_nodelete_file_allowed`).

The reverse TOCTOU (file created between check and write) is not relevant because file_exists=False -> write allowed -> writing creates the file -> no security issue.

**Result**: NOT EXPLOITABLE. Inherent architecture limitation. Error path is correctly fail-closed.

### AV-4: default_on_error Parameter Weaponization

**Vector**: Can `default_on_error=True` on deny-list checks be weaponized for bypass?

**Analysis**: An attacker who wants to BYPASS protection needs checks to return False (not matched). The fail-closed behavior always returns True (matched = deny) on error, which is the opposite of what a bypass needs.

**Polarity verification**:
| Check type | default_on_error | On error returns | Effect | Correct? |
|-----------|-----------------|-----------------|--------|----------|
| Deny-list (zeroAccess, readOnly, noDelete) | True | True (matched) | DENY | YES |
| Allow-list (allowedExternalPath) | False (default) | False (not matched) | DENY | YES |

**Result**: NOT EXPLOITABLE. Polarity is correct. All error states produce deny.

### AV-5: Normalization Error Creating Contradictory State

**Vector**: Can an attacker craft a path where normalization fails for one check but succeeds for another?

**Analysis**: All checks after `resolve_tool_path` use `path_str = str(resolved)`. If `resolve_tool_path` succeeds, `path_str` is a valid resolved absolute path. Subsequent calls to `normalize_path_for_matching` inside `match_path_pattern` call `expand_path` which calls `.resolve()` again. For the second `.resolve()` to fail after the first succeeded, the filesystem state would need to change between calls (sub-millisecond TOCTOU).

Even in that case: deny-list checks return True (deny), allow-list checks return False (deny). No combination produces an attacker-favorable outcome.

Furthermore, the check ordering in `run_path_guardian_hook` prevents contradictory states:
1. symlink escape
2. project boundary + allow-list
3. self-guardian
4. zeroAccess
5. readOnly
6. noDelete

If step 2 fails (path outside project, no external allow), steps 4-6 are never reached. If step 2 passes, steps 4-6 apply their own error handling independently.

**Result**: NOT EXPLOITABLE. All error states converge on deny.

### AV-6: Path(file_path).name in Deny Responses -- Information Leakage

**Vector**: Can `Path(file_path).name` in deny messages leak information or raise an exception?

**Analysis**: Tested experimentally:
- `Path('').name` -> `''` (no crash)
- `Path('/').name` -> `''` (no crash)
- `Path('///').name` -> `''` (no crash)
- `Path('a' * 10000).name` -> long string (no crash)
- `Path('/a/b/../../../etc/passwd').name` -> `'passwd'` (no crash)

`Path.name` only reveals the filename, which the user already provided. No information leakage beyond what the caller already knows.

**Result**: NOT EXPLOITABLE. No exception risk, no information leakage.

### AV-7: Config Loading Failure Bypassing Deny Lists

**Vector**: Can an attacker cause `load_guardian_config()` to fail, resulting in empty pattern lists?

**Analysis**: `load_guardian_config()` has a 3-step fallback chain:
1. User config (`$CLAUDE_PROJECT_DIR/.claude/guardian/config.json`)
2. Plugin default (`$CLAUDE_PLUGIN_ROOT/assets/guardian.default.json`)
3. Hardcoded `_FALLBACK_CONFIG` (L369-417)

The hardcoded fallback always has non-empty `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths`. The function is documented as "Never raises exceptions - returns safe default on any error" (L487).

The config file is protected from modification by both `is_self_guardian_path` (SELF_GUARDIAN_PATHS includes `.claude/guardian/config.json`) AND `readOnlyPaths` in the default config.

**Result**: NOT EXPLOITABLE. Fallback chain ensures non-empty patterns. Config is self-protected.

### AV-8: CLAUDE_PROJECT_DIR Manipulation

**Vector**: Can an attacker manipulate `CLAUDE_PROJECT_DIR` to point to a different directory?

**Analysis**: `CLAUDE_PROJECT_DIR` is set by Claude Code itself for each subprocess invocation. Manipulation requires OS-level exploits (ptrace, /proc) outside the threat model. Even if set to non-existent path, `get_project_dir()` returns empty string -> bash guardian denies all, path guardians deny at "outside project" check.

**Result**: NOT EXPLOITABLE (outside threat model).

### AV-9: RecursionError via _match_recursive_glob

**Vector**: Can a pathological `**` pattern cause stack overflow in `_match_recursive_glob` (L1087)?

**Analysis**: A pattern like `**/**/**/**/**/**/**/**/**/**` with a deep path could hit Python's recursion limit (default 1000). This would raise `RecursionError`, caught by `match_path_pattern`'s `except Exception` at L1187, returning `default_on_error`. For deny checks, this returns True (deny) -- fail-closed. Patterns are defined in config which is self-protected.

**Result**: NOT EXPLOITABLE. RecursionError is caught and handled fail-closed.

### AV-10: Dead Code -- normalize_path() at L918-951

**Vector**: The dead `normalize_path()` function (distinct from `normalize_path_for_matching()`) still has fail-open behavior at L948-951.

**Analysis**: Confirmed via grep that `normalize_path()` has ZERO callers anywhere in the codebase. Cannot be exploited because it is never called. However, it could be accidentally used by a future contributor who confuses it with `normalize_path_for_matching()`.

**Result**: NOT EXPLOITABLE (dead code). Recommendation: delete to prevent future misuse.

---

## Bypass Attempts

### Attempt 1: RuntimeError Escape Through resolve_tool_path Handler

Tried to find exception types not caught by `except (OSError, RuntimeError)` at L2304 that could be triggered by `Path.resolve()`. Tested `RuntimeError` (symlink loops), `OSError` (long paths), `PermissionError` (OSError subclass). All caught. `ValueError` would require null bytes, which are checked earlier at L2296. **FAILED to bypass.**

### Attempt 2: False-Allow via Error in Allow-List Check

Tried to construct a scenario where `match_allowed_external_path` returns a truthy value on error. On error, `match_path_pattern` returns `default_on_error=False` -> `any()` returns False -> function returns None (not matched). Path hits "outside project" deny. **FAILED to bypass.**

### Attempt 3: Circumvent noDelete via Non-Existent File Race

The hook denies because `except Exception: file_exists = True`. For a bypass, the attacker needs `file_exists = False`, which requires `exists()` to succeed AND return False. The exception handler only fires when `exists()` raises, always producing `True`. **FAILED to bypass.**

### Attempt 4: Verify test_exists_error_blocks_write Actually Tests Exception Path

Ran the noDelete path both WITH and WITHOUT the Path.exists monkey-patch in a subprocess:
- **Without patch**: File does not exist -> `decision = None` (allow)
- **With patch**: exists() raises -> `decision = deny` (fail-closed)

**CONFIRMED**: The deny can ONLY occur because the exception handler sets `file_exists = True`. The test correctly isolates the TOCTOU exception path.

### Attempt 5: Very Long Path to Trigger ENAMETOOLONG

Path: `/project/` + `a` * 4096 + `/CLAUDE.md`. `Path.resolve()` raises `OSError` (ENAMETOOLONG). Caught by L2304 -> deny. **BLOCKED.**

---

## False Positive Analysis

### Transient Filesystem Errors (NFS, FUSE, etc.)

On transient FS errors:
- All deny-list checks return True -> operation denied
- `is_path_within_project` returns False -> operation denied
- `is_self_guardian_path` returns True -> operation denied

**Impact**: User cannot read/write/edit any file until the filesystem stabilizes. **This is correct fail-closed behavior** -- if the filesystem is unreliable, security checks cannot be trusted.

**Risk**: LOW. For local filesystems, virtually never occurs. For NFS, errors are transient and resolve quickly.

### Paths with ~unknownuser

A path containing `~unknownuser` will:
1. Pass `resolve_tool_path` (Path constructor doesn't expand ~)
2. Be denied at `is_symlink_escape` (expanduser raises RuntimeError, caught by except Exception -> returns True -> denied as symlink escape)

This is a false positive (it's not actually a symlink escape), but `~unknownuser` paths are not used in legitimate operations.

**Risk**: NONE. Not a normal tool usage pattern.

### Permissions Errors on Path.resolve()

If the user doesn't have execute permission on a parent directory, `Path.resolve()` raises `PermissionError`. All operations on that path are denied.

**Risk**: LOW. Correct behavior -- if we can't resolve the path, we can't verify security.

**Overall false positive risk**: LOW. Fail-closed is the correct posture for a security tool.

---

## Test Suite Results

| Suite | Tests | Passed | Failed |
|-------|-------|--------|--------|
| test_advisory_failclosed.py | 26 | 26 | 0 |
| test_p0p1_failclosed.py | 34 | 34 | 0 |
| test_p0p1_comprehensive.py | 180 | 180 | 0 |
| **TOTAL** | **240** | **240** | **0** |

### Test Quality Assessment

**test_exists_error_blocks_write (rewritten)**: VERIFIED CORRECT. Experimentally confirmed that the deny can only come from the exception handler setting `file_exists = True`. Without the patch, the outcome is allow (file doesn't exist). With the patch, the outcome is deny.

**All 8 test classes cover their stated advisory fixes correctly.** No tests pass for the wrong reason. No missing assertions that could mask failures.

---

## Verdict

### PASS -- No bypass vectors found.

All three advisory fixes are correctly implemented and resistant to adversarial bypass:

**ADVISORY-1 (Variable Shadowing)**: Clean rename to `nodelete_resolved`. No ambiguity. Structural test prevents regression.

**ADVISORY-2 (TOCTOU Fail-Closed)**: `except Exception: file_exists = True` correctly handles ALL exception types. The rewritten test definitively proves the exception handler works by creating a scenario where only the exception path can produce deny.

**ADVISORY-3 (Fail-Closed Normalization)**: Exception propagation chain is complete. All boundary handlers use `except Exception` (catching OSError, RuntimeError, PermissionError, and any future exception types). The `default_on_error` polarity is correct: True for deny-lists, False for allow-lists. Both directions produce deny on error.

**Fundamental security property**: Errors always result in deny, which is the opposite of what an attacker needs for a bypass. The only theoretical "attack" is DoS via induced FS errors, which requires a separate OS-level exploit outside the guardian's threat model.

### Recommendations (non-blocking, pre-existing issues)

1. **Delete dead `normalize_path()` at L918-951** to prevent future accidental use with its fail-open semantics.
2. **Harmonize log message at L2181** to use `truncate_path(path)` instead of raw `path` (cosmetic, log-only, no security impact).
3. **Consider adding `~unknownuser` path test** to document the RuntimeError->Exception catch behavior explicitly.
