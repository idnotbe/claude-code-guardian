# Verification Round 1: Accuracy Report

**Verifier**: Teammate G
**Date**: 2026-02-14
**Method**: Read all referenced source files and compared each claim against actual code/docs.

---

## Team A: Code Bug Fixes

### A1. COMPAT-13: Circuit breaker recovery messages use platform-aware del vs rm
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`:
- Line 314: `rm_cmd = "del" if sys.platform == "win32" else "rm"` (PermissionError handler)
- Line 324: `rm_cmd = "del" if sys.platform == "win32" else "rm"` (OSError handler)
- Line 334: `rm_cmd = "del" if sys.platform == "win32" else "rm"` (generic Exception handler)

All three `except` blocks in `is_circuit_open()` correctly select `del` on Windows and `rm` elsewhere.

---

### A2. COMPAT-08: `$schema` field removed from assets/guardian.default.json
**PASS**

Evidence: `git show HEAD:assets/guardian.default.json` output begins with `"$comment"` key. No `"$schema"` key is present in the file. Confirmed via `grep '\$schema'` in the assets directory -- only `guardian.schema.json` contains `$schema` references (which is correct; that file IS a schema).

---

### A3. COMPAT-06: normalize_path() uses get_project_dir() for non-absolute path resolution
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`, lines 927-932:
```python
        # Get absolute path - resolve relative paths against project dir, not CWD
        if not os.path.isabs(expanded):
            project_dir = get_project_dir()
            if project_dir:
                expanded = os.path.join(project_dir, expanded)
        absolute = os.path.abspath(expanded)
```
Non-absolute paths are joined with `get_project_dir()` before `abspath()` is called. Falls back to CWD-based behavior if no project dir is available. Matches the report.

---

### A4. COMPAT-07: Six locations changed from `sys.platform == "win32"` to `sys.platform != "linux"`
**PASS**

Evidence from grep of `sys.platform` in `_guardian_utils.py`:
- Line 135: `sys.platform == "win32"` -- SIGALRM check, correctly unchanged
- Line 314: `sys.platform == "win32"` -- rm_cmd selection, correctly unchanged
- Line 324: `sys.platform == "win32"` -- rm_cmd selection, correctly unchanged
- Line 334: `sys.platform == "win32"` -- rm_cmd selection, correctly unchanged
- Line 936: `sys.platform != "linux"` -- `normalize_path()` (CHANGED)
- Line 1065: `sys.platform != "linux"` -- `normalize_path_for_matching()` (CHANGED)
- Line 1132: `sys.platform != "linux"` -- `match_path_pattern()` pattern lowering (CHANGED)
- Line 1151: `sys.platform != "linux"` -- `match_path_pattern()` project dir lowering (CHANGED)
- Line 2161: `sys.platform != "linux"` -- `is_self_guardian_path()` project dir lowering (CHANGED)
- Line 2168: `sys.platform != "linux"` -- `is_self_guardian_path()` protected path lowering (CHANGED)

Six locations changed to `!= "linux"`, plus the SIGALRM check and three rm_cmd checks correctly remain as `== "win32"`. Report states 6 locations changed -- confirmed correct.

---

### A5. evaluate_rules() catch block returns "deny" not "allow"
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`, line 1445:
```python
        return "deny", "Guardian internal error (fail-closed)"
```
The except block on line 1442-1445 returns `"deny"` with a fail-closed message, not `"allow"`.

---

### A6. MAX_COMMAND_LENGTH docstring says "fail-closed" not "fail-open"
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`, lines 79-81:
```python
MAX_COMMAND_LENGTH = 100_000
"""Maximum command length in bytes before blocking.
Commands exceeding this are denied (fail-closed) for security."""
```
Docstring correctly says "denied (fail-closed)".

---

## Team B: Feature Wiring

