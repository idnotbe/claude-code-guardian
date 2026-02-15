# Team B: Code Feature Wirer - Fix Summary
## Date: 2026-02-14

---

### Overview

Four disconnected/unused features were evaluated. Three were wired into the runtime; one was deliberately skipped with a documented rationale.

**Key Safety Principle:** All changes preserve identical behavior for users with the default configuration. The default `guardian.default.json` has `hookBehavior.onError: "deny"`, `hookBehavior.onTimeout: "deny"`, and `bashPathScan.scanTiers: ["zeroAccess"]` -- these defaults mean the previous hardcoded behavior is maintained.

---

### Feature 1: validate_guardian_config() - Wired into config loading

**Status:** IMPLEMENTED

**Files Modified:**
- `hooks/scripts/_guardian_utils.py`

**Changes:**
- Added validation call in `load_guardian_config()` after successfully loading JSON from both Step 1 (user custom config) and Step 2 (plugin default config)
- If validation returns errors, each error is logged as a WARN-level message
- Config is still used regardless of validation outcome (backwards compatible -- never blocks on validation failure)
- Fallback config (Step 3) is NOT validated -- it is hardcoded and known-good

**Behavioral Impact for Default Users:** None. The default config passes validation with zero errors (verified by test).

**Code Location:** Lines 507-510 (Step 1) and Lines 549-553 (Step 2) in `_guardian_utils.py`

---

### Feature 2: hookBehavior.onTimeout and onError - Wired into runtime

**Status:** IMPLEMENTED

**Files Modified:**
- `hooks/scripts/_guardian_utils.py` -- Added `make_hook_behavior_response()` helper function
- `hooks/scripts/bash_guardian.py` -- Updated imports and exception handler
- `hooks/scripts/read_guardian.py` -- Updated imports and exception handler
- `hooks/scripts/edit_guardian.py` -- Updated imports and exception handler
- `hooks/scripts/write_guardian.py` -- Updated imports and exception handler

**Changes:**
1. Added `make_hook_behavior_response(action, reason)` to `_guardian_utils.py`:
   - Converts a hookBehavior action string ("deny", "ask", "allow") to the appropriate hook response
   - Returns `None` for "allow" (no output = allow in Claude Code hook protocol)
   - Falls back to `deny_response()` for unrecognized action values (fail-closed)

2. Updated each security hook's `__main__` exception handler to:
   - Call `get_hook_behavior()` to read `onError` from config
   - Use `make_hook_behavior_response()` to generate the appropriate response
   - If `get_hook_behavior()` itself fails, fall back to hardcoded deny (fail-closed)

3. **auto_commit.py was NOT modified** -- it remains fail-open as specified, since it must never block session termination.

**Behavioral Impact for Default Users:** None. The default config has `"onError": "deny"`, which produces identical behavior to the previous hardcoded deny.

**Safety Analysis:**
- The `get_hook_behavior()` call is inside a try/except that falls back to deny on any failure
- Even if config is corrupted, the worst case is hardcoded deny (same as before)
- The ImportError handler at the top of each script remains unchanged (always deny) -- this fires before config is available

---

### Feature 3: scanTiers - Implemented in bash_guardian.py Layer 1

**Status:** IMPLEMENTED

**Files Modified:**
- `hooks/scripts/bash_guardian.py`

**Changes:**
- Updated `scan_protected_paths()` to read `bashPathScan.scanTiers` from config
- Added tier-to-config-key mapping: `"zeroAccess"` -> `"zeroAccessPaths"`, `"readOnly"` -> `"readOnlyPaths"`, `"noDelete"` -> `"noDeletePaths"`
- Collects path patterns from all configured tiers into a single scan list
- Default value is `["zeroAccess"]` when `scanTiers` is not configured (preserves current behavior exactly)
- Unknown tier names are silently ignored (no crash on typos)
- All existing logic (word-boundary regex, exactMatchAction, patternMatchAction, directory pattern skipping) is preserved

**Behavioral Impact for Default Users:** None. The default config has `scanTiers: ["zeroAccess"]`, which produces identical behavior to the previous hardcoded `config.get("zeroAccessPaths", [])`.

**Test Results:**
- Default config: `.env` detected (PASS), `package-lock.json` NOT detected (PASS -- backwards compatible)
- Expanded config with `["zeroAccess", "readOnly"]`: Both `.env` and `package-lock.json` detected (PASS)
- `noDelete` tier: `Makefile` detected (PASS)
- Invalid tier name: silently ignored (PASS)

---

### Feature 4: with_timeout() - Evaluated and SKIPPED

**Status:** SKIPPED (documented as TODO)

**Files Modified:**
- `hooks/scripts/bash_guardian.py` -- Added TODO comment with rationale

**Decision Rationale (5 reasons to skip):**

1. **SIGALRM can corrupt git state:** On Unix, SIGALRM interrupts any system call. If the alarm fires while a git subprocess is mid-write (e.g., during `git add -u` or `git commit`), it could leave `.git/index.lock` orphaned or the index in an inconsistent state.

2. **Windows threading timeout is a false safety net:** The threading-based timeout on Windows cannot actually kill the running thread. The thread continues executing in the background while the hook has already returned. This creates a race condition where the hook script reports "timeout" while the real work continues silently.

3. **Subprocess calls already have individual timeouts:** Every git subprocess call in the codebase already has its own timeout (5s for git ls-files, 10s for git status, 30s for git add/commit). These are the real timeout mechanisms and are more targeted.

4. **Archive file operations could be partially completed:** If the blanket timeout fires during `archive_files()`, files may be partially copied, leaving the archive in a corrupt state. The archive system has its own internal safety limits (100MB/file, 500MB total, 50 files max) which are more appropriate constraints.

5. **Risk-reward tradeoff:** The potential for subtle, hard-to-debug breakage (corrupt git state, partial archives, race conditions) outweighs the benefit of a blanket timeout. The existing per-subprocess timeouts provide sufficient protection.

**If implemented in the future**, the TODO comment specifies: wrap `main()` with `with_timeout()` using `hookBehavior.timeoutSeconds`, and route the `HookTimeoutError` through `hookBehavior.onTimeout` (default: "deny").

---

### Files Changed Summary

| File | Changes |
|------|---------|
| `hooks/scripts/_guardian_utils.py` | Added `make_hook_behavior_response()`, wired `validate_guardian_config()` into `load_guardian_config()` |
| `hooks/scripts/bash_guardian.py` | Added hookBehavior imports, implemented scanTiers, updated error handler, added with_timeout TODO |
| `hooks/scripts/read_guardian.py` | Added hookBehavior imports, updated error handler |
| `hooks/scripts/edit_guardian.py` | Added hookBehavior imports, updated error handler |
| `hooks/scripts/write_guardian.py` | Added hookBehavior imports, updated error handler |
| `hooks/scripts/auto_commit.py` | **NOT modified** (intentional -- remains fail-open) |

### Verification

- All 6 Python files pass `py_compile` syntax check
- Manual smoke tests pass for:
  - `get_hook_behavior()` returns correct defaults
  - `make_hook_behavior_response()` handles deny/ask/allow/unknown correctly
  - `validate_guardian_config()` returns no errors for default config
  - `validate_guardian_config()` catches invalid hookBehavior values
  - `scan_protected_paths()` with default `scanTiers` matches only zeroAccessPaths
  - `scan_protected_paths()` with expanded `scanTiers` matches additional tiers
  - Invalid tier names are silently ignored
