# Advisory Fixes Plan — Working Memory

## Date: 2026-02-15
## Scope: Fix all 3 advisory findings from P0/P1 verification

---

## ADVISORY-1: Variable shadowing (Informational)

**Location**: `_guardian_utils.py:2382`
**Issue**: `resolved = expand_path(file_path)` shadows outer `resolved = resolve_tool_path(file_path)` from L2298
**Fix**: Rename to `nodelete_resolved`
**Risk**: Zero — cosmetic rename
**Tests**: No changes needed

---

## ADVISORY-2: TOCTOU in exists() check (Low)

**Location**: `_guardian_utils.py:2383`
**Issue**: Race between `resolved.exists()` check and actual Write execution
- Scenario 2 (file created between check and write) = bypass

**Fix**: Remove the `exists()` check entirely. Always block Write on noDelete patterns.
- noDeletePaths files (CLAUDE.md, .gitignore, package.json, CI configs) are almost always pre-existing
- Creating new files matching noDelete patterns can still be done via Bash + Edit
- Eliminating TOCTOU is more important than convenience

**Code change**:
```python
# BEFORE (with TOCTOU):
if tool_name.lower() == "write" and match_no_delete(path_str):
    resolved = expand_path(file_path)
    if resolved.exists():  # ← TOCTOU race here
        # ... block ...

# AFTER (no TOCTOU):
if tool_name.lower() == "write" and match_no_delete(path_str):
    # Block ALL Write operations on noDelete patterns (no exists() check = no TOCTOU)
    # ... block ...
```

**Error message update**:
```
Protected path: {filename}
This path matches noDeletePaths. Write tool is blocked. Use Edit for modifications or Bash to create new files.
```

**Test changes**:
- `test_write_new_nodelete_file_allowed` → update to expect BLOCKED (Write to any noDelete pattern now blocked)
- Update test name and assertion

**Docstring update**: Remove "existing files only" from `run_path_guardian_hook()` docstring

---

## ADVISORY-3: Fail-open normalization helpers (Medium)

### Functions to fix:

1. **`expand_path()` (L954-973)**: Remove try/except, let exceptions propagate
   - Callers already handle: `is_path_within_project` (try/except→False), `normalize_path_for_matching` (will fix)

2. **`normalize_path()` (L918-951)**: DEAD CODE — never called. Leave as-is.

3. **`normalize_path_for_matching()` (L1061-1088)**: Remove try/except, let exceptions propagate
   - Callers: `match_path_pattern` (has try/except), `is_self_guardian_path` (will fix)

4. **`resolve_tool_path()` (L2214-2235)**: Remove except that returns raw path, let OSError propagate
   - Caller: `run_path_guardian_hook` L2298 (will add try/except→deny)

5. **`match_path_pattern()` (L1125-1191)**: Add `default_on_error` parameter
   - Current: returns False on error = fail-open for deny checks
   - Fix: returns `default_on_error` on error

6. **`match_zero_access/read_only/no_delete()`**: Pass `default_on_error=True` (fail-closed)

7. **`match_allowed_external_path()`**: Keep `default_on_error=False` (fail-closed for allow checks)

8. **`is_self_guardian_path()` (L2180)**: Add try/except around `normalize_path_for_matching` returning True

9. **`run_path_guardian_hook()` (L2298)**: Add try/except around `resolve_tool_path` emitting deny

### Security analysis of changes:

| Function | Before (error) | After (error) | Security impact |
|----------|---------------|---------------|-----------------|
| `expand_path` | returns Path(raw) | raises | Callers must handle |
| `normalize_path_for_matching` | returns raw string | raises | Callers must handle |
| `match_path_pattern` (deny context) | returns False (fail-open) | returns True (fail-closed) | Deny on error ✓ |
| `match_path_pattern` (allow context) | returns False (fail-closed) | returns False (fail-closed) | No change ✓ |
| `match_zero_access` | returns False (fail-open) | returns True (fail-closed) | Block on error ✓ |
| `match_read_only` | returns False (fail-open) | returns True (fail-closed) | Block on error ✓ |
| `match_no_delete` | returns False (fail-open) | returns True (fail-closed) | Block on error ✓ |
| `match_allowed_external_path` | returns None (fail-closed) | returns None (fail-closed) | No change ✓ |
| `is_self_guardian_path` | returns False (fail-open) | returns True (fail-closed) | Protect on error ✓ |
| `resolve_tool_path` | returns raw Path | raises OSError | Caller denies ✓ |

### New tests needed:
- `test_match_path_pattern_default_on_error_true`
- `test_match_path_pattern_default_on_error_false`
- `test_match_zero_access_failclosed_on_error`
- `test_match_read_only_failclosed_on_error`
- `test_match_no_delete_failclosed_on_error`
- `test_is_self_guardian_path_failclosed_on_error`
- `test_resolve_tool_path_raises_on_oserror`
- `test_run_path_guardian_hook_resolve_failure_denies`
- `test_expand_path_raises_on_exception`
- `test_normalize_path_for_matching_raises_on_exception`
- `test_write_nodelete_always_blocked` (updated from exists() test)

---

---

## Cross-Model Review (pal chat — gemini 3 pro)

**Verdict**: All 3 fixes APPROVED.

Key feedback:
1. ADVISORY-2: This fixes "failure-mode bypass" not full TOCTOU (which is inherent to pre-hook model). Agreed.
2. ADVISORY-3 risks:
   - **Missing call sites**: Must grep ALL callers. Top-level `run_path_guardian_hook` try/except is critical safety net.
   - **Symlink loops**: `Path.resolve()` raises RuntimeError on loops → now caught → deny. Acceptable.
   - **Logging**: When `default_on_error` triggers, MUST log warning for debugging.
3. Vibe-check recommended keeping exists() with fail-closed error path (adopted).

## Execution Order

1. ADVISORY-1 (variable rename) — smallest, no risk
2. ADVISORY-2 (keep exists + fail-closed error path) — moderate
3. ADVISORY-3 (fail-closed normalization) — largest, most callers affected
4. Write all new tests
5. Run full test suite
6. V1 verification round (diverse teammates)
7. V2 verification round (diverse teammates)
