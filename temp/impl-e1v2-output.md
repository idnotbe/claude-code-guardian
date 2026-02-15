# Implementer-E1v2 Output: Split allowedExternalPaths into Read/Write Keys

## Status: COMPLETE

## Summary

Replaced the single `allowedExternalPaths` config key (which supported mixed string/object entries with mode) with two simple string-array keys:
- `allowedExternalReadPaths`: string[] -- allows Read tool only
- `allowedExternalWritePaths`: string[] -- allows Read + Write + Edit tools

The old `allowedExternalPaths` key is fully removed from both modified files.

## Pre-work Validation

- **Vibe check**: Confirmed approach is sound, well-scoped, and aligned with existing config patterns.
- **Codex clink**: Codex independently recommended the split-key approach for: simpler validation, better auditability, no order-dependent behavior, consistency with existing tier keys (`zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths`), and reduced risk of accidental external-write grants.
- **Gemini clink**: Gemini quota exhausted (skipped).

## Changes Made

### File 1: `hooks/scripts/_guardian_utils.py`

**Change 1 -- `match_allowed_external_path()` (lines 1221-1246)**
- Replaced object/string parsing loop with two simple list lookups
- Checks `allowedExternalWritePaths` first (more permissive -- also grants read)
- Then checks `allowedExternalReadPaths`
- Return signature preserved: `tuple[bool, str]` returning `(True, "readwrite")`, `(True, "read")`, or `(False, "")`
- Filters with `isinstance(p, str)` for safety

**Change 2 -- `run_path_guardian_hook()` deny message (line 2307)**
- Old: `"Use {\"path\": \"...\", \"mode\": \"readwrite\"} in allowedExternalPaths to allow writes."`
- New: `"Add this path to allowedExternalWritePaths to allow writes."`

**Change 3 -- `validate_guardian_config()` (lines 714-723)**
- Added `allowedExternalReadPaths` and `allowedExternalWritePaths` to the `path_sections` list
- Removed the separate custom validation block for the old `allowedExternalPaths` (which handled string/object union types)
- Both new keys now get the standard string-array validation (same as `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths`)
- Updated comment: removed "excludes allowedExternalPaths which has custom validation" note

**Change 4 -- Fallback config (lines 415-416)**
- Old: `"allowedExternalPaths": []`
- New: `"allowedExternalReadPaths": []` and `"allowedExternalWritePaths": []`

**Change 5 -- Comment update (line 2296)**
- Updated inline comment from "allowedExternalPaths" to "allowedExternalReadPaths/WritePaths"

### File 2: `assets/guardian.schema.json`

**Change 6 -- Schema definition (lines 109-124)**
- Removed `allowedExternalPaths` with its `oneOf` (string | object) item schema
- Added `allowedExternalReadPaths`: simple string array with description noting read-only access
- Added `allowedExternalWritePaths`: simple string array with description noting read+write access
- Both include notes about ~ expansion, ** matching, and that only the 'outside project' check is bypassed

## API Contract Preserved

The function signature `match_allowed_external_path(path: str) -> tuple` is unchanged. Enhancement 2 (bash_guardian.py) can call `match_allowed_external_path(str(path))[0]` without modification.

## Test Results

| Test Suite | Result | Notes |
|-----------|--------|-------|
| `tests/core/test_p0p1_comprehensive.py` | 180/180 PASS | Zero regressions |
| `tests/core/test_v2fixes.py` | 124/125 PASS (1 FAIL) | Pre-existing failure (`test_ln_pattern_in_source`) -- unrelated to our changes, confirmed via git stash |
| `tests/security/test_v2_crossmodel.py` | 20/20 PASS | Zero regressions |
| `tests/security/test_v2fixes_adversarial.py` | 143/143 PASS | Zero regressions |
| `tests/security/test_v2_adversarial.py` | 61/63 PASS (2 FAIL) | Pre-existing failures (hex encoding bypass, question mark glob) -- confirmed via git stash |
| `tests/regression/test_allowed_external.py` | N/A | Pre-existing import error (`_protection_utils` module) |

**Conclusion: Zero regressions introduced by these changes.**

## Follow-up Items (out of scope for this task)

These files reference the old `allowedExternalPaths` key and should be updated by other team members:

1. **`agents/config-assistant.md` (line 150)** -- Plugin UX documentation references old key
2. **`skills/config-guide/references/schema-reference.md` (lines 17, 161)** -- Config guide references old key
3. **`README.md` (line 131)** -- Top-level README references old key
4. **`tests/regression/test_allowed_external.py`** -- Old test using `allowedExternalPaths` config format; needs rewrite for new keys
5. **`assets/guardian.default.json` (line 238)** -- Self-guarded file, could not read/modify; likely needs update from `allowedExternalPaths: []` to the two new keys
6. **Various files in `temp/` and `_archive/`** -- Planning/documentation files; low priority
