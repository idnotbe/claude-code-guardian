# KNOWN-ISSUES.md Review Report
## Date: 2026-02-14
## Reviewer: Teammate C

---

### 1. Document Overview

**File reviewed:** `/home/idnotbe/projects/claude-code-guardian/KNOWN-ISSUES.md`
**Document version:** 1.0.0, last updated 2026-02-11
**Document structure:** Well-organized with Platform Verification (PV-01 through PV-05), Open Issues (MEDIUM and LOW severity), and a Fixed Issues reference table.

**Total items documented:**
- 5 Platform Verification items (PV-01 through PV-05)
- 7 Open MEDIUM-severity issues (3 marked FIXED with strikethrough)
- 8 Open LOW-severity issues (2 marked FIXED with strikethrough, 1 marked Resolved)
- 14 entries in the Fixed Issues table

**Methodology:** Each issue was verified by reading the referenced source files (`hooks/scripts/bash_guardian.py`, `hooks/scripts/_guardian_utils.py`, `assets/guardian.default.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `hooks/hooks.json`, `commands/init.md`, `agents/config-assistant.md`, `skills/config-guide/references/schema-reference.md`) and cross-referencing the described behavior against the current implementation.

---

### 2. Issues Still Valid (confirmed still in code)

#### PV-01: CLAUDE_PLUGIN_ROOT Expansion
**Status: STILL VALID**
Verified in `hooks/hooks.json` (lines 9, 18, 27, 36, 46) -- all five hook commands use `${CLAUDE_PLUGIN_ROOT}` in their command strings. This assumption remains unverified in a real Claude Code environment.

#### PV-02: Hook JSON Protocol
**Status: STILL VALID**
Verified in `hooks/scripts/bash_guardian.py` (lines 63-66) -- the code outputs JSON with `hookSpecificOutput.permissionDecision` set to `"deny"`. The `deny_response()` and `ask_response()` functions in `_guardian_utils.py` produce this format. Still requires real-environment validation.

#### PV-03: Skill and Agent Discovery
**Status: STILL VALID**
Verified in `.claude-plugin/plugin.json` (lines 13-18) -- `skills` and `agents` arrays are declared. Whether Claude Code actually discovers them from these paths remains unverified.

#### PV-04: Marketplace Resolution
**Status: STILL VALID**
Verified in `.claude-plugin/marketplace.json` -- the file exists with a hypothetical `$schema` URL. No way to verify without the actual Claude Code marketplace infrastructure.

#### PV-05: Command Registration
**Status: STILL VALID**
Verified in `.claude-plugin/plugin.json` (line 11) -- `commands` array references `./commands/init.md`. Requires real-environment testing.

#### COMPAT-04: LC_ALL=C on non-MSYS2 Windows git
**Status: STILL VALID**
Verified in `_guardian_utils.py` lines 1459-1472 -- `_get_git_env()` unconditionally sets `LC_ALL=C`. No Windows-specific handling or detection of MSYS2 vs native git.
**Note:** Line reference in KNOWN-ISSUES.md says "lines 1452-1465" but the function is now at lines 1459-1472. Line numbers have drifted.

#### COMPAT-05: Thread-based timeout non-killable on Windows
**Status: STILL VALID**
Verified in `_guardian_utils.py` lines 135-155 -- the `with_timeout()` function uses `threading.Thread` with `daemon=True` and `thread.join(timeout=timeout_seconds)` on Windows. The thread cannot be forcibly killed if it hangs.
**Note:** Line reference in KNOWN-ISSUES.md says "lines 135-155" which is accurate.

#### COMPAT-06: normalize_path resolves against CWD
**Status: STILL VALID**
Verified in `_guardian_utils.py` lines 873-898 -- `normalize_path()` uses `os.path.abspath(expanded)` which resolves relative paths against CWD, not the project directory. The separate function `normalize_path_for_matching()` (line 1005) resolves against the project dir via `expand_path()`, but `normalize_path()` itself does not.
**Note:** Line reference in KNOWN-ISSUES.md says "lines 881-895" but the function spans lines 873-901. Minor drift.

#### COMPAT-07: fnmatch case sensitivity on macOS
**Status: STILL VALID**
Verified in `_guardian_utils.py`:
- `normalize_path()` at line 896: lowercases only on `sys.platform == "win32"`
- `normalize_path_for_matching()` at line 1024: lowercases only on `sys.platform == "win32"`
- `match_path_pattern()` at line 1090: lowercases pattern only on `sys.platform == "win32"`

macOS HFS+ is case-insensitive by default, but paths are not lowercased for matching. The suggested fix (using `sys.platform != 'linux'` instead of `sys.platform == 'win32'`) has not been applied.
**Note:** Line references in KNOWN-ISSUES.md ("lines 1055, 1087") have drifted -- the relevant lines are now 1024, 1062, 1090.

#### UX-07: README marketplace install commands unverified
**Status: STILL VALID**
The README contains marketplace installation commands that remain speculative. No way to verify until actual Claude Code plugin CLI documentation is available.

#### UX-09: Schema reference common patterns note
**Status: STILL VALID**
Verified in `skills/config-guide/references/schema-reference.md` lines 192-203 -- the "Common patterns" table lists patterns like `.env`, `*.pem`, `~/.ssh/**` etc. without noting that these are already pre-included in the default configuration. A user reading this might redundantly add them to their config.

#### UX-10: Config-assistant agent lacks sample output
**Status: STILL VALID**
Verified in `agents/config-assistant.md` -- the trigger examples (lines 27-61) show input scenarios and actions but do not include example output format. The "Workflow" section describes steps but does not demonstrate what the agent's actual response would look like.

#### COMPAT-08: Relative $schema in default config
**Status: STILL VALID**
Verified: `assets/guardian.default.json` contains `"$schema": "./guardian.schema.json"`. When this file is used as a template and the user copies it to `.claude/guardian/config.json`, the relative `$schema` path will not resolve correctly since `guardian.schema.json` is not in that directory.

#### COMPAT-12: Hypothetical marketplace schema URL
**Status: STILL VALID**
Verified: `.claude-plugin/marketplace.json` contains `"$schema": "https://anthropic.com/claude-code/marketplace.schema.json"`. This URL is hypothetical -- no indication that Anthropic hosts such a schema. As documented, it has no runtime impact.

#### COMPAT-13: Recovery guidance uses Windows del on all platforms
**Status: STILL VALID**
Verified in `_guardian_utils.py` lines 312-337 -- three separate recovery guidance messages in `is_circuit_open()` all suggest `del "{circuit_file}"` regardless of platform:
- Line 318: `'  Or delete the file manually: del "{circuit_file}"'`
- Line 326: `'  Recovery: Delete corrupted file: del "{circuit_file}"'`
- Line 335: `'  Recovery: Delete file manually: del "{circuit_file}"'`

On Linux/macOS, this should suggest `rm` instead of `del`. No `sys.platform` check is present.

---

### 3. Issues Now Fixed (should be removed/updated)

#### COMPAT-03: shlex.split quote handling on Windows -- CORRECTLY MARKED FIXED
The document already shows this as `~~FIXED~~` with strikethrough. Verified the fix in `hooks/scripts/bash_guardian.py` lines 477-480: `shlex.split(posix=False)` is used on Windows, followed by quote stripping (`parts = [p.strip("'\"") for p in parts]`).
**Recommendation:** Already correctly documented as fixed. No change needed.

#### UX-08: Default blocks --force-with-lease -- CORRECTLY MARKED FIXED
The document already shows this as `~~FIXED~~`. Verified in `assets/guardian.default.json`:
- Block pattern uses negative lookahead: `(?:--force(?!-with-lease)|-f\b)` which excludes `--force-with-lease`
- Ask pattern includes: `git\s+push\s[^;|&\n]*--force-with-lease`
The fallback config in `_guardian_utils.py` (line 382-388) also correctly implements this separation.
**Recommendation:** Already correctly documented as fixed. No change needed.

#### COMPAT-11: errno 28 disk full check -- CORRECTLY MARKED FIXED
The document already shows this as `~~FIXED~~`. Verified in `hooks/scripts/bash_guardian.py` line 814: `is_disk_full = e.errno == 28 or getattr(e, "winerror", None) == 112`. The cross-platform check is in place.
**Note:** Interestingly, `_guardian_utils.py` itself does NOT contain any `errno` or `winerror` checks -- the fix was only applied in `bash_guardian.py`. If disk-full errors occur in `_guardian_utils.py` functions, they would not get the same cross-platform handling. This is a minor gap but not directly related to the documented issue.
**Recommendation:** Already correctly documented as fixed. No change needed.

#### UX-11: No uninstall/disable documentation -- PARTIALLY FIXED
**Status: Should be updated to PARTIALLY FIXED**
The README now contains a "Disabling Guardian" section (verified at approximately offset 6935 in README.md) that explains:
- Temporarily disable: remove `--plugin-dir` flag
- Uninstall: delete cloned repository and remove references
- Clean up: remove `.claude/guardian/` directory

However, `CLAUDE_HOOK_DRY_RUN=1` (the dry-run mode) is still not documented in any user-facing documentation outside of code comments and the schema-reference.md dry-run test tip (line 316). The KNOWN-ISSUES.md text specifically mentions this env var as missing documentation.
**Recommendation:** Update to "Partially fixed -- uninstall docs added, CLAUDE_HOOK_DRY_RUN=1 dry-run mode still undocumented in user-facing docs."

#### UX-12: init.md quick tips depend on skill/agent -- CORRECTLY MARKED RESOLVED
The document says "Resolved -- skill/agent now registered in plugin.json." Verified in `.claude-plugin/plugin.json` lines 13-18: skills and agents arrays are properly declared. The `commands/init.md` Step 6 quick tips (lines 157-158) reference "Say 'block [command]'" and "Say 'show guardian config'" which would trigger the agent, but do not require explicit skill/agent references -- they rely on the agent's trigger detection.
**Recommendation:** Already correctly documented as resolved. No change needed.

---

### 4. Issues with Inaccurate Descriptions

#### COMPAT-04: Line Numbers Drifted
**KNOWN-ISSUES.md says:** "lines 1452-1465"
**Actual location:** Lines 1459-1472 in `_guardian_utils.py`
**Impact:** Minor -- the line numbers are close but not exact. Could confuse someone trying to locate the code.

#### COMPAT-05: Line Numbers Accurate
**KNOWN-ISSUES.md says:** "lines 135-155"
**Actual location:** Lines 135-155 in `_guardian_utils.py`
**Status:** Accurate.

#### COMPAT-06: Line Numbers Drifted
**KNOWN-ISSUES.md says:** "lines 881-895"
**Actual location:** Lines 873-901 (`normalize_path` function) in `_guardian_utils.py`
**Impact:** Minor drift, the function is still in the same area.

#### COMPAT-07: Line Numbers Drifted
**KNOWN-ISSUES.md says:** "lines 1055, 1087"
**Actual location:** Lines 1024, 1062, 1090 in `_guardian_utils.py`
**Impact:** Significant drift -- 30+ lines off. Someone following these references would not find the code immediately.

#### Fixed Issues Table -- Accurate
The Fixed Issues reference table (14 entries) accurately reflects the fixes applied. All IDs, severities, and fix rounds appear consistent with the code state.

---

### 5. Undocumented Issues Found in Code

#### UNDOC-01: ANSI-C Quoting ($'...') Not Handled in split_commands
**File:** `hooks/scripts/bash_guardian.py`, line 96
**Description:** The `split_commands()` function has a documented limitation in its docstring: "Known limitation: ANSI-C quoting ($'...') is not specially handled." This means a command like `rm $'\x2e\x65\x6e\x76'` (which decodes to `rm .env`) would not be correctly parsed by the command splitter. The ANSI-C string could contain delimiter characters that get incorrectly treated as command separators.
**Severity:** LOW -- ANSI-C quoting is rarely used in typical command contexts, and Layer 1 (raw string scan) provides a secondary defense layer.
**Recommendation:** Add to KNOWN-ISSUES.md as a LOW severity issue.

#### UNDOC-02: Optional `regex` Module Dependency for ReDoS Protection
**File:** `hooks/scripts/_guardian_utils.py`, lines 56-65, 727-760
**Description:** The `safe_regex_search()` function attempts to import the `regex` module (third-party) for timeout-protected regex matching. If the `regex` module is not installed, the code falls back to standard `re` which has NO timeout capability. This means ReDoS attacks (specially crafted input that causes catastrophic regex backtracking) have no timeout defense in the default installation. The code logs a warning on first use but continues operating.
**Severity:** MEDIUM -- This is a security gap in the default installation. The `regex` module is not listed as a required dependency.
**Recommendation:** Add to KNOWN-ISSUES.md. Consider adding `regex` to a requirements.txt or noting it as a recommended dependency in the README.

#### UNDOC-03: Multiple fail-open Behaviors in Non-Critical Paths
**File:** `hooks/scripts/_guardian_utils.py`, multiple locations
**Description:** Several functions intentionally fail-open (return the original input or allow the operation) when errors occur:
- `normalize_path()` (line 900): returns original path on error
- `expand_path()` (line 922): returns `Path(path)` on error
- `is_symlink_escape()` (line 971): returns `False` on error (allows operation)
- `is_path_within_project()` (line 1000-1002): returns `True` on error (allows operation)
- `normalize_path_for_matching()` (line 1029): returns original path on error
- `run_path_guardian_hook()` (line 1400): allows and logs on error

These are intentional design decisions documented in code comments (the module docstring at line 38 states "Fail-open on non-critical errors (logging, path normalization)"), but they represent a security surface where errors could bypass protection.
**Severity:** LOW -- each case is individually reasonable, but the cumulative effect means a chain of errors could result in unprotected operations. The critical paths (block/deny decisions) correctly fail-closed.
**Recommendation:** Document as accepted design decision in KNOWN-ISSUES.md with an explanation that critical security decisions fail-closed while non-critical helpers fail-open.

#### UNDOC-04: FALLBACK_CONFIG has Reduced Pattern Coverage
**File:** `hooks/scripts/_guardian_utils.py`, lines 364-418
**Description:** The `_FALLBACK_CONFIG` (used when no config.json or plugin default can be loaded) has significantly fewer patterns than the full `guardian.default.json`. For example:
- The fallback `ask` list has only 2 patterns (force-with-lease, hard reset) vs. 17 in the full config
- The fallback `block` list has 7 patterns vs. 19 in the full config
- Missing from fallback: SQL injection patterns, `find -delete`, `xargs rm`, `eval` with deletion, fork bombs, curl|bash, etc.

This is partially by design (emergency fallback should be minimal and reliable), but it means a misconfigured or missing config file significantly reduces protection.
**Severity:** LOW -- the fallback is an emergency measure and the most critical patterns (root deletion, .git deletion, force push, interpreter deletion) are present.
**Recommendation:** Consider noting this in KNOWN-ISSUES.md as an accepted limitation.

#### UNDOC-05: `*.env` Pattern in zeroAccessPaths Skipped by Layer 1 Scan
**File:** `hooks/scripts/bash_guardian.py`, lines 289-297 (`glob_to_literals`)
**Description:** The `glob_to_literals()` function intentionally skips `*.env` because `env` is in the `generic_words` set (line 296). This means Layer 1 (raw string scan) will not detect commands referencing files like `production.env` or `staging.env`. These are only caught by Layer 2+3+4 if the file path can be extracted and resolved. A command that obfuscates the path (e.g., through variable expansion or encoding) could bypass both layers for `*.env` files.
**Severity:** LOW -- Layer 1 is a defense-in-depth measure. The exclusion prevents false positives on common strings containing "env" (like environment variables). The specific patterns `.env` and `.env.*` are still scanned by Layer 1.
**Recommendation:** Consider documenting as an accepted risk.

#### UNDOC-06: `MAX_COMMAND_LENGTH` Fail-Open for Non-Block Patterns
**File:** `hooks/scripts/_guardian_utils.py`, line 81
**Description:** The comment on `MAX_COMMAND_LENGTH` (100000 bytes) states "Commands exceeding this are still processed (fail-open) but logged." However, looking at the actual code in `match_block_patterns()` (line 810) and `match_ask_patterns()` (line 846), oversized commands are actually denied/asked respectively (fail-closed). The code comment is inaccurate -- the implementation correctly fails closed. This is not a code bug but a misleading code comment.
**Severity:** INFORMATIONAL -- the code is correct; only the comment is wrong.
**Recommendation:** Fix the comment at line 81 of `_guardian_utils.py`.

---

### 6. Recommendations

#### Priority 1: Update KNOWN-ISSUES.md Line References
Multiple line number references have drifted since the document was written. Recommend updating:
- COMPAT-04: Change "lines 1452-1465" to "lines 1459-1472"
- COMPAT-06: Change "lines 881-895" to "lines 873-901"
- COMPAT-07: Change "lines 1055, 1087" to "lines 1024, 1062, 1090"

Alternatively, replace line number references with function names (e.g., "`_get_git_env()` function") which are more stable across code changes.

#### Priority 2: Update UX-11 Status
Change from open issue to "Partially fixed" -- uninstall/disable documentation has been added to README, but `CLAUDE_HOOK_DRY_RUN=1` dry-run mode remains undocumented in user-facing docs.

#### Priority 3: Add Undocumented Issues
Add the following to KNOWN-ISSUES.md:
1. **UNDOC-01 (LOW):** ANSI-C quoting bypass in `split_commands()` -- already noted in code docstring but not tracked in KNOWN-ISSUES.md
2. **UNDOC-02 (MEDIUM):** Optional `regex` module for ReDoS protection -- default installation has no regex timeout defense
3. **UNDOC-03 (LOW, accepted design):** Fail-open behavior in non-critical helper functions

#### Priority 4: Fix Misleading Code Comment
In `_guardian_utils.py` line 81, the `MAX_COMMAND_LENGTH` comment says "fail-open" but the implementation correctly fails closed. Update the comment to match the actual behavior.

#### Priority 5: COMPAT-13 Fix
The `del` command in recovery guidance (3 locations in `_guardian_utils.py` `is_circuit_open()`) should use `sys.platform` to suggest `rm` on Unix-like systems and `del` on Windows. This is a straightforward fix:
```python
delete_cmd = "del" if sys.platform == "win32" else "rm"
```

#### Summary Table

| Issue ID | Status | Action Required |
|----------|--------|-----------------|
| PV-01 through PV-05 | Still valid | No change |
| UX-07 | Still valid | No change |
| COMPAT-03 | Fixed (correctly marked) | No change |
| COMPAT-04 | Still valid, line numbers drifted | Update line references |
| COMPAT-05 | Still valid | No change |
| COMPAT-06 | Still valid, line numbers drifted | Update line references |
| COMPAT-07 | Still valid, line numbers drifted | Update line references |
| COMPAT-08 | Still valid | No change |
| COMPAT-11 | Fixed (correctly marked) | No change |
| COMPAT-12 | Still valid | No change |
| COMPAT-13 | Still valid | Fix or document timeline |
| UX-08 | Fixed (correctly marked) | No change |
| UX-09 | Still valid | No change |
| UX-10 | Still valid | No change |
| UX-11 | Partially fixed | Update status |
| UX-12 | Resolved (correctly marked) | No change |
| UNDOC-01 | New, undocumented | Add to KNOWN-ISSUES.md (LOW) |
| UNDOC-02 | New, undocumented | Add to KNOWN-ISSUES.md (MEDIUM) |
| UNDOC-03 | New, undocumented | Add as accepted design (LOW) |
| UNDOC-04 | New, undocumented | Consider documenting (LOW) |
| UNDOC-05 | New, undocumented | Consider documenting (LOW) |
| UNDOC-06 | Misleading comment | Fix code comment (INFORMATIONAL) |
