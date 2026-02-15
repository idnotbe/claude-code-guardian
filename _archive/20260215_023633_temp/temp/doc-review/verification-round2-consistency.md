# Verification Round 2: Cross-Document Consistency Report
## Verifier: Teammate I (Final Consistency Checker)
## Date: 2026-02-14

---

## Documents Reviewed

- **README.md** (196 lines)
- **CHANGELOG.md** (37 lines)
- **KNOWN-ISSUES.md** (141 lines)

## Context: Round 1 verification reports reviewed for prior findings.

---

## Section A: Cross-Document Consistency

### Check 1: Does CHANGELOG mention features that README does not cover?

| CHANGELOG Feature | Covered in README? | Status |
|---|---|---|
| Bash command guarding (block/ask) | Yes -- "Hard blocks" + "Confirmation prompts" + config table | PASS |
| Read/Edit/Write file guarding | Yes -- hook table (line 129-131) + "Protected files" section | PASS |
| Auto-commit on session stop | Yes -- "Safety checkpoints" bullet 1 + hook table row 5 | PASS |
| Pre-danger checkpoint commits | Yes -- "Safety checkpoints" bullet 2 | PASS |
| Dry-run mode via CLAUDE_HOOK_DRY_RUN=1 | Yes -- "Disabling Guardian" section (line 168) | PASS |
| Archive-before-delete | Yes -- "Safety checkpoints" bullet 3 (line 20) | PASS |
| JSON Schema for config validation | Yes -- "See `assets/guardian.schema.json`" (line 120) | PASS |
| Default config template | Yes -- "Plugin default (`assets/guardian.default.json`)" (line 80) | PASS |
| `/guardian:init` setup command | Yes -- "Setup" section (lines 65-73) | PASS |
| Renamed guardian.json to config.json (v1.0.1) | Yes -- README uses `config.json` throughout (lines 71, 77, 79, 136) | PASS |
| Renamed evaluate_guardian() to evaluate_rules() (v1.0.1) | N/A -- internal API, not user-facing | PASS (correctly omitted from README) |
| shlex.split Windows fix (v1.0.1) | N/A -- internal fix, not user-facing | PASS (correctly omitted) |
| --force-with-lease moved to ask (v1.0.1) | Yes -- "Confirmation prompts" bullet 1 (line 30) | PASS |
| errno 28 Windows fix (v1.0.1) | N/A -- internal fix, not user-facing | PASS (correctly omitted) |

**Result: PASS.** No CHANGELOG feature is missing from README. Internal implementation changes are correctly excluded from README.

---

### Check 2: Does README mention features that CHANGELOG does not cover?

| README Feature | Covered in CHANGELOG? | Status |
|---|---|---|
| Safety checkpoints (auto-commit) | Yes -- "Auto-commit on session stop" in v1.0.0 Added | PASS |
| Pre-danger checkpoint | Yes -- "Pre-danger checkpoint commits" in v1.0.0 Added | PASS |
| Archive-before-delete | Yes -- v1.0.0 Added (line 30) | PASS |
| Hard blocks (rm -rf, fork bombs, etc.) | Yes -- "Bash command guarding (block dangerous patterns...)" | PASS |
| Confirmation prompts | Yes -- "...ask for confirmation on risky ones" | PASS |
| Protected files (zero-access, read-only, no-delete) | Yes -- "Read/Edit/Write file guarding (zero-access paths, read-only paths, no-delete paths)" | PASS |
| Self-guarding of config file | Not explicitly mentioned | NOTE |
| Circuit breaker | Not explicitly mentioned | NOTE |
| Fail-closed behavior | Not explicitly mentioned | NOTE |
| `bashPathScan` config section | Not explicitly mentioned | NOTE |
| `version` config field | Not explicitly mentioned | NOTE |
| `hookBehavior` config section | Not explicitly mentioned | NOTE |
| Testing section (~1,009 tests) | Not mentioned (added outside of gap plan) | NOTE |

**Result: PASS with notes.** The README contains more detail than the CHANGELOG, which is expected and appropriate. The CHANGELOG is a release-oriented summary; it does not need to enumerate every config field or behavioral detail. The features flagged as NOTE are all sub-features or behavioral details of the features already listed in the CHANGELOG (e.g., "fail-closed" is a behavioral property of "Bash command guarding," not a separate feature).

