# Verification Round 2: User Perspective Review

**Reviewer**: Teammate J (New User Perspective)
**Date**: 2026-02-15
**Files Reviewed**: README.md, KNOWN-ISSUES.md, CHANGELOG.md
**Approach**: Reading as a first-time user with no prior project knowledge

---

## Executive Summary

**Overall Assessment**: MOSTLY PASS with 3 FLAGS and 5 NOTES

The documentation is generally clear and well-structured for new users. The user journey is logical (install → setup → configure → troubleshoot). Most potential confusion points are adequately addressed. However, there are three areas requiring fixes and several opportunities for improvement.

**Critical Findings**:
- FLAG: Missing hook count in "How It Works" table (claims 5, shows 5, but heading contradicts itself)
- FLAG: Jargon introduced without adequate explanation in multiple sections
- FLAG: Promise vs reality mismatch (force-with-lease placement is CORRECT, but description could be clearer)

---

## Section-by-Section Walkthrough

### 1. README.md: Top Matter (Lines 1-14)

**Section**: Title, tagline, "Why Guardian?"

#### PASS: Value Proposition
- The "Why Guardian?" section immediately answers "What problem does this solve?"
- The trade-off is clear: speed vs safety
- The 99%/1% framing is memorable and accurate

#### NOTE: Tagline Accessibility
- Line 3: "Selective security guardrails for Claude Code's `--dangerously-skip-permissions` mode."
- For a brand-new user who hasn't used Claude Code yet, this assumes they know what `--dangerously-skip-permissions` is
- **Suggestion**: Add a brief parenthetical like "...`--dangerously-skip-permissions` mode (which bypasses all approval prompts for speed)"

---

### 2. README.md: What It Catches (Lines 15-40)

**Section**: Feature overview with 4 categories

#### PASS: Force-with-lease Placement ✓
- Line 30: `git push --force-with-lease` is correctly under "Confirmation prompts"
- This matches the requirement (NOT under "Hard blocks")

#### FLAG: Category Naming Could Be Clearer
- **Issue**: "Safety checkpoints (automatic)" suggests these are things that happen automatically in the background. But the other categories are about blocking/asking.
- The asymmetry might confuse users: "Are checkpoints a type of block? Do they require my input?"
- **Suggestion**: Rename to "Automatic Safety Features" or "Background Protection" to clarify these are passive safeguards, not intervention points

#### NOTE: Protected Files Redundancy
- Lines 34-37: "Protected files (access controls)" lists zero-access, read-only, and no-delete paths
- These are already mentioned in "Hard blocks" (line 25-26)
- **Suggestion**: Either consolidate or clarify the distinction. Right now it reads like "we block .env files" (line 25) AND "we have zero-access paths for secrets" (line 35) without explaining these are the same mechanism.

#### PASS: Windows Coverage
- Line 39: "Default patterns cover both Unix and Windows commands" - good explicit reassurance

---

### 3. README.md: Installation (Lines 41-75)

**Section**: Manual installation and marketplace alternatives

#### PASS: Prerequisites Clarity ✓
- Line 45: Python 3.10+ requirement is surfaced BEFORE the install command
- Includes verification command: `python3 --version`
- Git requirement mentioned (though could be more prominent)

#### PASS: Persistence Warning ✓
- Lines 52-56: Shell profile alias example is excellent
- Directly addresses the "it worked once but now it's gone" problem

#### PASS: Marketplace Transparency ✓
- Line 62: "Unverified" label is prominent
- Line 62-63: Explicitly states manual installation is the reliable path
- Alternative syntaxes are provided without overpromising

#### FLAG: Git Requirement Buried
- Git is mentioned in line 45 ("Requires Python 3.10+ and Git") but there's no verification command like there is for Python
- A new user might think "I have git" but not realize they need it configured with user.name/user.email for auto-commits
- **Suggestion**: Add a verification line:
  ```
  Verify with `python3 --version` and `git --version` before installing.
  ```