### B1. validate_guardian_config() called in load_guardian_config() for both Step 1 and Step 2
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`:
- Step 1 (lines 507-511): After loading user config:
  ```python
  _validation_errors = validate_guardian_config(_config_cache)
  if _validation_errors:
      for _verr in _validation_errors:
          log_guardian("WARN", f"Config validation: {_verr}")
  ```
- Step 2 (lines 549-553): After loading plugin default config:
  ```python
  _validation_errors = validate_guardian_config(_config_cache)
  if _validation_errors:
      for _verr in _validation_errors:
          log_guardian("WARN", f"Config validation: {_verr}")
  ```

Both steps call `validate_guardian_config()` and log warnings. Config is still used regardless (backwards compatible). Step 3 (hardcoded fallback) is NOT validated -- as reported.

---

### B2. make_hook_behavior_response() function exists in _guardian_utils.py
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`, lines 629-649:
```python
def make_hook_behavior_response(action: str, reason: str) -> dict[str, Any] | None:
```
Function exists with correct signature. Handles "allow" (returns None), "ask" (returns `ask_response()`), and defaults to `deny_response()` for unrecognized values (fail-closed).

---

### B3. hookBehavior wired into bash_guardian.py, read_guardian.py, edit_guardian.py, write_guardian.py exception handlers
**PASS**

Evidence:
- **bash_guardian.py** (lines 38, 50, 1242-1268): Imports `get_hook_behavior` and `make_hook_behavior_response`. Exception handler at line 1248 calls `get_hook_behavior().get("onError", "deny")` then `make_hook_behavior_response()`. Falls back to hardcoded deny if that fails.

- **read_guardian.py** (lines 27, 29, 54-82): Imports `get_hook_behavior` and `make_hook_behavior_response`. Exception handler at line 62 calls `get_hook_behavior().get("onError", "deny")` then `make_hook_behavior_response()`. Falls back to hardcoded deny.

- **edit_guardian.py** (lines 31, 33, 58-86): Same pattern -- imports, exception handler with `get_hook_behavior()` and `make_hook_behavior_response()`, hardcoded deny fallback.

- **write_guardian.py** (lines 31, 33, 58-86): Same pattern -- imports, exception handler with `get_hook_behavior()` and `make_hook_behavior_response()`, hardcoded deny fallback.

All four security hooks follow the identical pattern.

---

### B4. scanTiers implemented in bash_guardian.py scan_protected_paths() with tier-to-config mapping
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py`, lines 333-348:
```python
    # Read scanTiers from config; default to ["zeroAccess"] (preserves current behavior)
    scan_tiers = scan_config.get("scanTiers", ["zeroAccess"])

    # Map tier names to config keys
    tier_to_config_key = {
        "zeroAccess": "zeroAccessPaths",
        "readOnly": "readOnlyPaths",
        "noDelete": "noDeletePaths",
    }

    # Collect all path patterns from configured tiers
    all_scan_paths: list[str] = []
    for tier in scan_tiers:
        config_key = tier_to_config_key.get(tier)
        if config_key:
            all_scan_paths.extend(config.get(config_key, []))
```
Default is `["zeroAccess"]`. Unknown tier names are silently skipped via `tier_to_config_key.get(tier)` returning None. All existing logic is preserved below this section.

---

### B5. with_timeout() deliberately NOT wired (has TODO comment explaining why)
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py`, lines 1235-1241:
```python
    # TODO: Consider wrapping main() with with_timeout() using hookBehavior.timeoutSeconds.
    # Currently SKIPPED because:
    # 1. SIGALRM on Unix can interrupt git subprocess calls mid-execution, risking git state corruption
    # 2. Threading timeout on Windows cannot kill the running thread (it continues in background)
    # 3. Individual subprocess calls already have their own timeouts (5-30s)
    # 4. A blanket timeout could race with archive file operations, causing partial archives
    # If implemented, the HookTimeoutError should follow hookBehavior.onTimeout (default: "deny").
```
`main()` is called directly on line 1243 without `with_timeout()`. The TODO provides 4 reasons plus future implementation guidance.

---