The Testing section is an unplanned addition (flagged in Round 1 completeness report) and is not changelog-worthy since it describes the test suite, not a product feature.

**No inconsistency.** The CHANGELOG is appropriately concise relative to the README's detail.

---

### Check 3: Does KNOWN-ISSUES reference things that README describes differently?

| KNOWN-ISSUES Claim | README Statement | Consistent? |
|---|---|---|
| UX-07: "Marketplace installation commands are speculative" | README line 56: "Marketplace integration is currently experimental" | PASS -- both acknowledge uncertainty |
| UX-11: "Dry-run mode undocumented" (title) | README line 168: Documents dry-run mode | **MINOR INCONSISTENCY** |
| UX-11 status: "Partially fixed -- ...dry-run mode remains undocumented in setup wizard" | README documents dry-run; setup wizard status unknown | PASS -- status line is accurate when read precisely |
| SCOPE-01: "noDeletePaths only enforced for Bash delete commands" | README line 37: "No-delete paths for critical project files" | **MINOR TENSION** |
| COMPAT-06: "normalize_path resolves against CWD" | Not discussed in README | PASS -- internal implementation detail |
| COMPAT-07: "fnmatch case sensitivity on macOS" | Not discussed in README | PASS -- internal implementation detail |
| PV-01 through PV-05: Platform verification items | README does not mention these | PASS -- pre-release internal tracking |

**Findings:**

1. **UX-11 title vs. README (MINOR):** The KNOWN-ISSUES title says "Dry-run mode undocumented" but the README now documents it in the "Disabling Guardian" section. The status line ("Partially fixed -- ...Dry-run mode remains undocumented in setup wizard") is accurate when read carefully, but the title is misleading post-edit. This was already flagged in both Round 1 reports (accuracy report Issue 2, completeness report observation 1).

   **Severity: LOW.** The status line correctly narrows the scope. A reader of KNOWN-ISSUES who reads only the title could be confused, but the body clarifies.

2. **SCOPE-01 vs. README "No-delete paths" (MINOR):** README line 37 says "No-delete paths for critical project files" under "Protected files (access controls)." This could give users the impression that no-delete protection is comprehensive across all tools. KNOWN-ISSUES SCOPE-01 clarifies that noDeletePaths is only enforced for Bash delete commands, not Edit/Write tools. These are not contradictory -- the README describes the feature's intent, KNOWN-ISSUES describes its limitation -- but a user reading only the README would not know about the scope limitation.

   **Severity: LOW.** This is a known and accepted design limitation (marked "By-design" in KNOWN-ISSUES). The README is not technically wrong -- no-delete paths DO exist -- but it does not communicate the enforcement boundary. This is appropriate; README is not the place for implementation caveats. KNOWN-ISSUES serves that purpose.

---

### Check 4: Are version numbers consistent across all docs?

| Document | Version References | Status |
|---|---|---|
| README | No explicit version number (refers to "config.json" not versioned) | N/A |
| CHANGELOG | v1.0.0 (initial release), v1.0.1 (latest release), [Unreleased] | Baseline |
| KNOWN-ISSUES | "Version: 1.0.0" (line 2), "Last Updated: 2026-02-11" (line 3) | **INCONSISTENCY** |
| CHANGELOG link | [Unreleased] compares v1.0.1...HEAD | Correct |
| KNOWN-ISSUES Fixed table | COMPAT-03 "v1.0.1", UX-08 "v1.0.1", COMPAT-11 "v1.0.1" | Correct |

**Finding:**

**KNOWN-ISSUES header says "Version: 1.0.0" but the latest release is v1.0.1.** The KNOWN-ISSUES file was last substantially updated on 2026-02-11 (the same date as v1.0.1), and it references v1.0.1 fixes within its body (COMPAT-03, UX-08, COMPAT-11 all say "Fixed In: v1.0.1"). Yet the header says "Version: 1.0.0."

This likely means the "Version" field in the KNOWN-ISSUES header refers to the initial version the document was created for, not the latest project version. However, this creates ambiguity: a reader could interpret it as "these known issues apply to version 1.0.0" when in fact the document covers issues through v1.0.1.

**Severity: LOW-MEDIUM.** The header version should either be updated to 1.0.1 or clarified (e.g., "Initial Version: 1.0.0" or "Applies to: 1.0.0 -- 1.0.1").

