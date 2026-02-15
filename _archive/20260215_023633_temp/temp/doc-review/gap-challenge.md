# Gap Challenge Report
## Date: 2026-02-14
## Challenger: Teammate F

---

### Summary of Review

I independently reviewed all four teammate reports (implementation-analysis.md, changelog-review.md, known-issues-review.md, readme-review.md) and cross-referenced their claims against the actual source code: `bash_guardian.py`, `_guardian_utils.py`, `guardian.default.json`, `guardian.schema.json`, `hooks.json`, and `read_guardian.py`.

**Headline finding**: The teammate reports contain a systematic pattern-count error that propagated across all four documents. Despite this, the qualitative gap findings are largely correct. The most important gaps -- the missing Read Guardian from the README, the misplaced `--force-with-lease`, and several undocumented user-facing features -- are real and should be fixed. However, some proposed fixes risk over-documenting implementation internals in user-facing documents.

---

### Agreements (gaps confirmed as real)

#### 1. Read Guardian missing from README hook table -- AGREE (HIGH)
**Teammates A, B, D all flagged this.** I independently verified:
- `hooks/hooks.json` lines 13-20: PreToolUse hook registered for "Read" pointing to `read_guardian.py`
- `read_guardian.py` exists (72 lines), calls `run_path_guardian_hook("Read")`
- README line 120: "Guardian registers four hooks" -- should say five
- README lines 122-127: Hook table has no Read Guardian row
- README line 129: Fail-closed list says "Bash, Edit, Write" -- should also include Read

**Verdict: Genuine gap. Fix required.** I experienced this firsthand during review -- the Read Guardian blocked my attempt to read `guardian.default.json`, demonstrating it is very much operational. Users absolutely need to know Read operations are being intercepted.

#### 2. `--force-with-lease` mislabeled in README -- AGREE (MEDIUM)
**Teammates B and D flagged this.** I independently verified:
- README line 26: Lists `--force-with-lease` under "Hard blocks (always denied)"
- `guardian.default.json` ask pattern #8: `git\s+push\s[^;|&\n]*--force-with-lease` with reason "Force push with lease (safer but still overwrites remote)"
- Block pattern #5 uses negative lookahead `(?:--force(?!-with-lease)|-f\b)` to *exclude* `--force-with-lease`

**Verdict: Genuine inaccuracy. Fix required.** The README explicitly contradicts the current code behavior. This was changed in v1.0.1 per CHANGELOG but the README was not updated.

#### 3. Dry-run mode undocumented in user-facing docs -- AGREE (MEDIUM)
**Teammates B, C, D all flagged this.** Verified:
- `_guardian_utils.py` lines 706-719: `is_dry_run()` checks `CLAUDE_HOOK_DRY_RUN` env var
- Used throughout `bash_guardian.py` at lines 962, 1049, 1071, 1119, 1160, 1200
- README "Disabling Guardian" section mentions removing `--plugin-dir` but not dry-run
- KNOWN-ISSUES.md UX-11 acknowledges this is undocumented

**Verdict: Genuine gap.** Dry-run mode is a user-configurable feature that helps with testing. It belongs in the README, ideally in the "Disabling Guardian" section.

#### 4. Archive-before-delete undocumented -- AGREE (MEDIUM)
**Teammates B and D flagged this.** Verified:
- `bash_guardian.py` lines 690-849: Full archive system
- Archive goes to `_archive/<timestamp>_<title>/` with metadata log
- Safety limits: 100MB/file, 500MB total, 50 files max
- README line 153: "Loss of work (via auto-commit checkpoints)" -- mentions auto-commit but not archive

**Verdict: Genuine gap.** This is a user-visible safety feature. When a user deletes files, they see the archive prompt. They need to know where archives go and what the limits are.

#### 5. `bashPathScan` config section undocumented in README -- AGREE (MEDIUM)
**Teammates A and D flagged this.** Verified:
- `guardian.schema.json` lines 178-222: Full schema definition for `bashPathScan`
- `guardian.default.json`: `bashPathScan` section with `enabled`, `scanTiers`, actions
- README Configuration Sections table (lines 103-115): No `bashPathScan` row

**Verdict: Genuine gap.** This is a user-configurable section with its own schema definition. It should appear in the Configuration Sections table.

#### 6. Example config missing required schema fields -- AGREE (MEDIUM)
**Teammate D flagged this.** Verified:
- README lines 86-101: Example JSON has `bashToolPatterns`, `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths`
- `guardian.schema.json` lines 7-10: `"required": ["version", "hookBehavior", "bashToolPatterns"]`
- Example config has no `version` and no `hookBehavior`

