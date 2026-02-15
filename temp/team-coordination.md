# Team Coordination: Enhancement 1 & 2 (Revised)

## Design Change (user feedback)
**`allowedExternalPaths` with mode object → split into two separate keys:**
- `allowedExternalReadPaths`: string[] — Read only
- `allowedExternalWritePaths`: string[] — Read + Write + Edit

This is cleaner, consistent with existing pattern (zeroAccessPaths, readOnlyPaths, noDeletePaths).
Old `allowedExternalPaths` is REMOVED entirely.

## API Contract

```python
# OLD: match_allowed_external_path(path: str) -> tuple[bool, str]
# NEW: Two simple functions:
#   match_allowed_external_read_path(path: str) -> bool
#   match_allowed_external_write_path(path: str) -> bool
#
# Or a combined function:
#   match_allowed_external_path(path: str) -> tuple[bool, str]
#     checks both lists, returns (matched, "read"|"readwrite"|"")
#     allowedExternalWritePaths checked first (more permissive)
```

## Config Format
```json
{
  "allowedExternalReadPaths": ["/sibling-project/**"],
  "allowedExternalWritePaths": ["~/.claude/projects/*/memory/**"]
}
```

## Files to Modify

| File | Changes |
|------|---------|
| `hooks/scripts/_guardian_utils.py` | Replace `match_allowed_external_path()`, update `run_path_guardian_hook()`, update `validate_guardian_config()`, update fallback config (line 415) |
| `hooks/scripts/bash_guardian.py` | Enhancement 2: `extract_paths()` includes external paths, update imports |
| `assets/guardian.schema.json` | Replace `allowedExternalPaths` with two new keys |
| `tests/core/test_external_path_mode.py` | New tests |

## Fallback Config (line 415 in _guardian_utils.py)
Current: `"allowedExternalPaths": []`
New: remove it, add `"allowedExternalReadPaths": []` and `"allowedExternalWritePaths": []`

## Team Members & Status

| # | Role | Status | Output File |
|---|------|--------|-------------|
| 1 | Implementer-E1v2 (Enhancement 1 revised) | in_progress | temp/impl-e1v2-output.md |
| 2 | Implementer-E2 (Enhancement 2) | pending | temp/impl-e2-output.md |
| 3 | Test Writer | pending | temp/test-writer-output.md |
| 4 | Security Reviewer (V1) | pending | temp/review-security-v1.md |
| 5 | Compat Reviewer (V1) | pending | temp/review-compat-v1.md |
| 6 | Integration Tester (V2) | pending | temp/verify-integration-v2.md |
| 7 | Architecture Reviewer (V2) | pending | temp/verify-arch-v2.md |
