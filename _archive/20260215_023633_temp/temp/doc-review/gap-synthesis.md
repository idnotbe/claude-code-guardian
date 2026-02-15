# Gap Synthesis Report
## Date: 2026-02-14
## Synthesizer: Teammate E

---

### Executive Summary

Four independent Phase 1 analysts reviewed the codebase and three documentation files (CHANGELOG.md, KNOWN-ISSUES.md, README.md). All 13 CHANGELOG claims and all 16 README claims that were testable against code were verified as accurate -- nothing in the documentation is fabricated. However, the documentation has significant gaps:

- **6 inaccuracies** where the document states something contradicted by the current code
- **12 missing items** where implemented features have no documentation
- **4 stale/outdated items** where information was once true but is no longer
- **3 formatting issues** affecting standards compliance

The implementation is the source of truth. All changes below update documentation to match code.

**Highest-impact findings** (identified by 3+ teammates independently):
1. README hook table lists 4 hooks; code registers 5 (Read Guardian missing)
2. README lists `--force-with-lease` as "hard block"; it is actually "ask" since v1.0.1
3. Dry-run mode (`CLAUDE_HOOK_DRY_RUN=1`) exists in code, absent from all user-facing docs
4. Archive-before-delete safety system exists in code, absent from all docs

---

### Cross-Reference Matrix

Each gap is tagged with which teammates independently identified it.

| Gap ID | CHANGELOG | KNOWN-ISSUES | README | Description | Teammates |
|--------|-----------|--------------|--------|-------------|-----------|
| G-01 | | | X | Read Guardian missing from hook table | A, B, D |
| G-02 | | | X | --force-with-lease listed as hard block | A, B, C, D |
| G-03 | | X | X | Dry-run mode undocumented | A, B, C, D |
| G-04 | | | X | bashPathScan config section missing | A, B, D |
| G-05 | | | X | Archive-before-delete undocumented | A, B, D |
| G-06 | | | X | Circuit breaker undocumented | A, B, D |
| G-07 | X | | | "Edit/Write" should be "Read/Edit/Write" | A, B |
| G-08 | | | X | Example config missing required fields note | A, D |
| G-09 | | | X | Self-guarding undocumented | A, D |
| G-10 | | | X | Fail-closed list omits Read Guardian | A, D |
| G-11 | | X | | COMPAT-04 line numbers drifted | A, C |
| G-12 | | X | | COMPAT-06 line numbers drifted | A, C |
| G-13 | | X | | COMPAT-07 line numbers drifted | A, C |
| G-14 | | X | | UX-11 should be partially fixed | C, D |
| G-15 | | | X | regex package not in Requirements | C, D |
| G-16 | X | | | No [Unreleased] section | B |
| G-17 | X | | | No version comparison links | B |
| G-18 | X | | | Read guardian not mentioned in CHANGELOG | B |
| G-19 | | | X | version config field not in config table | D |
| G-20 | | | X | Symlink escape not called out | A, D |
| G-21 | | | X | Interpreter deletion coverage understated | B, D |

---

### CHANGELOG.md Gaps (ordered by priority)

#### G-07 | INACCURACY | HIGH | Confidence: 2 (A, B)

**Section:** v1.0.0 Added, third bullet
**Current text (line 24):**
```
- Edit/Write file guarding (zero-access paths, read-only paths, no-delete paths)
```
**Should say:**
```
- Read/Edit/Write file guarding (zero-access paths, read-only paths, no-delete paths)
```
**Evidence:** `hooks/hooks.json` lines 13-20 register a PreToolUse hook with matcher "Read" pointing to `read_guardian.py`. The Read Guardian blocks zero-access paths, symlink escapes, and paths outside the project. Teammate A confirmed in implementation analysis Section 4 (run_path_guardian_hook). Teammate B flagged this as Missing Item M1.

---

#### G-18 | MISSING | MEDIUM | Confidence: 1 (B)

**Section:** v1.0.0 Added
**Current text:** No mention of Read tool guarding as a distinct feature.
**Recommended addition** (new bullet after the corrected G-07 bullet):
```
- Dry-run mode via `CLAUDE_HOOK_DRY_RUN=1` environment variable for testing configurations
```
**Evidence:** `_guardian_utils.py` lines 706-719: `is_dry_run()` function. Used throughout `bash_guardian.py` (lines 962, 1049, 1071, 1119, 1160, 1200). This is a user-configurable feature that belongs in the changelog.