---

### 4. README.md: Setup (Lines 76-89)

**Section**: Post-installation configuration

#### PASS: Next Step Obvious ✓
- Line 78: The `/guardian:init` command is the first thing after installation
- Clear description of what it does ("generates a config.json")

#### PASS: Optional Setup Explained
- Lines 86-87: Explicitly states you can skip setup and use defaults
- Lists what the defaults protect

#### PASS: Dry-run Discoverability ✓
- Line 88: Dry-run mode is mentioned early with a forward reference to the Disabling section
- This is excellent progressive disclosure

#### NOTE: "Sensible defaults" vs "Built-in defaults"
- Line 84: "sensible defaults"
- Line 86: "built-in defaults"
- Are these the same thing? If yes, use consistent terminology. If no, explain the difference.

---

### 5. README.md: Configuration (Lines 90-136)

**Section**: config.json structure and resolution

#### FLAG: Jargon Without Explanation
- Line 101: "Your config must also include `version` and `hookBehavior` (both required by the schema)"
- **Problem**: "hookBehavior" is introduced here without any context about what it is
- The configuration table (lines 120-134) explains it later, but a first-time reader at line 101 has no idea what "hookBehavior" controls
- **Suggestion**: Either remove the parenthetical from line 101 (the user will see the full config anyway), or add a brief inline explanation: "`hookBehavior` (timeout/error handling)"

#### FLAG: "scanTiers" Not Explained
- Line 133: "bashPathScan | Raw command string scanning for protected path names"
- The table mentions this section exists but doesn't explain what it does or why you'd use it
- In CHANGELOG.md line 14, we see "`scanTiers` now implemented" which suggests this is a recent feature
- A new user has no context for what "scan tiers" means
- **Suggestion**: Expand the table row to something like: "bashPathScan | Scans bash commands for references to protected paths (e.g., blocks `python3 script.py --file .env` even if the pattern doesn't match). Supports `scanTiers` for granular control."

#### PASS: Schema Reference
- Line 135: "See `assets/guardian.schema.json` for the full schema" - good pointer to authoritative source

#### PASS: Resolution Order Clear
- Lines 92-97: The 1-2-3 fallback chain is explicit
- Emergency fallback is mentioned (though not detailed)

---

### 6. README.md: How It Works (Lines 137-158)

**Section**: Hook registration table and fail-closed explanation

#### PASS: Five Hooks Table ✓
- Line 139: "Guardian registers five hooks with Claude Code:"
- Table has exactly 5 rows:
  1. Bash Guardian
  2. Read Guardian
  3. Edit Guardian
  4. Write Guardian
  5. Auto-Commit
- **Verification**: Count matches claim ✓

#### PASS: Fail-Closed Explanation
- Lines 149-150: Clear explanation of the fail-closed philosophy
- The "annoying vs catastrophic" framing is user-friendly

#### NOTE: Hook Event Names Unexplained
- Line 142: "PreToolUse: Bash", "PreToolUse: Read", etc.
- A new user doesn't know what "PreToolUse" means in Claude Code's architecture
- **Suggestion**: Add a brief note like "PreToolUse hooks intercept operations before execution" (one sentence is enough)

#### PASS: Self-Protection Mentioned
- Line 151: Guardian protects its own config from modification
- This is a good trust signal

#### FLAG: Verification Guidance Assumes Knowledge
- Line 153: "Verify hooks are loaded at the start of your session by attempting to read a `.env` file"
- **Problem**: A new user might not HAVE a .env file to test with
- **Suggestion**: Provide a complete test command:
  ```
  Create a test file: `echo "SECRET=test" > .env`
  Try to read it: Ask Claude to read .env
  Expected result: Guardian should block the operation
  ```

---

### 7. README.md: Failure Modes (Lines 159-195)

**Section**: Limitations and troubleshooting

#### PASS: Honest Limitations
- Lines 165-169: Clear list of what Guardian does NOT protect against
- Lines 171-175: Clear list of what it DOES protect against
- Line 177: "alongside...not instead of" is excellent framing