---

### Check 5: Are feature names spelled consistently?

| Term | README | CHANGELOG | KNOWN-ISSUES | Consistent? |
|---|---|---|---|---|
| `--dangerously-skip-permissions` | Lines 3, 7, 138, 146 | Not mentioned | Not mentioned | PASS (only relevant in README) |
| `config.json` | Lines 71, 77, 79, 136 | Line 13: "Renamed...to `config.json`" | Not used by name | PASS |
| `guardian.json` (old name) | Not used | Line 13: "Renamed...from `guardian.json`" | Not used | PASS (correctly absent from README) |
| `/guardian:init` | Line 68 | Line 33 | Not mentioned | PASS |
| `CLAUDE_HOOK_DRY_RUN` | Line 168 | Not mentioned by env var name | Line 100 | PASS |
| `_archive/` | Line 20 | Line 30 | Not mentioned | PASS |
| `.claude/guardian/config.json` | Line 79, 136 | Line 13 (implied by path) | Not mentioned | PASS |
| `bashToolPatterns` | Line 90, 111 | Not mentioned | Not mentioned | PASS |
| `bashPathScan` | Line 118 | Not mentioned | Not mentioned | PASS |
| `zeroAccessPaths` | Line 99, 113 | Not mentioned | Line 83 (as "zeroAccessPaths") | PASS |
| `noDeletePaths` | Line 101, 115 | Not mentioned | Line 81, 83 | PASS |
| `readOnlyPaths` | Line 100, 114 | Not mentioned | Not mentioned | PASS |
| Bash Guardian / Read Guardian / etc. | Lines 128-132 (hook table) | Not named individually | Line 56 (bash_guardian.py) | PASS |
| `--force-with-lease` | Lines 27, 30 | Line 18 | Line 89-91 | PASS |
| Auto-Commit | Line 132 (hook table) | Line 27 ("Auto-commit on session stop") | Not mentioned | PASS (capitalization varies: "Auto-Commit" in table vs "Auto-commit" in CHANGELOG -- minor but table uses title case consistently) |
| `evaluate_rules()` | Not mentioned | Line 14 | Not mentioned | PASS |

**Result: PASS.** Feature names, path names, config keys, and command names are spelled consistently across all three documents. The only variation is "Auto-Commit" (README table, title case) vs. "Auto-commit" (CHANGELOG, sentence case), which is appropriate for their respective contexts (table header vs. prose).

---

### Check 6: Does CHANGELOG "Fixed" list match KNOWN-ISSUES "Fixed Issues" table?

**CHANGELOG v1.0.1 Fixed section (3 items):**
1. shlex.split quote handling on Windows (posix=False quote stripping)
2. --force-with-lease moved from block to ask patterns
3. errno 28 disk full check now handles Windows winerror 112

**KNOWN-ISSUES Fixed Issues table entries attributed to v1.0.1 (3 items):**
1. COMPAT-03: shlex.split Windows quote handling -- Fixed In: v1.0.1
2. UX-08: --force-with-lease blocked instead of ask -- Fixed In: v1.0.1
3. COMPAT-11: errno 28 disk full Linux-only -- Fixed In: v1.0.1

**Cross-reference:**

| CHANGELOG Fixed Item | KNOWN-ISSUES ID | Match? |
|---|---|---|
| shlex.split quote handling on Windows | COMPAT-03 | PASS |
| --force-with-lease moved from block to ask | UX-08 | PASS |
| errno 28 disk full Windows winerror 112 | COMPAT-11 | PASS |

**Result: PASS.** All three v1.0.1 fixes in the CHANGELOG have corresponding entries in the KNOWN-ISSUES Fixed Issues table, and vice versa. No orphaned fixes in either direction.

**Note:** KNOWN-ISSUES also has fixes attributed to "Round 1" and "Round 2" (pre-release internal review rounds) that are not in the CHANGELOG. This is correct -- those were fixes made during development review, not in a versioned release.

---

## Section B: Internal Consistency Within Each Document

### Check 7: README hook count vs. table rows

- README line 124: "Guardian registers **five** hooks with Claude Code:"
- Table rows (lines 128-132): Bash Guardian, Read Guardian, Edit Guardian, Write Guardian, Auto-Commit
- Count: 5 rows

