# Team A: Code Bug Fixes Summary

All 6 confirmed bugs have been fixed in the following files:

- `hooks/scripts/_guardian_utils.py` (5 bugs)
- `assets/guardian.default.json` (1 bug)

---

## Fix 1: COMPAT-13 - Recovery guidance uses Windows `del` on all platforms

**File**: `hooks/scripts/_guardian_utils.py`
**Lines affected**: 314, 324, 334 (after edit)

**Problem**: All three `except` blocks in `is_circuit_open()` hardcoded `del "{circuit_file}"` in recovery messages, which is a Windows-only command. Unix/macOS users would see incorrect guidance.

**Fix**: Added `rm_cmd = "del" if sys.platform == "win32" else "rm"` before each log message, then used `{rm_cmd}` in the f-string. Each exception handler now suggests the correct deletion command for the user's platform.

---

## Fix 2: COMPAT-08 - Relative $schema in default config

**File**: `assets/guardian.default.json`
**Line affected**: 1 (the `$schema` key)

**Problem**: `"$schema": "./guardian.schema.json"` used a relative path. Since the default config lives in `assets/` within the plugin cache directory, but user configs go in `.claude/guardian/`, the relative path was always wrong when the config was copied or referenced from a different location. It provided no runtime value and misled users.

**Fix**: Removed the `$schema` key entirely from the JSON. The `$comment` key remains for documentation purposes.

---

## Fix 3: COMPAT-06 - normalize_path resolves against CWD

**File**: `hooks/scripts/_guardian_utils.py`
**Lines affected**: 927-931 (after edit)

**Problem**: `normalize_path()` called `os.path.abspath()` directly, which resolves relative paths against the current working directory (CWD). If the CWD differs from the project directory, relative paths would resolve incorrectly.

**Fix**: Added a check before `os.path.abspath()`: if the expanded path is not already absolute, resolve it against `get_project_dir()` first. If no project dir is available, falls back to the original CWD-based behavior. This is a minimal, safe fix since tool inputs typically arrive as absolute paths.

---

## Fix 4: COMPAT-07 - fnmatch case sensitivity on macOS

**File**: `hooks/scripts/_guardian_utils.py`
**Lines affected**: 936, 1065, 1132, 1151, 2161, 2168 (after edit)

**Problem**: Path lowercasing was only applied on Windows (`sys.platform == "win32"`), but macOS HFS+ (and APFS by default) is also case-insensitive. This meant path patterns could fail to match on macOS when casing differed.

**Fix**: Changed all 6 case-insensitive lowering conditions from `sys.platform == "win32"` to `sys.platform != "linux"`. This ensures both Windows and macOS paths are lowercased for matching. The following functions were updated:
- `normalize_path()` (line 936)
- `normalize_path_for_matching()` (line 1065)
- `match_path_pattern()` (lines 1132, 1151)
- Self-guardian path matching (lines 2161, 2168)

**Not changed**: `sys.platform == "win32"` at line 135 (timeout handler - threading vs SIGALRM), and lines 314/324/334 (recovery command selection) which correctly use `win32` for the `del` vs `rm` distinction.

---

## Fix 5: evaluate_rules() fails-open

**File**: `hooks/scripts/_guardian_utils.py`
**Line affected**: 1445 (after edit)

**Problem**: The `except` block in `evaluate_rules()` returned `"allow", ""` (fail-open), contradicting the project's fail-closed security philosophy. An exception during rule evaluation would silently allow potentially dangerous commands.

**Fix**: Changed the return to `"deny", "Guardian internal error (fail-closed)"`. Now any unexpected error during rule evaluation results in a denial, consistent with the security-first design principle stated in the module docstring.

---

## Fix 6: MAX_COMMAND_LENGTH comment misleading

**File**: `hooks/scripts/_guardian_utils.py`
**Line affected**: 81 (after edit)

**Problem**: The docstring for `MAX_COMMAND_LENGTH` said "Commands exceeding this are still processed (fail-open) but logged." However, the actual implementation in `match_block_patterns()` (line ~846) returns `True` (blocked) for oversized commands, which is fail-closed behavior.

**Fix**: Changed the docstring from:
```
Commands exceeding this are still processed (fail-open) but logged.
```
to:
```
Commands exceeding this are denied (fail-closed) for security.
```

---

## Verification

- Python syntax check: PASSED (`py_compile` reports no errors)
- JSON validation: PASSED (guardian.default.json parses correctly)
- All `sys.platform == "win32"` for case lowering: converted to `sys.platform != "linux"` (6 locations)
- Only `sys.platform == "win32"` remaining: line 135 (timeout handler), lines 314/324/334 (rm_cmd selection) -- all correct