#### PASS: Troubleshooting Table ✓
- Lines 187-195: All 5 problems have actionable solutions
- The "Verify path" solution includes the exact command to run
- The dry-run solution includes the exact environment variable

#### PASS: Log File Location
- Line 183: `.claude/guardian/guardian.log` with explicit path context ("inside your project directory")

#### NOTE: Circuit Breaker Detail Level
- Lines 179-180: Circuit breaker is mentioned but the user hasn't seen auto-commits explained yet (they're listed in "What It Catches" but not detailed)
- **Suggestion**: Add a forward reference to the auto-commit feature where circuit breaker is first mentioned

---

### 8. README.md: Disabling Guardian (Lines 196-206)

**Section**: Dry-run mode and uninstallation

#### PASS: Dry-run Command Copy-Pasteable ✓
- Line 202: `CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/claude-code-guardian`
- This is a complete, working command (user just needs to substitute the path)

#### PASS: Uninstall Steps Clear
- Line 205: Three clear steps (remove flag, delete repo, remove .claude/guardian/)

---

### 9. README.md: Testing (Lines 207-222)

**Section**: Test suite documentation

#### PASS: Test Examples Provided
- Lines 211-217: Two concrete examples (pytest and direct python)
- Forward reference to tests/README.md for details

#### PASS: Coverage Gaps Acknowledged
- Lines 221-222: Explicitly lists untested scripts
- Refers to TEST-PLAN.md for action plan

---

### 10. README.md: Requirements (Lines 223-227)

**Section**: Prerequisites

#### NOTE: Redundant Section
- This repeats line 45 (already stated in Installation)
- **Suggestion**: Either remove this section entirely, or expand it to include system requirements (disk space, OS versions, etc.)

---

## Cross-Document Checks

### Contradictions: README vs KNOWN-ISSUES

#### CHECK: Force-with-lease
- README line 30: "Confirmation prompts" ✓
- KNOWN-ISSUES line 88-90: "UX-08: Default blocks --force-with-lease" marked as FIXED
- **Result**: PASS - No contradiction (issue was fixed)

#### CHECK: Marketplace Commands
- README lines 62-72: Marked as "Unverified"
- KNOWN-ISSUES lines 49-53: "UX-07: README marketplace install commands unverified"
- **Result**: PASS - Consistent disclosure

#### CHECK: Dry-run Mode
- README lines 88, 199-202: Dry-run mode documented
- KNOWN-ISSUES lines 102-104: "UX-11: Dry-run mode not mentioned in setup wizard"
- **Result**: PASS - README correctly documents it; known issue is about the wizard, not README

### Dead Links Check

