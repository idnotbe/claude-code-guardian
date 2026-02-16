# Documentation Fix Log

**Date**: 2026-02-16
**Author**: doc-fixer teammate
**Input**: V1 verification reports (05-v1-accuracy.md, 06-v1-usability.md, 07-v1-completeness.md)

---

## Changes Applied

### README.md - Accuracy Fixes

| # | Issue | Source | Before | After | Verified Against |
|---|-------|--------|--------|-------|------------------|
| A1 | Ask pattern count wrong | 05-v1-accuracy #1 | "17 ask patterns" (line 230) | "18 ask patterns" | `guardian.default.json`: 18 ask entries counted programmatically |
| A2 | Ask pattern count wrong (duplicate) | 05-v1-accuracy #1 | "18 block + 17 ask" (line 611) | "18 block + 18 ask" | Same as A1 |
| A3 | zeroAccessPaths count wrong | 05-v1-accuracy #2 | "26 zero-access" (line 615) | "27 zero-access" | `guardian.default.json`: 27 entries counted programmatically |
| A4 | readOnlyPaths count wrong | 05-v1-accuracy #3 | "17 read-only" (line 615) | "18 read-only" | `guardian.default.json`: 18 entries counted programmatically |
| A5 | noDeletePaths count wrong | 05-v1-accuracy #4 | "26 no-delete" (line 615) | "27 no-delete" | `guardian.default.json`: 27 entries counted programmatically |
| A6 | Log-skip list missing `type` | 05-v1-accuracy #8 | "Simple commands (`ls`, `cd`, `pwd`, `echo`, `cat`) under 10 characters are not even logged when allowed." | "Allowed commands under 10 characters, or commands starting with `ls`, `cd`, `pwd`, `echo`, `cat`, or `type`, are not logged." | `bash_guardian.py:1248-1250` |
| A7 | Test method count stale | 05-v1-accuracy #6 | "~1,009 test methods across 6 category directories" | "~631 test methods across 7 category directories" | pytest `--collect-only` reports 631 collected; 7 subdirectories in `tests/` |

### CLAUDE.md - Accuracy Fixes

| # | Issue | Source | Before | After | Verified Against |
|---|-------|--------|--------|-------|------------------|
| A8 | Total LOC stale | 05-v1-accuracy #5 | "~3,900 LOC total" | "~4,142 LOC total" | `wc -l` on all 6 scripts: 4,142 total |
| A9 | Test count stale | 05-v1-accuracy #6 | "~1,009 methods across 6 subdirectories" | "~631 methods across 7 subdirectories" | Same as A7 |
| A10 | --no-verify line number wrong | 05-v1-accuracy #7 | `auto_commit.py:145` | `auto_commit.py:146` | `auto_commit.py:146`: `if git_commit(message, no_verify=True):` |
| A11 | bash_guardian.py LOC | 05-v1-accuracy #5 | 1,231 | 1,289 | `wc -l bash_guardian.py` |
| A12 | _guardian_utils.py LOC | 05-v1-accuracy #5 | 2,308 | 2,426 | `wc -l _guardian_utils.py` |
| A13 | edit_guardian.py LOC | 05-v1-accuracy #5 | 75 | 86 | `wc -l edit_guardian.py` |
| A14 | read_guardian.py LOC | 05-v1-accuracy #5 | 71 | 82 | `wc -l read_guardian.py` |
| A15 | write_guardian.py LOC | 05-v1-accuracy #5 | 75 | 86 | `wc -l write_guardian.py` |

### README.md - Usability Fixes

| # | Issue | Source | Change |
|---|-------|--------|--------|
| U1 | Missing "Protected from overwrite" in block message table | 06-v1-usability Finding 2 | Added row: `Protected from overwrite: LICENSE` with resolution "Remove from noDeletePaths or use Edit tool instead" |
| U2 | Config assistant invocation unclear | 06-v1-usability Finding 5 | Added sentence: "Simply ask Claude about your Guardian configuration while the plugin is loaded" |

### README.md - Completeness Fixes

| # | Issue | Source | Change |
|---|-------|--------|--------|
| C1 | `LC_ALL=C` git locale forcing not documented | 07-v1-completeness FINDING-04 | Added note in Troubleshooting: "Guardian forces LC_ALL=C for all git operations..." |
| C2 | Deprecated `allowedExternalPaths` key not documented | 07-v1-completeness FINDING-07 | Added note in Upgrading section about renaming deprecated key |
| C3 | `$schema` IDE validation not documented | 07-v1-completeness FINDING-15 | Added IDE validation tip in Configuration Reference section |
| C4 | Emergency fallback config description incomplete | 07-v1-completeness FINDING-09 | Expanded fallback list to include `~/.gnupg/**`, `~/.aws/**`, `secrets.json`, `secrets.yaml` |

---

## Issues NOT Fixed (with justification)

### From 05-v1-accuracy.md

- **M1 (100KB approximation)**: "100KB" for `MAX_COMMAND_LENGTH = 100_000` is acceptable documentation shorthand. No fix needed.
- **M2 (Case sensitivity wording)**: Already correctly documented. No fix needed.
- **M3 (Pre-danger checkpoint code default)**: README correctly documents the shipped config default. No fix needed.

### From 06-v1-usability.md

- **Finding 1 (guardian.schema.json)**: This file exists in the repo. Not a doc issue.
- **Finding 3 ("Read-only path:" vs "Read-only file:")**: Code inconsistency, not a documentation issue. Would require code change.
- **Finding 4 (Fallback config summary)**: Expanded in C4 above with key additions while keeping it readable.

### From 07-v1-completeness.md

- **FINDING-01 (Internal constants)**: `MAX_PATH_PREVIEW_LENGTH` and `MAX_COMMAND_PREVIEW_LENGTH` are internal display limits. Not user-facing.
- **FINDING-02 (HookTimeoutError)**: Dead/unused code. Documenting would mislead.
- **FINDING-03 (sanitize_stderr_for_log)**: Internal privacy measure. Not user-facing.
- **FINDING-05 (Git retry mechanism)**: Transparent automatic behavior. Not user-facing.
- **FINDING-06 (sanitize_commit_message)**: Internal implementation detail.
- **FINDING-08 (noDeletePaths fail-closed)**: Already covered by CLAUDE.md security invariants.
- **FINDING-10 (allow_response)**: Already correctly documented in README.
- **FINDING-11 (Config validation details)**: Troubleshooting table is sufficient.
- **FINDING-12 (default_on_error dual-default)**: Covered by CLAUDE.md "must not fail-open" principle.
- **FINDING-13 (Self-guarding blocks Read)**: Already correctly documented.
- **FINDING-14 ($comment field)**: Common JSON convention, low priority.
- **FINDING-16 (Plugin UX components)**: Functionality is documented; exact invocation mechanism is implied.
- **FINDING-17 (Case sensitivity)**: Already correctly documented.
- **FINDING-18, -19, -20**: Internal APIs, not user-facing.

---

## Verification Method

Every accuracy fix was verified by:
1. Reading the actual implementation source code
2. Running programmatic counts (`wc -l`, `json.load` + `len()`, `pytest --collect-only`)
3. Confirming the corrected value matches the implementation before editing

Files modified:
- `/home/idnotbe/projects/claude-code-guardian/README.md` (14 changes)
- `/home/idnotbe/projects/claude-code-guardian/CLAUDE.md` (8 changes)