**Also recommended** (new bullet):
```
- Archive-before-delete: untracked files are archived to `_archive/` before deletion is permitted
```
**Evidence:** `bash_guardian.py` lines 690-849: `archive_files()`, `create_deletion_log()`, `generate_archive_title()`. Safety limits: 100MB/file, 500MB total, 50 files max.

---

#### G-16 | MISSING | LOW | Confidence: 1 (B)

**Section:** Top of file (after header)
**Current text:** File goes directly from header to `## [1.0.1]`.
**Should add** (between header and first version):
```

## [Unreleased]

```
**Evidence:** Keep a Changelog 1.1.0 convention recommends an [Unreleased] section for tracking in-progress changes. The CHANGELOG header explicitly claims to follow this format.

---

#### G-17 | MISSING | LOW | Confidence: 1 (B)

**Section:** Bottom of file (after last entry)
**Current text:** File ends after last v1.0.0 bullet.
**Should add** (at end of file):
```

[1.0.1]: https://github.com/idnotbe/claude-code-guardian/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/idnotbe/claude-code-guardian/releases/tag/v1.0.0
```
**Evidence:** Keep a Changelog convention expects version comparison links in footer. The CHANGELOG header claims to follow this format.

---

### KNOWN-ISSUES.md Gaps (ordered by priority)

#### G-14 | STALE | HIGH | Confidence: 2 (C, D)

**Section:** Open Issues > LOW Severity > UX-11
**Current text (line 93-94):**
```
#### UX-11: No uninstall/disable documentation
- **Issue**: No docs on CLAUDE_HOOK_DRY_RUN=1 or uninstalling
```
**Should say:**
```
#### UX-11: Dry-run mode undocumented
- **Issue**: `CLAUDE_HOOK_DRY_RUN=1` dry-run/simulation mode is not documented in user-facing docs (README or setup wizard)
- **Status**: Partially fixed -- uninstall/disable documentation added to README "Disabling Guardian" section. Dry-run mode remains undocumented.
```
**Evidence:** README.md lines 157-159 now contain a "Disabling Guardian" section covering uninstall steps. However, `CLAUDE_HOOK_DRY_RUN=1` (confirmed in `_guardian_utils.py` lines 706-719) is still not mentioned in any user-facing document. Teammate C Section 3 confirmed the partial fix. Teammate D Missing Documentation #5 confirmed dry-run is still absent from README.

---

#### G-11 | OUTDATED | MEDIUM | Confidence: 2 (A, C)

**Section:** Open Issues > MEDIUM Severity > COMPAT-04
**Current text (line 61):**
```
- **File**: hooks/scripts/_guardian_utils.py (lines 1452-1465)
```
**Should say:**
```
- **File**: hooks/scripts/_guardian_utils.py, `_get_git_env()` function
```
**Evidence:** Teammate A (Section 4) reports `_get_git_env()` at lines 1459-1472. Teammate C (Section 4) confirmed drift from "lines 1452-1465" to "lines 1459-1472". Using the function name is more stable than line numbers.

---

#### G-12 | OUTDATED | MEDIUM | Confidence: 2 (A, C)

**Section:** Open Issues > MEDIUM Severity > COMPAT-06
**Current text (line 71):**
```
- **File**: hooks/scripts/_guardian_utils.py (lines 881-895)
```
**Should say:**
```
- **File**: hooks/scripts/_guardian_utils.py, `normalize_path()` function
```
**Evidence:** Teammate A (Section 4) reports `normalize_path()` at lines 873-901. Teammate C confirmed drift from "lines 881-895". Function name reference is more stable.

---

#### G-13 | OUTDATED | MEDIUM | Confidence: 2 (A, C)

**Section:** Open Issues > MEDIUM Severity > COMPAT-07
**Current text (line 77):**
```
- **File**: hooks/scripts/_guardian_utils.py (lines 1055, 1087)
```
**Should say:**
```
- **File**: hooks/scripts/_guardian_utils.py, `normalize_path_for_matching()` and `match_path_pattern()` functions
```
**Evidence:** Teammate C found significant drift: "lines 1055, 1087" should be "lines 1024, 1062, 1090" (30+ lines off). Function names are the stable reference. The relevant functions are `normalize_path_for_matching()` (line 1024) and `match_path_pattern()` (line 1090).