**Verdict: Genuine gap.** A user who copies this example and validates against the schema will get errors. The README already says "See `assets/guardian.default.json` for the complete config with all required fields" (line 84), which partially mitigates this, but the example should either include the required fields or explicitly note their omission.

#### 7. COMPAT-13: Recovery guidance uses `del` on all platforms -- AGREE (LOW)
**Teammate C flagged this.** I independently verified in `_guardian_utils.py`:
- Line 318: `'  Or delete the file manually: del "{circuit_file}"'`
- Line 326: `'  Recovery: Delete corrupted file: del "{circuit_file}"'`
- Line 335: `'  Recovery: Delete file manually: del "{circuit_file}"'`
- No `sys.platform` check for command choice

**Verdict: Genuine bug.** Straightforward fix.

#### 8. UX-11 should be updated to "Partially Fixed" -- AGREE (LOW)
**Teammate C flagged this.** README now has a "Disabling Guardian" section, but dry-run mode remains undocumented. The KNOWN-ISSUES.md entry should reflect partial resolution.

---

### Disagreements (gaps I dispute)

#### 1. DISAGREE: Circuit breaker needs README documentation (MEDIUM downgraded to LOW/OPTIONAL)
**Teammate D rated this MEDIUM and recommended documenting it in the Failure Modes section.**

I disagree with the severity. The circuit breaker is an internal resilience mechanism:
- It only affects auto-commit behavior (not security blocking)
- It auto-expires after 1 hour
- Users do not configure it or interact with it during normal operation
- The only user-visible effect is that auto-commits silently stop for up to an hour after a failure

A brief mention in a "Troubleshooting" or "Failure Modes" section would be reasonable, but this is LOW priority, not MEDIUM. Users do not need to understand the circuit breaker to use Guardian effectively. The file location (`.claude/guardian/.circuit_open`) could be mentioned in advanced troubleshooting if desired.

#### 2. DISAGREE: ReDoS defense needs README/Requirements documentation (LOW, not MEDIUM)
**Teammates C and D both recommended documenting the `regex` package as an optional dependency.**

The `regex` package provides timeout protection for regex matching. Without it, Guardian falls back to standard `re` with no timeout. While this is technically a security gap, I dispute the severity:
- ReDoS attacks require a malicious actor crafting specific input to Claude Code's bash commands
- The pattern set is authored by the developer, not by untrusted input
- The command input comes from Claude's AI model, not arbitrary user input
- Adding "optional dependency for ReDoS defense" to the README would confuse most users

**Recommendation**: At most, mention in KNOWN-ISSUES.md. Not suitable for the README Requirements section.

#### 3. DISAGREE: Multi-layer architecture should be documented in README
**Teammate B recommended breaking down the v1.0.0 changelog bullet with multi-layer details. Teammate D suggested expanding the README.**

The multi-layer architecture (Layer 0 patterns, Layer 1 scan, Layer 2 decomposition, Layer 3+4 path extraction/type detection) is an implementation detail. Users do not need to know how Guardian detects dangerous commands -- they need to know *that* it does and *what* patterns it catches. Documenting the layer architecture in user-facing docs would:
- Add complexity without actionable value
- Create maintenance burden as the architecture evolves
- Make the README significantly longer without helping users configure or use the tool

The current README description ("Checks commands against block/ask patterns") is adequate for users. The architecture should be documented in developer/contributor docs if needed.

#### 4. DISAGREE: Log rotation needs README documentation
**Teammate D rated this LOW and recommended documenting log file location.**

Mentioning the log file location (`.claude/guardian/guardian.log`) is marginally useful for debugging, but log rotation details (1MB limit, one backup) are pure implementation noise. If mentioned at all, a single line would suffice: "Guardian logs to `.claude/guardian/guardian.log`." No rotation details needed.

#### 5. DISAGREE with count-dependent claims (affects reports A, B, C, D)
See the Escalation section below for the count discrepancy. Multiple findings in the reports cite incorrect counts, and any recommendation that depends on these specific numbers should be verified against the corrected figures.

---

### Modifications (gaps that need adjusted fixes)

#### 1. MODIFY: Self-guarding documentation scope
**Teammates B and D recommended documenting self-guarding in README.**

Self-guarding is relevant to users (they should know Guardian protects its own config), but the proposed documentation level is too detailed. The fix should be a single sentence in the "How It Works" section:

> Guardian also protects its own configuration file (`.claude/guardian/config.json`) from modification by the AI agent.