**Verified against hooks.json:** 4 PreToolUse hooks (Bash, Read, Edit, Write) + 1 Stop hook (auto_commit) = 5 total.

**Result: PASS.** The word "five" matches exactly 5 table rows and 5 hooks in the implementation.

---

### Check 8: README "Hard blocks" and "Confirmation prompts" vs. config table

**Hard blocks (README lines 23-27):**
- `rm -rf /`, fork bombs, catastrophic shell commands -- matches `bashToolPatterns.block`
- Reading `.env`, `.pem`, SSH keys, secret files -- matches `zeroAccessPaths`
- Writing to protected paths outside project -- matches path-within-project check + `allowedExternalPaths`
- `git push --force` -- matches block pattern with negative lookahead for `--force-with-lease`

**Confirmation prompts (README lines 29-32):**
- `git push --force-with-lease` -- matches `bashToolPatterns.ask` pattern
- `git reset --hard`, branch deletion -- matches `bashToolPatterns.ask` patterns
- "Other risky-but-sometimes-intentional operations" -- general catch-all for remaining ask patterns

**Config table sections (lines 107-119):**
- `bashToolPatterns.block` = "Regex patterns always blocked" -- aligns with "Hard blocks"
- `bashToolPatterns.ask` = "Regex patterns requiring confirmation" -- aligns with "Confirmation prompts"
- `zeroAccessPaths` = "files that cannot be read or written" -- aligns with Hard blocks bullet on secrets
- `readOnlyPaths` = "read-only files" -- aligns with "Protected files" section
- `noDeletePaths` = "files that cannot be deleted" -- aligns with "Protected files" section

**Result: PASS.** The README's feature descriptions are consistent with what the config table sections imply. Each "Hard block" item maps to either a block pattern or a zero-access/path check; each "Confirmation prompt" maps to an ask pattern.

---

### Check 9: "Does not protect against" vs. "Does protect against"

**Does NOT protect against (lines 150-154):**
1. Determined human adversaries crafting bypass commands
2. Arbitrary code within interpreter scripts (with caveat about known deletion APIs)
3. Operations in separate terminal/process outside Claude Code
4. Its own failure to load

**DOES protect against (lines 156-160):**
1. Accidental file deletion and destructive shell commands
2. Secret file exposure (.env, credentials, private keys)
3. Force pushes and irreversible git operations
4. Loss of work (via auto-commit checkpoints)

**Contradiction check:**
- Item 2 under "Does not" says Guardian cannot catch all interpreter code patterns; Item 1 under "Does" says it protects against "accidental file deletion." These are not contradictory -- "accidental" implies the common case (rm commands), while interpreter scripts are an edge case explicitly called out with a caveat.
- Item 1 under "Does not" says it cannot stop "determined human adversaries"; Item 3 under "Does" says it protects against "force pushes." These are not contradictory -- it blocks the force push command pattern, but a determined adversary could find a workaround.

**Result: PASS.** No contradictions. The "Does not protect" items describe edge cases and inherent limitations; the "Does protect" items describe the common-case protections. The interpreter caveat in item 2 of "Does not" is properly nuanced.

---

### Check 10: CHANGELOG chronological order

- Line 8: `## [Unreleased]` -- most recent (future)
- Line 10: `## [1.0.1] - 2026-02-11` -- second most recent
- Line 21: `## [1.0.0] - 2026-02-11` -- oldest

Both releases share the same date (2026-02-11), but v1.0.1 appears above v1.0.0.

**Result: PASS.** Newest-first ordering is correct per Keep a Changelog convention.

---

### Check 11: KNOWN-ISSUES severity levels appropriate?

