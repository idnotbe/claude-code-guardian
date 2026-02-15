# Implementer-E2 Output: Bash Guardian External Path Extraction

## Status: COMPLETE

## Summary

Updated `extract_paths()` in `bash_guardian.py` to include allowed external paths in the extraction pipeline. Previously, external paths (even those configured in `allowedExternalReadPaths`/`allowedExternalWritePaths`) were silently dropped during path extraction, meaning bash commands like `sed -i /external/file.txt` could bypass `readOnlyPaths`/`zeroAccessPaths` checks.

## Pre-work Validation

- **Vibe check (pre)**: Confirmed approach is sound, well-scoped, and aligned with task specification. No concerns about API contract or ordering.
- **Codex clink**: Codex confirmed that external path candidates should be extracted and run through the same policy pipeline (`zeroAccess`, `readOnly`, `noDelete`, symlink/traversal). Key edge cases noted: `cd` affecting relative paths, unresolved `$VAR`/`$(...)`, external glob expansion, redirections with quoted targets, and path-like non-paths (URLs/scp/git). These edge cases are pre-existing and out of scope for this enhancement.
- **Vibe check (post)**: Confirmed implementation is complete, minimal, and correct with zero regressions.

## Changes Made

### File: `hooks/scripts/bash_guardian.py`

**Change 1 -- Import addition (line 51)**
- Added `match_allowed_external_path` to the import block from `_guardian_utils`
- Positioned alphabetically between `make_hook_behavior_response` and `match_ask_patterns`

**Change 2 -- Location A: Flag-concatenated paths (line 522-523)**
- Added `elif match_allowed_external_path(str(suffix_path))[0]:` after the existing project-internal and `allow_nonexistent` checks
- This catches paths like `-f/external/config` where the flag suffix is an allowed external path

**Change 3 -- Location B: Glob expansion (line 556-557)**
- Added `elif match_allowed_external_path(str(p))[0]:` after the `is_within_project` check inside the glob expansion loop
- This catches glob-expanded external paths that match allowed patterns

**Change 4 -- Location C: Normal path extraction (line 563-564)**
- Added `elif match_allowed_external_path(str(path))[0]:` after the existing project-internal and `allow_nonexistent` checks
- This is the primary extraction point for most command arguments

### Design Decisions

1. **External check is always the LAST elif**: Project-internal paths take priority. External path matching is the fallback for paths that are outside the project but explicitly allowed.
2. **No `allow_nonexistent` logic for externals**: External paths are included only if they match the configured allowed patterns. The `match_allowed_external_path()` function handles pattern matching (including `**` globs and `~` expansion) without requiring the path to exist on disk.
3. **Uses `[0]` tuple indexing**: `match_allowed_external_path()` returns `(bool, str)` where the string is `"read"`, `"readwrite"`, or `""`. We only need the boolean for extraction; the mode is used later during enforcement.

### Security Flow

Once extracted, external paths flow through the same security checks as internal paths:
- `match_zero_access()` (bash_guardian.py lines ~1029-1040) -- blocks access entirely
- `match_read_only()` (bash_guardian.py lines ~1041-1050) -- blocks writes to read-only paths
- `match_no_delete()` (bash_guardian.py lines ~1051-1062) -- blocks deletion of protected paths

This closes the gap where external paths were invisible to the bash guardian's path-tier enforcement.

## Test Results

| Test Suite | Result | Notes |
|-----------|--------|-------|
| `tests/core/test_p0p1_comprehensive.py` | 180/180 PASS | Zero regressions |
| `tests/core/test_v2fixes.py` | 124/125 PASS (1 FAIL) | Pre-existing failure (`test_ln_pattern_in_source`) -- unrelated to our changes |
| `tests/security/test_v2_crossmodel.py` | 20/20 PASS | Zero regressions |
| `tests/security/test_v2fixes_adversarial.py` | 143/143 PASS | Zero regressions |
| `tests/security/test_v2_adversarial.py` | 61/63 PASS (2 FAIL) | Pre-existing failures (hex encoding bypass, question mark glob) -- unrelated |

**Conclusion: Zero regressions introduced by these changes.**

## Diff Summary

```diff
--- a/hooks/scripts/bash_guardian.py
+++ b/hooks/scripts/bash_guardian.py
@@ -50,6 +50,7 @@
         make_hook_behavior_response,  # hookBehavior response helper
+        match_allowed_external_path,
         match_ask_patterns,
@@ -520,6 +521,8 @@
                         elif allow_nonexistent and _is_within_project_or_would_be(suffix_path, project_dir):
                             paths.append(suffix_path)
+                        elif match_allowed_external_path(str(suffix_path))[0]:
+                            paths.append(suffix_path)
@@ -554,6 +557,8 @@
                     if p.exists() and is_within_project(p, project_dir):
                         paths.append(p)
+                    elif match_allowed_external_path(str(p))[0]:
+                        paths.append(p)
@@ -561,6 +566,8 @@
                 elif allow_nonexistent and _is_within_project_or_would_be(path, project_dir):
                     paths.append(path)
+                elif match_allowed_external_path(str(path))[0]:
+                    paths.append(path)
```

## Dependencies

- **Depends on E1v2**: The `match_allowed_external_path()` function in `_guardian_utils.py` was implemented by E1v2. This enhancement only imports and calls it.
- **No other files modified**: Only `bash_guardian.py` was changed.

## Follow-up Items (out of scope)

1. **New tests needed**: Tests for `extract_paths()` with external paths should be written by the Test Writer (task #3). Key scenarios:
   - External path in normal argument position is extracted
   - External path in flag-concatenated position is extracted
   - External path not in allowed lists is NOT extracted
   - Extracted external path triggers zeroAccess denial
   - Extracted external path triggers readOnly enforcement
2. **Redirection targets**: `extract_redirection_targets()` (separate function) also filters to project-internal paths. This may need similar treatment in a future enhancement.