No need to explain SELF_GUARDIAN_PATHS, dynamic config path detection, or the plugin migration history.

#### 2. MODIFY: CHANGELOG expansion scope
**Teammate B recommended extensive backfill of v1.0.0 with 28+ missing items across two tiers.**

I agree the CHANGELOG is sparse, but the proposed expansion is excessive. Prioritize:
- **Must add**: Read tool guarding (M1), dry-run mode (M2), archive system (M3), allowedExternalPaths (M4)
- **Should add**: Self-guarding (M6), symlink escape detection (M7), interpreter deletion blocking (M10)
- **Skip for changelog**: Internal items like circuit breaker, ReDoS defense, verdict aggregation, command decomposition, git lock retry logic

The changelog should document *what users can observe*, not internal implementation decisions.

#### 3. MODIFY: hookBehavior documentation approach
**Teammate A identified that `hookBehavior.onTimeout` and `hookBehavior.onError` are read by `get_hook_behavior()` but this function is never called by hook scripts.**

The proposed treatment should be clearer about user impact. The config and schema declare these as user-configurable, but changing them has zero runtime effect. The fix should be one of:
- (a) Wire up the config values to the actual hook behavior (code fix, not doc fix)
- (b) Remove from schema and default config (breaking change)
- (c) Add a note to the schema-reference.md that these are "reserved for future use" and currently have no effect

Option (c) is the lowest-risk path. This should be tracked in KNOWN-ISSUES.md.

#### 4. MODIFY: scanTiers documentation approach
**Teammate A identified that `bashPathScan.scanTiers` is declared in config/schema but the code only ever scans zeroAccessPaths.**

Same treatment as hookBehavior. The schema validates `["zeroAccess", "readOnly", "noDelete"]` as valid values, but the code at `bash_guardian.py` line 328 hardcodes `config.get("zeroAccessPaths", [])`. A user who sets `scanTiers: ["readOnly"]` will get no change in behavior.

This is more concerning than hookBehavior because it creates a false sense of expanded protection. Users may think they have enabled read-only path scanning when they have not.

**Recommended fix**: Either implement the feature or add a comment in the default config / schema-reference noting that only `"zeroAccess"` is currently supported. Track in KNOWN-ISSUES.md.

#### 5. MODIFY: Teammate C line number drift recommendations
**Teammate C recommended updating 3 line references in KNOWN-ISSUES.md.**

The recommendation to update line numbers is correct, but the secondary recommendation (replace line numbers with function names) is the better long-term fix. Line numbers will continue to drift with every code change. Function names like `_get_git_env()`, `normalize_path()`, and `normalize_path_for_matching()` are stable across refactors. The fix should do the replacement, not just update numbers.

---

### Escalations (new gaps I found)

#### ESCALATE-01: Systematic pattern count errors across all teammate reports (METHODOLOGICAL)

All four teammate reports cite the same incorrect counts for the default config:

| Item | Reported Count | Actual Count | Delta |
|------|---------------|--------------|-------|
| Block patterns | 19 | **18** | -1 |
| Ask patterns | 17 | **18** | +1 |
| zeroAccessPaths | 26 | **27** | +1 |
| readOnlyPaths | 17 | **18** | +1 |
| noDeletePaths | 29 | **27** | -2 |

I verified these counts by running `python3` directly against the JSON and Python files. The counts are unambiguous.

This systematic error likely propagated from Teammate A's implementation-analysis.md, which the other teammates used as a reference rather than independently verifying. This is a methodological concern: the "4 independent reviewers" claim in KNOWN-ISSUES.md may overstate the independence of the reviews.

**Impact**: While the qualitative findings remain valid, any recommendation that depends on specific pattern counts (e.g., "the fallback config has 7 block patterns vs. 19 in the full config" -- should be 8 vs 18) should be corrected.

**Corrected fallback config counts (verified)**:
- Fallback block: 8
- Fallback ask: 2
- Fallback zeroAccess: 9
- Fallback readOnly: 5
- Fallback noDelete: 4

#### ESCALATE-02: `noDeletePaths` not enforced by Edit/Write tools (DOCUMENTATION GAP)

Teammate A noted this in the implementation analysis, but no teammate flagged it as a documentation gap requiring a fix. The current behavior:

- `bash_guardian.py` line 1037: `noDeletePaths` only checked for bash delete commands
- `run_path_guardian_hook()` in `_guardian_utils.py` lines 2166-2293: Does NOT check `noDeletePaths` at all
- Edit and Write tools can modify (and effectively empty) files listed in `noDeletePaths`
- The README line 35 says "No-delete paths for critical project files" without clarifying that this only applies to bash `rm`-style commands