### B6. auto_commit.py NOT modified (remains fail-open)
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/auto_commit.py`:
- Line 40-42: ImportError handler is fail-open: `print(f"Warning: ...", file=sys.stderr)` then `sys.exit(0)`
- Line 162-173: `__main__` exception handler logs error, opens circuit breaker, then `sys.exit(0)` -- fail-open
- No imports of `get_hook_behavior` or `make_hook_behavior_response` present
- No hookBehavior logic wired into auto_commit.py

Confirmed: auto_commit.py was intentionally not modified and remains fail-open.

---

## Team C: Documentation

### C1. README: Shell profile persistence alias example present
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/README.md`, lines 52-56:
```
> **Persistence**: The `--plugin-dir` flag applies to a single session. To load Guardian automatically, add to your shell profile:
> ```bash
> # ~/.bashrc or ~/.zshrc
> alias claude='claude --plugin-dir /path/to/claude-code-guardian'
> ```
```
Concrete alias example with `~/.bashrc` and `~/.zshrc` reference.

---

### C2. README: Marketplace commands marked as unverified
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/README.md`, lines 62-74:
```
> **Unverified**: Marketplace integration is currently experimental and these commands have not been tested against a live Claude Code plugin CLI. Manual installation (above) is the reliable path.

The following are two alternative syntaxes...

# Alternative A: marketplace add
...
# Alternative B: direct install
...
See [UX-07 in KNOWN-ISSUES.md](KNOWN-ISSUES.md) for details.
```
Marked as "Unverified", labeled as alternatives, cross-references KNOWN-ISSUES.

---

### C3. README: Troubleshooting section with log location, common issues table
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/README.md`, lines 181-195:
- Log file location: `.claude/guardian/guardian.log` (line 183)
- Hook check method: "try to read a `.env` file" (line 185)
- Common issues table with 5 rows: Hooks not firing, python3 not found, Config not loading, Auto-commits stopped, Unexpected blocks (lines 189-195)

All items present with Problem/Cause/Solution columns.

---

### C4. README: Python 3.10+ mentioned in Installation
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/README.md`, line 45:
```
> **Requires Python 3.10+** and Git. Verify with `python3 --version` before installing.
```
Prominent callout before the clone command.

---

### C5. README: Dry-run tip in Setup section
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/README.md`, line 88:
```
> **Tip**: To test your configuration without blocking operations, use dry-run mode: `CLAUDE_HOOK_DRY_RUN=1`. See [Disabling Guardian](#disabling-guardian) for details.
```
Cross-references Disabling Guardian section. Additionally, lines 199-203 show the enhanced Disabling Guardian section with concrete command example:
```bash
CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/claude-code-guardian
```

---

### C6. CHANGELOG: [Unreleased] section has Added, Changed, and Fixed subsections with all entries
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/CHANGELOG.md`, lines 8-33:
- `### Added` (line 10): 4 entries covering validate_guardian_config, hookBehavior runtime, make_hook_behavior_response, scanTiers
- `### Changed` (line 16): 13 entries covering COMPAT-06/07/08/13 code fixes and all README/KNOWN-ISSUES doc changes
- `### Fixed` (line 31): 2 entries covering evaluate_rules fail-closed and MAX_COMMAND_LENGTH docstring

All three subsections present with comprehensive entries.

---

### C7. KNOWN-ISSUES: COMPAT-06, COMPAT-07, COMPAT-08, COMPAT-13 marked as FIXED with strikethrough
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/KNOWN-ISSUES.md`:
- Line 70: `#### ~~COMPAT-06: normalize_path resolves against CWD~~ FIXED`
- Line 75: `#### ~~COMPAT-07: fnmatch case sensitivity on macOS~~ FIXED`
- Line 109: `#### ~~COMPAT-08: Relative $schema in default config~~ FIXED`
- Line 123: `#### ~~COMPAT-13: Recovery guidance uses Windows del on all platforms~~ FIXED`

All four use strikethrough formatting with "FIXED" suffix. Each includes a `**Fix**:` line describing the actual resolution.

---

