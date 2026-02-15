# Team B Fixes Report

## Fix 1: Fixed Issues Table Detail (KNOWN-ISSUES.md)

**Status**: Applied

**What was changed**: All 21 rows in the Fixed Issues reference table at the bottom of KNOWN-ISSUES.md were reviewed. Terse descriptions were expanded to be self-contained and meaningful without requiring the reader to look up the full body entry.

**Key improvements**:
| ID | Before | After |
|----|--------|-------|
| F-01 | "bash_guardian.py fail-open on crash" | "bash_guardian.py failed open on unhandled crash, allowing commands through without checks" |
| F-02 | "Oversized command bypass (padding attack)" | "Oversized command could bypass pattern matching via padding attack" |
| CRITICAL-01 | "README documented non-existent config step" | "README documented a configuration step that did not exist in the codebase" |
| MEDIUM-03 | ".gitignore wrong log filename" | ".gitignore referenced wrong log filename, leaving actual logs unignored" |
| COMPAT-01 | "plugin.json missing skills/agents" | "plugin.json missing skills and agents declarations, preventing discovery" |
| COMPAT-02 | "python vs python3 in hooks.json" | "hooks.json used `python` instead of `python3`, failing on Linux/WSL systems" |
| UX-01 | "SKILL.md vague config paths" | "SKILL.md referenced vague config paths that did not match actual file locations" |
| UX-03 | "No skip-init guidance" | "No guidance for skipping /guardian:init wizard when manually configuring" |
| UX-04 | "Inconsistent fail-closed terminology" | "Inconsistent fail-closed terminology across documentation and code comments" |
| UX-05 | "No fallback for unrecognized projects" | "No fallback behavior defined for unrecognized project types in init wizard" |
| UX-06 | "Legacy path check in init wizard" | "Init wizard checked for legacy config path that no longer existed" |
| UX-12 | "init.md quick tips depend on skill/agent" | "init.md quick tips referenced skill/agent before they were registered in plugin.json" |
| COMPAT-06 | "normalize_path resolves against CWD" | "normalize_path() resolved relative paths against CWD instead of project directory" |
| COMPAT-07 | "fnmatch case sensitivity on macOS" | "fnmatch case sensitivity incorrect on macOS HFS+ (case-insensitive filesystem)" |
| COMPAT-08 | "Relative $schema in default config" | "Relative `$schema` path in default config broke when config copied to project" |
| COMPAT-13 | "Recovery guidance uses del on all platforms" | "Circuit breaker recovery guidance suggested Windows `del` command on all platforms" |

Entries that were already clear (COMPAT-03, COMPAT-11, UX-08, HIGH-01, MEDIUM-02) received minor wording polish for consistency but were not significantly rewritten.

---

## Fix 5: Add SCOPE-02 to KNOWN-ISSUES and CHANGELOG

**Status**: Applied

**KNOWN-ISSUES.md changes**:
- Added SCOPE-02 entry under MEDIUM Severity, immediately after SCOPE-01 (line 86)
- Entry documents `hookBehavior.timeoutSeconds` as a by-design limitation
- Includes File, Issue, Impact, and Status fields matching the existing SCOPE-01 format
- Status explains the design rationale: SIGALRM risks, partial file copies, Windows threading

**CHANGELOG.md changes**:
- Added line to [Unreleased] Changed section:
  `- KNOWN-ISSUES: Added SCOPE-02 documenting hookBehavior.timeoutSeconds as a by-design limitation`
- Placed after the existing KNOWN-ISSUES changelog entries for logical grouping

---

## Files Modified
- `/home/idnotbe/projects/claude-code-guardian/KNOWN-ISSUES.md` (Fix 1 + Fix 5)
- `/home/idnotbe/projects/claude-code-guardian/CHANGELOG.md` (Fix 5)

## Verification
- Re-read SCOPE-02 in context with SCOPE-01: both follow identical structure (File, Issue, Impact, Status)
- Re-read Fixed Issues table: all 21 entries now have self-contained descriptions
- Re-read CHANGELOG [Unreleased] Changed section: SCOPE-02 entry fits naturally with other KNOWN-ISSUES entries