#### Internal Links
- Line 74: `[UX-07 in KNOWN-ISSUES.md](KNOWN-ISSUES.md)` ✓ (file exists, reference valid)
- Line 88: Reference to [Disabling Guardian](#disabling-guardian) ✓ (section exists at line 197)
- Line 153: Reference to [Failure Modes](#failure-modes) ✓ (section exists at line 159)

#### External Links
- Line 48: `https://github.com/idnotbe/claude-code-guardian` (not verified in this review)

**Result**: PASS - All internal links valid

---

## KNOWN-ISSUES.md Review

### Structure Check

#### PASS: Versioning Clear
- Lines 3-5: Version, date, and review status at the top
- This is excellent context for users wondering how current the doc is

#### PASS: Platform Verification Section
- Lines 9-42: The 5 PV items are clearly marked as pre-release assumptions
- Each has: assumption, location, consequence if wrong, and test method
- This is transparent and builds trust

#### PASS: Issue Categorization
- Issues are grouped by severity (MEDIUM, LOW)
- Fixed issues are strikethrough
- Fixed issues table (lines 130-154) provides audit trail

### Specific Items Check

#### FLAG: UX-09 Missing File Path
- Line 92-96: UX-09 mentions the schema but doesn't give the exact line number
- Compare to UX-10 (line 97) which DOES specify the file
- **Suggestion**: Add line number or section reference for consistency

#### NOTE: Fixed Issue Formatting Inconsistency
- Line 58: `~~COMPAT-03: shlex.split quote handling on Windows~~ FIXED`
- Line 70: `~~COMPAT-06: normalize_path resolves against CWD~~ FIXED`
- Some issues use strikethrough + FIXED suffix, others just strikethrough
- **Suggestion**: Pick one format and use it consistently

---

## CHANGELOG.md Review

### Structure Check

#### PASS: Keep a Changelog Format
- Lines 5-6: Explicitly states adherence to standards
- This is good for users familiar with changelog conventions

#### PASS: Unreleased Section
- Lines 8-34: Clear separation of unreleased vs released changes
- Changes are categorized: Added, Changed, Fixed

#### PASS: Version Links
- Lines 60-62: Links to GitHub compare views
- This is helpful for users who want to see exact diffs

### Content Check

#### PASS: User-Facing Changes Highlighted
- Line 21-26: README improvements are called out
- These are the changes most users will encounter first

#### NOTE: Technical Jargon in Changelog
- Line 11: "hookBehavior.onTimeout and hookBehavior.onError now used at runtime"
- This is fine for a changelog (audience is more technical)
- But for a NEW USER reading the changelog to understand what's new, this is opaque without README context

---

## User Journey Simulation

### Journey 1: "I want to install this"

**Steps a user would take**:
1. Read README.md title and "Why Guardian?" → **Clear motivation** ✓
2. Scan "What It Catches" → **Clear capabilities** ✓
3. Jump to Installation → **Prerequisites listed** ✓ (FLAG: Git verification missing)
4. Copy install command → **Copy-pasteable** ✓
5. Run setup wizard → **Next step obvious** ✓

**Result**: MOSTLY PASS (would succeed, minor confusion on Git check)

---

### Journey 2: "I want to configure it for my project"

**Steps a user would take**:
1. Run `/guardian:init` (from README line 78)
2. Want to customize → read Configuration section
3. See example config → **Clear structure** ✓
4. Check table for what each field does → FLAG: "hookBehavior" and "scanTiers" not adequately explained
5. Look at `assets/guardian.default.json` for full config → **Reference provided** ✓

**Result**: PASS with NOTES (would succeed but need to read schema for full understanding)

---

### Journey 3: "Something's not working"

**Steps a user would take**:
1. Check if hooks are loaded → Line 185 says "try to read a .env file"
2. FLAG: User might not have a .env file → confusion
3. Check log file → **Location clearly stated** ✓
4. Look at troubleshooting table → **Actionable solutions** ✓
5. Check KNOWN-ISSUES.md for their specific problem → **Well organized** ✓

**Result**: MOSTLY PASS (would likely succeed)

---

### Journey 4: "I want to uninstall this"

**Steps a user would take**:
1. Search README for "uninstall" or "disable"
2. Find "Disabling Guardian" section → **Clear heading** ✓
3. Read steps → **Three clear actions** ✓
4. Execute → **Would succeed** ✓

**Result**: PASS

---

## Specific Verification Checklist

### ✓ Force-with-lease Placement
- **Requirement**: Should be under "Confirmation prompts", NOT "Hard blocks"
- **Finding**: Line 30 - Correctly placed under "Confirmation prompts"
- **Status**: PASS

### ✓ Five Hooks Table
- **Requirement**: Should list exactly 5 hooks
- **Finding**: Lines 141-147 - Exactly 5 rows (Bash, Read, Edit, Write, Auto-Commit)
- **Status**: PASS

### ✓ Troubleshooting Table Actionable
- **Requirement**: Should have actionable solutions
- **Finding**: All 5 problems have specific solutions (verify path, install Python, validate JSON, delete circuit file, use dry-run)
- **Status**: PASS

### ✓ Dry-run Command Copy-Pasteable
- **Requirement**: Should be a complete command
- **Finding**: Line 202 - `CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/claude-code-guardian`
- **Status**: PASS (user just needs to substitute path)

### ✓ Marketplace Installation Marked Unverified
- **Requirement**: Should be clearly marked as unverified
- **Finding**: Line 62 - "Unverified" in bold with explicit warning
- **Status**: PASS

---

## Recommendations Summary

### Must Fix (FLAGS)

1. **README line 45**: Add Git verification command
   - Current: "Requires Python 3.10+ and Git. Verify with `python3 --version` before installing."
   - Suggested: "Requires Python 3.10+ and Git. Verify with `python3 --version` and `git --version` before installing."

2. **README line 101**: Remove or explain "hookBehavior" jargon
   - Current: "Your config must also include `version` and `hookBehavior` (both required by the schema)."
   - Suggested: "Your config must also include `version` and `hookBehavior` (timeout/error handling settings required by the schema)."

3. **README line 133**: Explain "bashPathScan" and "scanTiers"
   - Current: "bashPathScan | Raw command string scanning for protected path names"
   - Suggested: "bashPathScan | Scans bash commands for references to protected paths (e.g., blocks `python3 script.py --file .env`). Supports `scanTiers` for granular control of which path types to scan for."

4. **README line 153**: Provide complete verification test
   - Current: "Verify hooks are loaded at the start of your session by attempting to read a `.env` file"
   - Suggested: Add example: "Create a test file (`echo "TEST=1" > .env`), then ask Claude to read it. Guardian should block the operation."

5. **KNOWN-ISSUES line 93**: Add file path to UX-09
   - Add: "**File**: assets/guardian.schema.json (common patterns table)"

### Should Consider (NOTES)

6. **README line 3**: Add parenthetical for `--dangerously-skip-permissions`
   - Helps brand-new Claude Code users understand the context

7. **README line 17**: Rename "Safety checkpoints (automatic)" to "Automatic Safety Features"
   - Clearer distinction from intervention categories

8. **README line 34-37**: Consolidate or clarify "Protected files" vs "Hard blocks"
   - Avoid appearing to list the same feature twice

9. **README line 84 vs 86**: Use consistent terminology for "defaults"
   - Pick either "sensible defaults" or "built-in defaults"

10. **README line 142**: Add one-sentence explanation of "PreToolUse"
    - "PreToolUse hooks intercept operations before execution"

11. **README lines 223-227**: Either remove redundant Requirements section or expand it
    - Already stated in Installation section

12. **KNOWN-ISSUES**: Use consistent strikethrough format for fixed issues
    - Some use `~~text~~ FIXED`, others just `~~text~~`

---

## Overall User Experience Rating

**Installation**: 8/10 (clear, copy-pasteable, one missing Git verification)
**Setup**: 9/10 (obvious next step, dry-run mentioned early)
**Configuration**: 7/10 (structure clear, some jargon unexplained)
**Understanding Features**: 8/10 (good categorization, minor redundancy)
**Troubleshooting**: 8/10 (log location clear, solutions actionable, one weak test instruction)
**Uninstallation**: 10/10 (perfect clarity)

**Overall**: 8.3/10 - Solid documentation with good user journey, minor improvements needed for jargon and completeness.

---

## Final Verdict

**MOSTLY PASS** - The documentation successfully guides a new user through installation, setup, configuration, and troubleshooting. The user journey is logical and well-structured. The 5 must-fix items are minor clarity improvements that would prevent confusion for users unfamiliar with the project's internal terminology.

The verification requirements are all met:
- ✓ Force-with-lease correctly placed
- ✓ Five hooks table accurate
- ✓ Troubleshooting actionable
- ✓ Dry-run command copy-pasteable
- ✓ Marketplace clearly marked unverified

**Recommendation**: Fix the 5 flagged items before release. The notes are nice-to-have improvements but not blockers.