### C8. KNOWN-ISSUES: Fixed Issues table includes the 4 newly fixed items
**PASS**

Evidence in `/home/idnotbe/projects/claude-code-guardian/KNOWN-ISSUES.md`, lines 151-154:
```
| COMPAT-06 | MEDIUM | normalize_path resolves against CWD | Unreleased |
| COMPAT-07 | MEDIUM | fnmatch case sensitivity on macOS | Unreleased |
| COMPAT-08 | LOW | Relative $schema in default config | Unreleased |
| COMPAT-13 | LOW | Recovery guidance uses del on all platforms | Unreleased |
```
All four items appear in the Fixed Issues table with "Unreleased" in the Fixed In column.

---

## Cross-Checks

### Cross-1: Are there contradictions between fixes and documentation?
**PASS** -- No contradictions found.

- CHANGELOG says COMPAT-06 through COMPAT-13 are fixed -- code confirms all four fixes exist.
- CHANGELOG says evaluate_rules() returns deny on error -- code line 1445 confirms.
- CHANGELOG says MAX_COMMAND_LENGTH docstring corrected -- code line 81 confirms.
- CHANGELOG says hookBehavior/scanTiers/validate wired -- all verified in code.
- KNOWN-ISSUES marks all four COMPAT items as FIXED -- code confirms all four fixes.
- README says fail-closed on timeout/error -- code confirms (hookBehavior defaults to "deny").

### Cross-2: Does the CHANGELOG accurately reflect what actually changed in code?
**PASS** -- All CHANGELOG entries verified.

One minor observation: The CHANGELOG "Added" section mentions `make_hook_behavior_response()` as new, which is accurate. It also mentions `validate_guardian_config()` being "called during config loading" -- this is accurately described as an "Added" item since the function existed but was never called. The wiring is new.

### Cross-3: Are any KNOWN-ISSUES still marked as open that should be marked fixed?
**PASS** -- No mismatches found.

- The two code-level fixes not tracked as COMPAT issues (evaluate_rules fail-open, MAX_COMMAND_LENGTH docstring) are not in KNOWN-ISSUES, which is correct -- they were discovered as part of this fix round, not previously tracked issues.
- UX-12 is correctly marked FIXED (line 106).
- All open issues (UX-07, COMPAT-04, COMPAT-05, SCOPE-01, UX-09, UX-10, UX-11, COMPAT-12) are genuinely still open -- none of them were addressed in this round.

---

## Summary

| Team | Item | Verdict |
|------|------|---------|
| A | A1: COMPAT-13 (circuit breaker rm/del) | PASS |
| A | A2: COMPAT-08 ($schema removed) | PASS |
| A | A3: COMPAT-06 (normalize_path project dir) | PASS |
| A | A4: COMPAT-07 (6x sys.platform != "linux") | PASS |
| A | A5: evaluate_rules() fail-closed | PASS |
| A | A6: MAX_COMMAND_LENGTH docstring | PASS |
| B | B1: validate_guardian_config() wired | PASS |
| B | B2: make_hook_behavior_response() exists | PASS |
| B | B3: hookBehavior in 4 security hooks | PASS |
| B | B4: scanTiers implemented | PASS |
| B | B5: with_timeout() skipped with TODO | PASS |
| B | B6: auto_commit.py not modified | PASS |
| C | C1: Shell profile persistence | PASS |
| C | C2: Marketplace unverified | PASS |
| C | C3: Troubleshooting section | PASS |
| C | C4: Python 3.10+ in Installation | PASS |
| C | C5: Dry-run tip in Setup | PASS |
| C | C6: CHANGELOG unreleased entries | PASS |
| C | C7: KNOWN-ISSUES strikethrough fixes | PASS |
| C | C8: Fixed Issues table updated | PASS |
| X | Cross-1: No contradictions | PASS |
| X | Cross-2: CHANGELOG accurate | PASS |
| X | Cross-3: No stale open issues | PASS |

**Result: 23/23 items PASS. All claimed fixes verified as present and correct.**
