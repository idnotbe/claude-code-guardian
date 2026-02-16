# Documentation Changes Log

## Date: 2026-02-16
## Author: doc-writer teammate

---

## Files Modified

### 1. README.md (root) -- Complete Rewrite

**Before**: ~232 lines covering basics of installation, setup, configuration, how it works, failure modes, troubleshooting, testing, requirements.

**After**: ~868 lines with comprehensive coverage. Changes include:

#### New Sections Added
- **Table of Contents** with deep links to all sections
- **Quick Start** section with numbered steps
- **Configuration Reference** -- complete reference for ALL config options including:
  - `bashPathScan` with all 4 sub-options (was barely mentioned before)
  - `gitIntegration` with all sub-sections (`autoCommit`, `preCommitOnDangerous`, `identity`)
  - `allowedExternalReadPaths` and `allowedExternalWritePaths` with usage examples
  - `hookBehavior` with SCOPE-02 limitation note about `timeoutSeconds`
  - `noDeletePaths` with SCOPE-01 limitation caveat
- **Glob Pattern Syntax** reference section
- **Writing Regex Patterns** section with JSON escaping guidance
- **Architecture** section with hook table, JSON protocol, and fail-mode info
- **Bash Guardian (Multi-Layer Defense)** explaining all 5 layers
- **Path Guardian (Read/Edit/Write)** with check-order matrix
- **Auto-Commit** section with skip conditions and pre-danger checkpoints
- **Archive-Before-Delete** section with limits, naming convention, recovery procedures
- **Self-Guarding** section explaining config protection mechanism
- **Circuit Breaker** section with reset instructions
- **Security Model** section with "protects against" / "does NOT protect against" / "design principles"
- **User Guide** section with subsections:
  - Understanding Default Protection (default pattern summary)
  - Customizing Command Patterns (with examples)
  - Customizing Path Restrictions (with pitfalls)
  - Configuring Auto-Commit (with security warning)
  - Working with Multiple Projects
  - Understanding Block Messages (message-meaning-resolution table)
- **Troubleshooting** section expanded with log levels and more common issues
- **Upgrading** section with update procedure
- **FAQ** section with 10 common questions
- **Environment Variables** reference table
- **Optional `regex` package** installation note for ReDoS protection

#### Gaps Filled (from doc-analysis P0/P1/P2)
- P0: `bashPathScan` fully documented with all 4 sub-options
- P0: SCOPE-01 caveat added to `noDeletePaths` docs
- P1: Archive-before-delete fully documented with limits, naming, recovery
- P1: Self-guarding behavior documented
- P1: Block message reference table added
- P2: Architecture overview (layered checking, script interactions)
- P2: Implementation limits documented (command size 100KB, log rotation 1MB)
- P2: Human-readable summary of default config patterns
- P2: Environment variables documented
- P2: Config validation mentioned
- P2: Fallback config content listed

### 2. CLAUDE.md -- Internal Contradiction Fixed, Coverage Table Updated

**Changes**:
- Fixed internal contradiction: Coverage table previously said edit/read/write_guardian.py had "None" test coverage while the text said they were "now tested via subprocess integration". Updated table to say "Basic (subprocess integration in `tests/security/test_p0p1_failclosed.py`)"
- Updated `_guardian_utils.py` coverage description to mention path guardian paths covered by subprocess tests
- Updated Known Security Gap #2 description for consistency

### 3. skills/config-guide/references/schema-reference.md -- bashPathScan Added, Caveats Added

**Changes**:
- Added `bashPathScan` to Top-Level Structure example
- Added complete `bashPathScan` section with all 4 fields, types, defaults, values, descriptions, example JSON, and guidance notes
- Added SCOPE-01 limitation note to `noDeletePaths` description
- Added `timeoutSeconds` limitation note to `hookBehavior` guidance
- Fixed case-sensitivity note: changed "case-sensitive on Linux/macOS" to "case-sensitive on Linux, case-insensitive on Windows and macOS" (matches COMPAT-07 fix)
- Added note to Regex Pattern Cookbook that many patterns are already in default config (addresses UX-09)

### 4. temp/04-doc-changes.md -- This File

Created to log all documentation changes.

---

## Gap Analysis Coverage

### P0 Gaps Addressed
| Gap | Status | Where |
|-----|--------|-------|
| Document bashPathScan fully | DONE | README.md Configuration Reference, schema-reference.md |
| Add SCOPE-01 caveat to noDeletePaths | DONE | README.md, schema-reference.md |

### P1 Gaps Addressed
| Gap | Status | Where |
|-----|--------|-------|
| Document archive-before-delete | DONE | README.md Archive-Before-Delete section |
| Add block message reference | DONE | README.md Understanding Block Messages |
| Document self-guarding behavior | DONE | README.md Self-Guarding section |

### P2 Gaps Addressed
| Gap | Status | Where |
|-----|--------|-------|
| Architecture overview | DONE | README.md How It Works section |
| Implementation limits | DONE | README.md (100KB command, 1MB log rotation) |
| Human-readable default summary | DONE | README.md Understanding Default Protection |
| Fix CLAUDE.md contradiction | DONE | CLAUDE.md coverage table |
| Environment variables | DONE | README.md Environment Variables |

### P3 Gaps Addressed
| Gap | Status | Where |
|-----|--------|-------|
| UX-09: Cookbook patterns note | DONE | schema-reference.md |

### Cross-Reference Gaps Addressed
| Gap | Status | Where |
|-----|--------|-------|
| SCOPE-01 linked from docs | DONE | README.md, schema-reference.md |
| SCOPE-02 linked from docs | DONE | README.md hookBehavior note, FAQ |
| KNOWN-ISSUES.md linked | DONE | README.md multiple locations |

---

## Files NOT Modified (by design)
- `CHANGELOG.md` -- no code changes, only doc updates
- `KNOWN-ISSUES.md` -- no new issues to add; existing issues referenced via links
- `TEST-PLAN.md` -- test-focused, not a doc gap
- `tests/README.md` -- adequate for its audience
- `commands/init.md` -- setup wizard prompt, changes would affect behavior
- `agents/config-assistant.md` -- agent prompt, changes would affect behavior
- `skills/config-guide/SKILL.md` -- skill prompt, changes would affect behavior
- All Python files -- documentation-only task, no code changes
