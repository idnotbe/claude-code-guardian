# Team C: Documentation Polisher -- Fix Summary

## Date: 2026-02-14

---

## Changes Made

### README.md (6 fixes applied)

#### Fix 1: Shell profile persistence example
- **Location**: Installation > Manual Installation section (line ~52)
- **Change**: Replaced vague "add it to your shell profile or Claude Code settings" with a concrete bash alias example showing `~/.bashrc` or `~/.zshrc` configuration.
- **Source**: Verification-round2-userperspective.md Priority 1, item 1

#### Fix 2: Marketplace commands clarification
- **Location**: Installation > From Marketplace section (lines ~60-74)
- **Change**:
  - Changed "experimental" warning to explicitly state "**Unverified**" and that commands have not been tested against a live CLI
  - Added explanatory text that the two commands are "alternative syntaxes"
  - Added inline comments labeling each as "Alternative A" and "Alternative B"
  - Added cross-reference to UX-07 in KNOWN-ISSUES.md
- **Source**: Verification-round2-userperspective.md Priority 1, item 2

#### Fix 3: Troubleshooting section
- **Location**: New subsection under Failure Modes, before Disabling Guardian (lines ~181-195)
- **Change**: Added complete Troubleshooting subsection containing:
  - Log file location (`.claude/guardian/guardian.log`)
  - How to check if hooks are loaded (test with `.env` read)
  - Common issues table with 5 rows: hooks not firing, python3 not found, config not loading, auto-commits stopped, unexpected blocks
- **Source**: Verification-round2-userperspective.md Priority 1, item 3; gap-challenge.md recommendation

#### Fix 4: hookBehavior.timeoutSeconds in config table
- **Location**: Configuration Sections table, `hookBehavior` row (line ~125)
- **Change**: Expanded description from "What to do on timeout or error (allow/deny/ask)" to include ", and `timeoutSeconds` for hook execution limit"
- **Source**: Verification-round2-userperspective.md Priority 2, item 7; verification-round2-consistency.md Check 3

#### Fix 5: Python 3.10+ requirement surfaced in Installation
- **Location**: Manual Installation section, before the clone command (line ~45)
- **Change**: Added prominent callout: "> **Requires Python 3.10+** and Git. Verify with `python3 --version` before installing."
- **Source**: Verification-round2-userperspective.md Priority 1, item 5

#### Fix 6: Dry-run mode discoverability
- **Location**: Setup section, after the skip-setup note (line ~88)
- **Change**: Added tip with cross-reference: "> **Tip**: To test your configuration without blocking operations, use dry-run mode: `CLAUDE_HOOK_DRY_RUN=1`. See [Disabling Guardian](#disabling-guardian) for details."
- **Also**: Enhanced Disabling Guardian section with a concrete command example showing `CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir ...` and added sentence about usefulness for debugging.
- **Source**: Verification-round2-userperspective.md Priority 2, item 6

### KNOWN-ISSUES.md (4 fixes applied)

#### Fix 7: UX-11 title update
- **Location**: UX-11 entry (line ~103)
- **Change**: Changed title from "Dry-run mode undocumented" to "Dry-run mode not mentioned in setup wizard". Updated issue description and status to reflect that README now documents dry-run, with remaining gap being the setup wizard.
- **Source**: Verification-round2-consistency.md finding 1; verification-round2-userperspective.md

#### Fix 8: Fleshed out terse entries
- **UX-09** (line ~93): Added **File** field (`assets/guardian.schema.json`), expanded issue description to explain what "noting they are pre-included" means, and added concrete fix recommendation with suggested wording.
- **UX-10** (line ~98): Added **File** field (`.claude-plugin/agents/config-assistant.md`), expanded issue to explain that trigger examples lack response previews, and added concrete fix recommendation.
- **COMPAT-12** (line ~117): Added **File** field (`.claude-plugin/marketplace.json`), expanded to explain the hypothetical URL issue and IDE validation impact, and clarified the cosmetic-only status.
- **Source**: Verification-round2-userperspective.md item 12; gap-challenge.md

#### Fix 9: UX-12 consistency
- **Location**: UX-12 entry (line ~107) and Fixed Issues table (line ~147)
- **Change**: Applied strikethrough formatting (`~~UX-12: ...~~ FIXED`) to match the convention used by other fixed items (COMPAT-03, UX-08, COMPAT-11). Added "(Round 2)" to the status line. Added UX-12 row to the Fixed Issues reference table at the bottom.
- **Source**: Verification-round2-consistency.md observation on formatting consistency

### CHANGELOG.md (1 fix applied)

#### Fix 10: Populated [Unreleased] section
- **Location**: [Unreleased] section (lines ~8-25)
- **Change**: Added entries under `### Changed` covering:
  - Code fixes: COMPAT-06, COMPAT-07, COMPAT-08, COMPAT-13
  - Documentation improvements: All 6 README changes and all 3 KNOWN-ISSUES changes
- **Note**: Initially used `### Improved` category but corrected to `### Changed` to comply with Keep a Changelog standard categories.
- **Source**: Task specification item 10

---

## Verification Checklist

| Fix | Document | Verified |
|-----|----------|----------|
| 1. Shell profile persistence example | README.md | Yes -- concrete alias shown |
| 2. Marketplace commands clarified | README.md | Yes -- marked unverified, alternatives explained |
| 3. Troubleshooting section added | README.md | Yes -- log location, hook check, common issues table |
| 4. hookBehavior.timeoutSeconds added | README.md | Yes -- config table updated |
| 5. Python 3.10+ in Installation | README.md | Yes -- prominent callout before clone command |
| 6. Dry-run cross-reference | README.md | Yes -- tip in Setup, example in Disabling section |
| 7. UX-11 title updated | KNOWN-ISSUES.md | Yes -- reflects current state |
| 8. Terse entries fleshed out | KNOWN-ISSUES.md | Yes -- UX-09, UX-10, COMPAT-08, COMPAT-12, COMPAT-13 all expanded |
| 9. UX-12 marked fixed consistently | KNOWN-ISSUES.md | Yes -- strikethrough + added to Fixed table |
| 10. [Unreleased] populated | CHANGELOG.md | Yes -- code and doc changes listed |

---

## Items NOT Changed (with rationale)

- **KNOWN-ISSUES version header**: Already at 1.0.1 (was updated in a prior round, per the file content read at start).
- **SCOPE-01 vs README no-delete description**: Per the consistency report, this is an acceptable tension -- README describes intent, KNOWN-ISSUES describes enforcement boundary. No change needed.
- **Multi-layer architecture in README**: Per gap-challenge.md, this is an implementation detail not suitable for user-facing docs.
- **Circuit breaker internals**: Already documented in Failure Modes section. Additional detail added to Troubleshooting table.
- **Pattern counts**: These appear in review reports, not in the published docs. No doc change needed.

---

## Files Modified

1. `/home/idnotbe/projects/claude-code-guardian/README.md` -- 6 edits
2. `/home/idnotbe/projects/claude-code-guardian/KNOWN-ISSUES.md` -- 7 edits (5 original + COMPAT-08 and COMPAT-13 expansions)
3. `/home/idnotbe/projects/claude-code-guardian/CHANGELOG.md` -- 2 edits (initial + correction)
4. `/home/idnotbe/projects/claude-code-guardian/temp/fix-all-issues/team-c-fixes.md` -- this summary (created new)