| Issue | Assigned Severity | Assessment |
|---|---|---|
| UX-07 (marketplace commands unverified) | MEDIUM | Appropriate -- affects first-time user experience |
| COMPAT-03 (shlex.split Windows) | MEDIUM (strikethrough, FIXED) | Was appropriate; now fixed |
| COMPAT-04 (LC_ALL=C non-MSYS2 Windows) | MEDIUM | Appropriate -- accepted risk, affects Windows subset |
| COMPAT-05 (thread timeout Windows) | MEDIUM | Appropriate -- accepted risk, mitigated |
| COMPAT-06 (normalize_path CWD) | MEDIUM | Appropriate -- latent bug, not currently triggered |
| COMPAT-07 (fnmatch macOS) | MEDIUM | Appropriate -- platform-specific case sensitivity |
| SCOPE-01 (noDeletePaths bash-only) | MEDIUM | **Questionable -- see note below** |
| UX-08 (force-with-lease blocked) | LOW (strikethrough, FIXED) | Was appropriate; now fixed |
| UX-09 (schema common patterns note) | LOW | Appropriate -- cosmetic |
| UX-10 (agent lacks sample output) | LOW | Appropriate -- nice-to-have |
| UX-11 (dry-run mode undocumented) | LOW | Appropriate post-partial-fix -- only missing from wizard |
| UX-12 (init.md quick tips) | LOW | Appropriate -- resolved |
| COMPAT-08 (relative $schema) | LOW | Appropriate -- cosmetic |
| COMPAT-11 (errno 28 Linux-only) | LOW (strikethrough, FIXED) | Was appropriate; now fixed |
| COMPAT-12 (hypothetical marketplace URL) | LOW | Appropriate -- cosmetic |
| COMPAT-13 (recovery guidance platform) | LOW | Appropriate -- minor UX |

**Note on SCOPE-01:** Assigned MEDIUM severity. The issue is that `noDeletePaths` is only enforced for Bash delete commands, not Edit/Write. This is marked "By-design limitation." MEDIUM severity seems appropriate: users may have a false sense of protection, but the attack surface is narrow (an Edit replacing content with empty is a contrived scenario for an AI assistant). If it were HIGH it would imply an urgent fix is needed, which contradicts "by-design." If it were LOW it would understate the user-expectation gap. MEDIUM is the right call.

**Result: PASS.** Severity levels are internally consistent and appropriate to the issues they describe.

---

## Section C: Tone and Style Consistency

### Check 12: Voice and tense

| Document | Voice | Tense | Style |
|---|---|---|---|
| README | Second person ("You keep the speed"), imperative ("Run the setup wizard"), declarative ("Guardian registers five hooks") | Present tense throughout | Conversational but technical; uses "you" freely |
| CHANGELOG | Third person, passive/declarative ("Renamed user config file", "shlex.split quote handling") | Past tense for changes; present tense for descriptions | Terse, bullet-point summaries per Keep a Changelog convention |
| KNOWN-ISSUES | Third person, declarative ("Claude Code expands...", "Hook processes are short-lived") | Present tense for open issues; past tense for fixes | Technical reference style; more formal than README |

**Assessment:** Each document follows its genre conventions:
- README: User-facing guide -- conversational, second person, present tense. Appropriate.
- CHANGELOG: Release notes -- terse, past tense for changes. Follows Keep a Changelog style. Appropriate.
- KNOWN-ISSUES: Technical tracker -- formal, third person, present tense for open items. Appropriate.

**Result: PASS.** The three documents have different voices appropriate to their purposes. They do not clash or create confusion when read together.

---

### Check 13: Formatting conventions

| Convention | README | CHANGELOG | KNOWN-ISSUES | Consistent? |
|---|---|---|---|---|
| Heading levels | H1 title, H2 sections, H3 subsections | H1 title, H2 versions, H3 categories | H1 title, H2 major sections, H3 severity groups, H4 individual issues | PASS -- each uses appropriate hierarchy |
| Bullet style | Hyphens (`-`) throughout | Hyphens (`-`) throughout | Hyphens (`-`) throughout | PASS |
| Code formatting | Backticks for inline code, triple-backtick blocks | Backticks for inline code | Backticks for inline code | PASS |
| Bold text | Used for emphasis (`**fail-closed**`, `**Hard blocks**`) | Used for category headers (`### Changed`, `### Fixed`) | Used for field labels (`**File**:`, `**Issue**:`, `**Status**:`) | PASS |
| Table style | Pipe-delimited markdown tables | No tables | Pipe-delimited markdown tables | PASS |
| Strikethrough | Not used | Not used | Used for FIXED items (`~~COMPAT-03~~`) | PASS -- appropriate for issue tracker |

**Result: PASS.** Formatting conventions are consistent within each document and compatible across documents. Each document uses formatting appropriate to its genre.

---

## Section D: Summary of All Findings

### Issues Found