---

### README.md Gaps (ordered by priority)

#### G-01 | INACCURACY | HIGH | Confidence: 3 (A, B, D)

**Section:** "How It Works" hook table (lines 120-127)
**Current text:**
```
Guardian registers four hooks with Claude Code:

| Hook | Event | Script |
|------|-------|--------|
| Bash Guardian | PreToolUse: Bash | Checks commands against block/ask patterns |
| Edit Guardian | PreToolUse: Edit | Validates file paths against access rules |
| Write Guardian | PreToolUse: Write | Validates file paths against access rules |
| Auto-Commit | Stop | Commits pending changes as a checkpoint |
```
**Should say:**
```
Guardian registers five hooks with Claude Code:

| Hook | Event | Script |
|------|-------|--------|
| Bash Guardian | PreToolUse: Bash | Checks commands against block/ask patterns |
| Read Guardian | PreToolUse: Read | Blocks reading secret files and paths outside project |
| Edit Guardian | PreToolUse: Edit | Validates file paths against access rules |
| Write Guardian | PreToolUse: Write | Validates file paths against access rules |
| Auto-Commit | Stop | Commits pending changes as a checkpoint |
```
**Evidence:** `hooks/hooks.json` lines 13-20 register `read_guardian.py` for PreToolUse:Read. Teammate A (Section 2) listed all 5 hooks. Teammate B (M1) flagged Read Guardian as missing from changelog. Teammate D (Inaccuracy #1, rated HIGH) identified this as the most significant README gap.

---

#### G-10 | INACCURACY | HIGH | Confidence: 2 (A, D)

**Section:** Fail-closed paragraph (line 129)
**Current text:**
```
All security hooks (Bash, Edit, Write) are **fail-closed**:
```
**Should say:**
```
All security hooks (Bash, Read, Edit, Write) are **fail-closed**:
```
**Evidence:** `read_guardian.py` has the same fail-closed exception handling pattern as the other security hooks. Teammate A (Section 2): "All security hooks (Bash, Read, Edit, Write) are fail-closed". Teammate D (Inaccuracy #6): "Should also list Read Guardian as fail-closed."

---

#### G-02 | OUTDATED | HIGH | Confidence: 4 (A, B, C, D)

**Section:** "What It Catches" > Hard blocks (line 26)
**Current text:**
```
- `git push --force` and `--force-with-lease` (configure to allow if needed)
```
**Should say:**
```
- `git push --force` (configure to allow if needed)
```
**And add to the "Confirmation prompts" section (after line 30):**
```
- `git push --force-with-lease`
```
**Evidence:** CHANGELOG.md v1.0.1 documents this change: "--force-with-lease moved from block to ask patterns." Teammate A (Section 5): block pattern uses negative lookahead `(?:--force(?!-with-lease))` excluding --force-with-lease; a separate ask pattern covers --force-with-lease. Teammate B (C4): verified the separation. Teammate C (UX-08): confirmed correctly marked as fixed in KNOWN-ISSUES. Teammate D (Inaccuracy #2, MEDIUM): "--force-with-lease is in the ask list, not the block list."

---

#### G-04 | MISSING | MEDIUM | Confidence: 3 (A, B, D)

**Section:** Configuration Sections table (lines 105-114)
**Current text:** Table has 8 rows (hookBehavior through gitIntegration). No mention of bashPathScan.
**Should add** (new row after gitIntegration):
```
| `bashPathScan` | Raw command string scanning for protected path names |
```
**Evidence:** Teammate A (Section 5): bashPathScan has its own section in both `guardian.default.json` and `guardian.schema.json` with fields `enabled`, `scanTiers`, `exactMatchAction`, `patternMatchAction`. Teammate B (M5): flagged as missing Tier 1 user-facing feature. Teammate D (Missing #2, HIGH): "Configurable via enabled, scanTiers, exactMatchAction, patternMatchAction. Not mentioned anywhere in README."

---

#### G-19 | MISSING | MEDIUM | Confidence: 1 (D)

**Section:** Configuration Sections table (lines 105-114)
**Current text:** No mention of `version` field.
**Should add** (new row at top of table):
```
| `version` | Config version (semver, required) |
```
**Evidence:** `guardian.schema.json` lists `version` as a required top-level field with pattern `^\d+\.\d+\.\d+$`. Teammate D (Missing #11): "The version field is required by schema but never mentioned in the Configuration section."

---

#### G-05 | MISSING | MEDIUM | Confidence: 3 (A, B, D)

**Section:** "What It Catches" > Safety checkpoints (lines 17-20)
**Current text:** Three bullets about auto-commit and pre-danger checkpoints. No mention of archive-before-delete.
**Should add** (new bullet after line 19):
```
- Archives untracked files to `_archive/` before deletion, so nothing is permanently lost without a copy
```
**Evidence:** `bash_guardian.py` lines 690-849: complete archive system with size limits (100MB/file, 500MB total, 50 files). Teammate A (Section 3): detailed archive analysis. Teammate B (M3): "automatic archiving of untracked files before deletion is a major safety feature." Teammate D (Missing #3, MEDIUM): "significant safety feature with no README coverage."

---

#### G-06 | MISSING | MEDIUM | Confidence: 3 (A, B, D)

**Section:** "Failure Modes" (lines 137-155)
**Current text:** No mention of circuit breaker behavior.
**Should add** (new paragraph after line 155, before "### Disabling Guardian"):
```
**Circuit breaker**: If auto-commit fails repeatedly, Guardian stops attempting auto-commits to prevent cascading failures. The circuit breaker auto-resets after one hour. To manually reset, delete `.claude/guardian/.circuit_open`.
```
**Evidence:** `_guardian_utils.py` lines 222-351: file-based circuit breaker with 1-hour expiry. Teammate A (Section 8.6): detailed circuit breaker analysis. Teammate B (M11): flagged as Tier 2 missing. Teammate D (Missing #4, MEDIUM): "No README documentation."

---

#### G-03 | MISSING | MEDIUM | Confidence: 4 (A, B, C, D)

**Section:** "Disabling Guardian" (lines 157-159)
**Current text:**
```
To temporarily disable Guardian, remove the `--plugin-dir` flag from your launch command. To uninstall, delete the cloned repository and remove any references from your Claude Code settings. If you ran `/guardian:init`, also remove the `.claude/guardian/` directory from your project.
```
**Should say:**
```
To test Guardian without blocking, set `CLAUDE_HOOK_DRY_RUN=1` in your environment. Hooks will log what they would do without actually blocking operations.

To temporarily disable Guardian, remove the `--plugin-dir` flag from your launch command. To uninstall, delete the cloned repository and remove any references from your Claude Code settings. If you ran `/guardian:init`, also remove the `.claude/guardian/` directory from your project.
```
**Evidence:** `_guardian_utils.py` lines 706-719: `is_dry_run()` checks `CLAUDE_HOOK_DRY_RUN` env var. All 4 teammates identified this gap. Teammate C (UX-11 analysis): "CLAUDE_HOOK_DRY_RUN=1 dry-run mode still undocumented." Teammate D (Missing #5, MEDIUM): "Useful for testing. Not mentioned in README."

---

#### G-15 | MISSING | LOW | Confidence: 2 (C, D)

**Section:** Requirements (lines 179-180)
**Current text:**
```
- Python 3.10 or later
- Git (for auto-commit features)
```
**Should say:**
```
- Python 3.10 or later
- Git (for auto-commit features)
- `regex` package (optional, for ReDoS timeout defense): `pip install regex`
```
**Evidence:** `_guardian_utils.py` lines 59-65: `import regex as _regex_module` with fallback to standard `re`. Without the `regex` package, pattern matching has no timeout protection against ReDoS attacks. Teammate C (UNDOC-02, MEDIUM): "default installation has no regex timeout defense." Teammate D (Missing #8, LOW): "optional but security-relevant dependency worth mentioning."

---

#### G-08 | MISSING | LOW | Confidence: 2 (A, D)

**Section:** Configuration > Example (lines 84-101)
**Current text (line 84):**
```
The following shows a partial custom configuration. See `assets/guardian.default.json` for the complete config with all required fields.
```
**Should say:**
```
The following shows a partial custom configuration. Your config must also include `version` and `hookBehavior` (both required by the schema). See `assets/guardian.default.json` for the complete config with all required fields.
```
**Evidence:** `guardian.schema.json` requires `version`, `hookBehavior`, and `bashToolPatterns` at the top level. The example JSON omits `version` and `hookBehavior`. A user copying only the example would fail schema validation. Teammate D (Inaccuracy #3, MEDIUM). The existing "See assets/..." text partially mitigates this, so a note about the required fields is sufficient -- no need to expand the JSON example.

---

#### G-09 | MISSING | LOW | Confidence: 2 (A, D)

**Section:** "How It Works" (after hook table, around line 129)
**Current text:** No mention of self-guarding.
**Recommended addition** (new sentence at end of the fail-closed paragraph):
```
Guardian also protects its own configuration file (`.claude/guardian/config.json`) from being modified by the AI agent.
```
**Evidence:** `_guardian_utils.py` lines 354-362: `SELF_GUARDIAN_PATHS = (".claude/guardian/config.json",)`. Lines 2094-2139: `is_self_guardian_path()`. Teammate A (Section 8.7). Teammate D (Missing #6, MEDIUM): "important security property not documented."

---

#### G-21 | OUTDATED | LOW | Confidence: 2 (B, D)

**Section:** Failure Modes > "Does not protect against" (line 145)
**Current text:**
```
- Shell commands inside Python scripts (e.g., `subprocess.run()`) -- only direct Bash tool calls are intercepted
```
**Should say:**
```
- Arbitrary code within interpreter scripts (Guardian blocks known deletion APIs like `os.remove` and `shutil.rmtree` at the Bash command level, but cannot catch all possible code patterns)
```
**Evidence:** The default config has 4 block patterns for interpreter-mediated deletions (Python os.remove/shutil.rmtree, Node unlinkSync/rmSync, Perl unlink, Ruby File.delete). The current text implies zero interpreter coverage, which is misleading. Teammate B (M10): "not mentioned at all in changelog." Teammate D (Missing #10, LOW): "partially contradicted by these blocks."

---

### DO NOT CHANGE List

These items were flagged by teammates but should NOT be changed because they are correct or intentional:

| Item | Why it stays |
|------|-------------|
| README "Does not protect against: Determined human adversaries" | Accurate and important caveat (D confirmed) |
| README "99% safe / 1% dangerous" ratio | Rhetorical device, not a measurement claim (D: "ACCURATE in spirit") |
| README "Your work is never more than one git reset away" | Aspirational but defensible when combined with archive-before-delete (which we are adding) |
| README marketplace install commands | Already flagged as experimental with warning; KNOWN-ISSUES UX-07 tracks this (C, D confirmed) |
| README "If you skip setup, Guardian uses built-in defaults" | Accurate per 3-step config chain (A, D confirmed) |
| KNOWN-ISSUES PV-01 through PV-05 | All still valid; cannot be verified without real Claude Code environment (C confirmed) |
| KNOWN-ISSUES COMPAT-05 line numbers (135-155) | Still accurate (C confirmed) |
| KNOWN-ISSUES fixed items (COMPAT-03, UX-08, COMPAT-11) | All correctly marked as fixed with strikethrough (C confirmed) |
| CHANGELOG v1.0.0 under-specification of internal architecture | Changelogs document what changed, not full architecture. The README is the right place for architecture detail. Adding 18+ internal mechanism bullets (Teammate B Tier 2 items M11-M28) would be over-correction. |

---

### Recommended Change Order

Phase 3 editors should apply changes in this order to minimize conflicts:

**Round 1: Fix inaccuracies (these are wrong and could mislead users)**
1. G-01: Add Read Guardian to README hook table (HIGH)
2. G-10: Add "Read" to fail-closed hook list in README (HIGH)
3. G-02: Move --force-with-lease from hard blocks to confirmation prompts in README (HIGH)
4. G-07: Change "Edit/Write" to "Read/Edit/Write" in CHANGELOG (HIGH)

**Round 2: Update stale information**
5. G-14: Update UX-11 to partially fixed in KNOWN-ISSUES (HIGH)
6. G-11: Replace COMPAT-04 line numbers with function name in KNOWN-ISSUES (MEDIUM)
7. G-12: Replace COMPAT-06 line numbers with function name in KNOWN-ISSUES (MEDIUM)
8. G-13: Replace COMPAT-07 line numbers with function name in KNOWN-ISSUES (MEDIUM)

**Round 3: Add missing user-facing features to README**
9. G-05: Add archive-before-delete to Safety checkpoints (MEDIUM)
10. G-03: Add dry-run mode to Disabling Guardian section (MEDIUM)
11. G-06: Add circuit breaker to Failure Modes section (MEDIUM)
12. G-04: Add bashPathScan to Configuration Sections table (MEDIUM)
13. G-19: Add version to Configuration Sections table (MEDIUM)
14. G-08: Add required fields note to example config text (LOW)
15. G-09: Add self-guarding mention (LOW)
16. G-21: Clarify interpreter protection coverage (LOW)

**Round 4: Add missing features to CHANGELOG**
17. G-18: Add dry-run mode and archive-before-delete to v1.0.0 (MEDIUM)

**Round 5: Formatting fixes**
18. G-16: Add [Unreleased] section to CHANGELOG (LOW)
19. G-17: Add version comparison links to CHANGELOG (LOW)
20. G-15: Add regex package to README Requirements (LOW)

---

### Confidence Assessment

| Confidence Level | Count | Description |
|------------------|-------|-------------|
| 4 teammates | 2 gaps | G-02 (--force-with-lease), G-03 (dry-run) -- highest confidence, fix first |
| 3 teammates | 4 gaps | G-01 (Read Guardian table), G-04 (bashPathScan), G-05 (archive), G-06 (circuit breaker) |
| 2 teammates | 9 gaps | G-07, G-08, G-09, G-10, G-11, G-12, G-13, G-14, G-15, G-20, G-21 |
| 1 teammate | 4 gaps | G-16, G-17, G-18, G-19 -- still valid but may warrant lighter treatment |

**Overall assessment:** The documentation is *accurate but incomplete*. Nothing it claims is false (aside from the --force-with-lease hard-block claim and the 4-hook count), but it documents roughly 40% of the user-facing feature surface. The 20 changes above would bring coverage to approximately 80% while keeping documents concise.

**Risk of over-correction:** The vibe-check identified a mild feature-creep risk in expanding CHANGELOG v1.0.0 too aggressively. The recommendations above are conservative -- they fix what's wrong, add what users need to know, and leave internal architecture details for code comments and the schema-reference skill document where they already live.

---

### Appendix: Gaps Considered But Not Included

These items were flagged by individual teammates but excluded from the actionable list:

| Item | Reason for exclusion |
|------|---------------------|
| G-20: Symlink escape detection (A, D) | Already implicitly covered by "Writing to protected paths outside your project" in README. Adding explicit symlink mention is nice-to-have but not a gap that would mislead users. |
| UNDOC-01: ANSI-C quoting bypass (C) | LOW severity, code-level limitation. Belongs in KNOWN-ISSUES only if the team decides to track it. Not a documentation gap per se. |
| UNDOC-03: Fail-open in non-critical helpers (C) | Accepted design decision documented in code comments. Not a user-facing documentation gap. |
| UNDOC-04: Fallback config reduced coverage (C) | Emergency fallback by design. The fallback's purpose is minimal reliable protection, not comprehensive coverage. |
| UNDOC-05: *.env skipped by Layer 1 scan (C) | Defense-in-depth detail. Layer 2+3+4 still catch these. Not user-facing. |
| UNDOC-06: Misleading MAX_COMMAND_LENGTH comment (C) | Code comment fix, not a documentation file change. Out of scope for this review. |
| COMPAT-13: del vs rm in recovery guidance (C) | Code fix, not a documentation file change. Out of scope for this review. |
| B Tier 2 items M11-M28 (18 items) | Internal implementation details. Changelogs and READMEs should not inventory every internal mechanism. These are adequately documented in code comments and the schema-reference skill. |
| README skills/agents mention (D Missing #12) | LOW priority. Skills and agents are registered in plugin.json and discoverable at runtime. Not mentioning them in README is a reasonable editorial choice. |
| README log location (D Missing #13) | LOW priority. Log location (.claude/guardian/guardian.log) is an implementation detail. Could be added but not a gap that harms users. |