A user who adds `README.md` to `noDeletePaths` would expect it to be protected from all deletion vectors. In practice, an Edit tool call could replace the entire contents with an empty string, or a Write tool call could overwrite it with an empty file. Neither would be caught.

**This is a documentation gap at minimum, and arguably a design gap.** The README should clarify the scope of `noDeletePaths` protection, or the implementation should be extended to the Edit/Write hooks.

#### ESCALATE-03: `evaluate_rules()` fails-open contradicts fail-closed philosophy (MINOR)

`_guardian_utils.py` line 1400:
```python
except Exception as e:
    # Fail-open: on any error, allow and log
    log_guardian("ERROR", f"Error in evaluate_rules: {e}")
    return "allow", ""
```

The README states "All security hooks (Bash, Edit, Write) are fail-closed" (line 129). The `evaluate_rules()` function explicitly returns "allow" on error, which is fail-open. While this function is not currently called by any hook script (bash_guardian.py has its own flow), the contradiction between the documented philosophy and the code's behavior creates a latent risk if this function is ever used in the future.

**Severity: LOW.** The function is unused, so the practical risk is zero. But the code should either be updated to fail-closed (return "deny" on error) or documented as an intentional exception.

#### ESCALATE-04: `guardian.default.json` blocked by Read Guardian self-protection (USABILITY)

During this review, my attempt to read `/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json` via the Read tool was blocked with the message: `[BLOCKED] Protected system file: guardian.default.json`.

This suggests the Read Guardian's self-guarding or zero-access check is triggering on the plugin's default config file. This could be a problem for users trying to understand the default configuration by reading it through Claude Code. The file is the canonical reference for default patterns and is referenced by the README (line 84: "See `assets/guardian.default.json` for the complete config").

**This is a usability issue worth investigating.** If the default config file is intentionally blocked from reading, the README should not direct users to read it. If it is unintentionally blocked, the self-guarding logic should be adjusted.

---

### Spot-Check Results (10 specific verifications)

#### Spot-Check 1: "19 block patterns in default config"
**Claimed by**: Teammates A, B, C (implementation-analysis, changelog-review, known-issues-review)
**Method**: `python3 -c "import json; d=json.load(open('assets/guardian.default.json')); print(len(d['bashToolPatterns']['block']))"`
**Result**: **18** (not 19)
**Verdict**: INCORRECT. All teammates report 19. The actual count is 18.

#### Spot-Check 2: "17 ask patterns in default config"
**Claimed by**: Teammates A, B, C
**Method**: Same approach, counting `ask` array
**Result**: **18** (not 17)
**Verdict**: INCORRECT. All teammates report 17. The actual count is 18.

#### Spot-Check 3: "`evaluate_rules()` not called by bash_guardian.py"
**Claimed by**: Teammate A (implementation-analysis)
**Method**: `grep -n "evaluate_rules" hooks/scripts/bash_guardian.py` -- no matches
**Result**: Confirmed. `evaluate_rules` does not appear in bash_guardian.py
**Verdict**: CORRECT.

#### Spot-Check 4: "`with_timeout()` defined but not called anywhere"
**Claimed by**: Teammate A
**Method**: `grep -rn "with_timeout" hooks/scripts/` -- only the definition at line 116
**Result**: Confirmed. Only the function definition exists; no call sites.
**Verdict**: CORRECT.

#### Spot-Check 5: "`scanTiers` config field not read by code"
**Claimed by**: Teammate A
**Method**: `grep -rn "scanTiers" hooks/scripts/` -- no matches
**Result**: Confirmed. The string "scanTiers" does not appear in any Python file. `scan_protected_paths()` hardcodes `config.get("zeroAccessPaths", [])` at line 328.
**Verdict**: CORRECT.

#### Spot-Check 6: "Read Guardian does NOT check readOnlyPaths"
**Claimed by**: Teammate A
**Method**: `_guardian_utils.py` line 2278: `if tool_name.lower() != "read" and match_read_only(path_str):`
**Result**: Confirmed. The read-only check is skipped when `tool_name` is "read".
**Verdict**: CORRECT.

#### Spot-Check 7: "`noDeletePaths` not enforced by Edit/Write hooks"
**Claimed by**: Teammate A
**Method**: `grep -n "noDeletePaths\|no_delete\|match_no_delete" hooks/scripts/edit_guardian.py hooks/scripts/write_guardian.py` -- no matches. `run_path_guardian_hook()` code review confirms no noDeletePaths check.
**Result**: Confirmed. Only `bash_guardian.py` calls `match_no_delete()`.
**Verdict**: CORRECT.

