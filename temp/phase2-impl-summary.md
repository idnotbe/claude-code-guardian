# Phase 2 Implementation Summary: F1 Interpreter Path Resolution

## Changes Made

### 1. `hooks/scripts/bash_guardian.py` — New function (lines 1243-1328)

**`extract_paths_from_interpreter_payload(command, project_dir) -> list[Path]`**

Added near `extract_paths()`. Extracts file paths from interpreter `-c`/`-e` payload string literals.

Algorithm:
1. Calls `extract_interpreter_payload(command)` to get the payload string
2. Uses `_QUOTED_LITERAL_RE` regex to find single/double-quoted string literals
3. Filters out non-path strings (URLs, MIME types, interpolation markers)
4. Resolves relative paths against `project_dir`
5. Validates all paths through `is_within_project()` (relative_to-based, F2-1)
6. Supports glob expansion within project boundary

Security invariants enforced:
- **F2-1**: Project boundary via `Path.relative_to()` (NOT `str.startswith()`)
- **F2-2**: Rejects `{}` and `$` in literals (unresolvable interpolation)
- **Fail-closed**: Outer `try/except` returns `[]` on any error

### 2. `hooks/scripts/bash_guardian.py` — Modified F1 block (lines 1912-1954)

Replaced the simple F1 ASK with a three-branch decision:

1. **Interpreter + paths resolved**: Routes paths through normal validation pipeline (no F1 ASK)
2. **Interpreter + paths NOT resolved**: Enriched F1 ASK with API name (e.g., "Detected delete via os.remove but could not resolve target paths")
3. **Non-interpreter command**: Standard F1 ASK (unchanged behavior)

API name extraction uses `interp_detail.rsplit(": ", 1)[-1]` to parse from the existing `check_interpreter_payload()` reason string — no signature changes needed.

### 3. `hooks/scripts/_guardian_utils.py` — No changes

The `check_interpreter_payload()` 2-tuple return `(bool, str)` is preserved. The API name is extracted from the reason string in the F1 block, avoiding any signature-breaking changes.

### 4. MIME type filter refinement

During testing, discovered the MIME type filter was too broad — it rejected legitimate relative paths like `data/out.txt` (single `/`, doesn't start with `.` or `/`). Added `'.' not in literal` condition to distinguish MIME types (`application/json`) from paths (`data/out.txt`).

## Tests Created

**File**: `tests/regression/test_interpreter_path_resolution.py` — 22 test methods in 5 classes

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestExtractPathsBasic` | 7 | Python/Node extraction, variables, chr() obfuscation, non-interpreter, no payload |
| `TestFilteringRules` | 5 | URL, MIME type, f-string `{}`, `$` interpolation, curly braces |
| `TestProjectBoundary` | 4 | Outside project, traversal attack, prefix confusion (F2-1), valid path |
| `TestGlobExpansion` | 2 | Glob with matches, glob with no matches |
| `TestF1Integration` | 4 | Enriched message with API name, paths resolved flow, non-interpreter unchanged, Node enrichment |

## Self-Check Results

1. Uses `is_within_project()` (relative_to-based)? **YES** (line 1320)
2. Rejects `{}` and `$` in literals? **YES** (line 1287)
3. F1 block fail-closed? **YES** (no paths -> ASK fires)
4. Non-interpreter F1 behavior unchanged? **YES** (else branch at line 1949)
5. Enriched message includes API name? **YES** (e.g., "via os.remove")
6. All tests pass? **YES** (22/22 pass)

## Test Results

```
Phase 2 tests: 22 passed, 0 failed
Full suite:    1002 passed, 11 failed (pre-existing), 1 error (pre-existing)
New failures:  0
```

Pre-existing failures (unchanged): 11 in `TestNewBlockPatterns`, 1 error in `test_bypass_v2.py`.