| # | Check | Finding | Severity | Documents |
|---|---|---|---|---|
| 1 | Check 3 | UX-11 title "Dry-run mode undocumented" is misleading because README now documents it | LOW | KNOWN-ISSUES vs. README |
| 2 | Check 4 | KNOWN-ISSUES header says "Version: 1.0.0" but latest release is v1.0.1 and fixes from v1.0.1 are referenced in the document body | LOW-MEDIUM | KNOWN-ISSUES header vs. CHANGELOG |
| 3 | Check 3 | SCOPE-01 limitation (noDeletePaths bash-only) is not hinted at in README's "No-delete paths" description | LOW | KNOWN-ISSUES vs. README |

### Issues NOT Found (Clean Passes)

- CHANGELOG features all covered in README (Check 1)
- README features appropriately scoped relative to CHANGELOG (Check 2)
- Version numbers consistent within CHANGELOG (Check 4, partial)
- Feature names spelled consistently across all docs (Check 5)
- CHANGELOG Fixed list matches KNOWN-ISSUES Fixed table for v1.0.1 (Check 6)
- Hook count "five" matches table rows and implementation (Check 7)
- Hard blocks and Confirmation prompts match config table (Check 8)
- "Does not protect" does not contradict "Does protect" (Check 9)
- CHANGELOG is newest-first (Check 10)
- Severity levels are appropriate (Check 11)
- Voice/tense appropriate per document genre (Check 12)
- Formatting conventions consistent (Check 13)

---

## Section E: Vibe Check

Reading all three documents as a cohesive set from the perspective of a new user:

1. **Coherent narrative**: The README tells the story (what Guardian is, what it does, how to use it). The CHANGELOG provides release history. KNOWN-ISSUES provides transparency about limitations and open bugs. Together they paint a complete and honest picture.

2. **No jarring contradictions**: Nothing in one document made me distrust another. The minor inconsistencies identified (UX-11 title, version header) are the kind of thing only a careful cross-reference reveals -- a normal user would not encounter confusion.

3. **Appropriate level of detail**: README is detailed but not exhaustive. CHANGELOG is appropriately terse. KNOWN-ISSUES is appropriately thorough for a technical tracker. No document over-promises or under-delivers relative to the others.

4. **Trust signals**: The explicit "Does not protect against" section in the README, combined with the honest KNOWN-ISSUES tracker, creates a trustworthy impression. The project does not overclaim.

5. **One thing that could confuse**: A user who reads README's "No-delete paths for critical project files" and then discovers that an Edit tool call can empty a "protected" file might feel misled. The KNOWN-ISSUES SCOPE-01 entry documents this, but users rarely read known issues proactively. This is the single most meaningful tension across the document set, and it is LOW severity because the scenario is unlikely (Claude Code would not typically empty a file via Edit to circumvent deletion protection).

6. **Version header staleness**: The KNOWN-ISSUES "Version: 1.0.0" header is the most likely item to cause real confusion for a contributor or triager looking at the document header to understand its currency. This is the most actionable fix identified.

---

## Overall Assessment

**RESULT: PASS -- All three documents are internally consistent with each other.**

Three minor findings were identified, none of which rise to the level of a blocking inconsistency:

1. **UX-11 title staleness (LOW):** Previously flagged in both Round 1 reports. The status line is accurate; only the title slightly overstates the issue post-fix.

2. **KNOWN-ISSUES version header (LOW-MEDIUM):** The header says "Version: 1.0.0" but the document tracks issues through v1.0.1. Recommend updating to "Version: 1.0.1" or "Versions covered: 1.0.0 -- 1.0.1."

3. **SCOPE-01 vs. README no-delete description (LOW):** A design-level tension between README's feature description and KNOWN-ISSUES' limitation disclosure. Acceptable as-is; README describes intent, KNOWN-ISSUES describes boundary.

**Confidence level: HIGH.** Every cross-reference between the three documents was checked systematically. No blocking inconsistencies exist. The documents can be published as a coherent set.

### Recommended Fixes (Optional, Non-Blocking)

1. Update KNOWN-ISSUES line 2 from `## Version: 1.0.0` to `## Version: 1.0.1`
2. Update KNOWN-ISSUES UX-11 title from "Dry-run mode undocumented" to "Dry-run mode not in setup wizard"
3. No change needed for SCOPE-01/README tension -- the current split of concerns (README = intent, KNOWN-ISSUES = implementation boundary) is appropriate.