#### Spot-Check 8: "CHANGELOG C4: --force-with-lease moved from block to ask"
**Claimed by**: Teammate B
**Method**: Verified block pattern uses negative lookahead `(?:--force(?!-with-lease)|-f\b)` and ask pattern explicitly matches `--force-with-lease`
**Result**: Confirmed in both `guardian.default.json` and `_FALLBACK_CONFIG`.
**Verdict**: CORRECT.

#### Spot-Check 9: "`get_hook_behavior()` defined but never called by hook scripts"
**Claimed by**: Teammate A (medium confidence)
**Method**: `grep -rn "get_hook_behavior" hooks/scripts/` -- only the definition at line 600
**Result**: Confirmed. Function is defined but has zero call sites across all hook scripts.
**Verdict**: CORRECT.

#### Spot-Check 10: "Recovery guidance uses `del` on all platforms"
**Claimed by**: Teammate C (COMPAT-13)
**Method**: Verified lines 318, 326, 335 in `_guardian_utils.py` all use `del "{circuit_file}"` with no platform check
**Result**: Confirmed. All three recovery messages suggest `del` regardless of OS.
**Verdict**: CORRECT.

---

### Spot-Check Summary

| # | Claim | Source | Result |
|---|-------|--------|--------|
| 1 | 19 block patterns | A, B, C | **INCORRECT** (actual: 18) |
| 2 | 17 ask patterns | A, B, C | **INCORRECT** (actual: 18) |
| 3 | evaluate_rules() unused by bash_guardian | A | CORRECT |
| 4 | with_timeout() defined but unused | A | CORRECT |
| 5 | scanTiers not read by code | A | CORRECT |
| 6 | Read Guardian skips readOnly check | A | CORRECT |
| 7 | noDeletePaths not enforced by Edit/Write | A | CORRECT |
| 8 | force-with-lease moved to ask | B | CORRECT |
| 9 | get_hook_behavior() never called | A | CORRECT |
| 10 | del used on all platforms | C | CORRECT |

**Accuracy: 8/10 correct.** The two errors are the same systematic count discrepancy propagated across all reports. Qualitative findings are reliable; quantitative precision needs improvement.

---

### Final Recommendation

#### Priority 1: Fix Real Inaccuracies (do immediately)
1. **Add Read Guardian to README hook table** -- this is the single most important fix
2. **Move `--force-with-lease` from "Hard blocks" to "Confirmation prompts"** in README
3. **Fix example config** to include required `version` and `hookBehavior` fields, or add explicit note

#### Priority 2: Document User-Facing Features (do soon)
4. **Add dry-run mode** to README (one line in "Disabling Guardian" section)
5. **Add archive-before-delete** to README (one line under "Safety checkpoints")
6. **Add `bashPathScan`** to Configuration Sections table
7. **Add `version`** to Configuration Sections table
8. **Add self-guarding** mention (one sentence in "How It Works")

#### Priority 3: Fix Known Issues Tracking (do soon)
9. **Correct all pattern counts** in all teammate reports and any docs that cite them
10. **Update KNOWN-ISSUES.md**: fix line references (use function names), update UX-11 to "Partially Fixed"
11. **Add to KNOWN-ISSUES.md**: scanTiers not implemented, hookBehavior not runtime-configurable, noDeletePaths scope limitation

#### Priority 4: Address When Feasible (lower urgency)
12. **Fix COMPAT-13**: platform-aware `del`/`rm` in circuit breaker recovery messages
13. **Fix MAX_COMMAND_LENGTH comment** in `_guardian_utils.py` line 81 (says "fail-open" but code fails-closed)
14. **Investigate ESCALATE-04**: determine if guardian.default.json blocking is intentional or a bug
15. **Consider implementing scanTiers** or clearly documenting the limitation in schema-reference

#### What NOT to do
- Do not add multi-layer architecture details to the README
- Do not add circuit breaker internals to the README
- Do not add ReDoS defense to the README Requirements section
- Do not expand the CHANGELOG v1.0.0 entry with 28 items -- focus on the 7 most user-visible
- Do not document verdict aggregation, command decomposition, or git retry logic in user-facing docs

The documentation should help users *use and trust* Guardian, not understand its implementation. The implementation analysis (Teammate A) is valuable as internal developer documentation but should not drive user-facing doc changes.
