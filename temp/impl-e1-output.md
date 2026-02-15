# Enhancement 1 Implementation Output

## Status: COMPLETE

## Changes Made

### Change 1: `match_allowed_external_path()` (lines 1235-1266)
**File:** `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`

- Changed return type from `bool` to `tuple` (specifically `tuple[bool, str]`)
- Now returns `(matched, mode)` where mode is `"read"`, `"readwrite"`, or `""` (unmatched)
- Supports two config entry formats:
  - **String**: treated as read-only (`mode="read"`) -- BREAKING CHANGE
  - **Object** `{"path": "...", "mode": "read"|"readwrite"}`: explicit mode
- Invalid mode values fail-safe to `"read"` (more restrictive)
- First-match-wins semantics (patterns evaluated in config order)

### Change 2: `run_path_guardian_hook()` (lines 2314-2341)
**File:** `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`

- Updated to unpack tuple return: `matched, ext_mode = match_allowed_external_path(path_str)`
- Added mode enforcement: when `ext_mode == "read"` and `tool_name.lower() in ("write", "edit")`, the request is DENIED
- Deny message is actionable: tells user to use object format with `mode: "readwrite"`
- Dry-run mode is handled for the new read-only denial path
- Log messages now include `mode=` for audit trail
- Read tool is NOT blocked by read-only external paths (correct behavior)

### Change 3: `validate_guardian_config()` (lines 713-737)
**File:** `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`

- Removed `allowedExternalPaths` from the generic string-only path validation loop (line 714)
- Added dedicated validation block for `allowedExternalPaths` that accepts:
  - String entries (glob patterns)
  - Object entries with required `path` field and optional `mode` field
  - Validates `mode` is one of `"read"` or `"readwrite"` if present
  - Reports clear error for missing `path` field in objects
  - Reports clear error for non-string/non-object entries

### Change 4: JSON Schema (lines 109-127)
**File:** `/home/idnotbe/projects/claude-code-guardian/assets/guardian.schema.json`

- Changed `allowedExternalPaths.items` from `{"type": "string"}` to `oneOf` supporting both:
  - String (glob pattern, read-only mode)
  - Object with `path` (required), `mode` (optional, enum: `["read", "readwrite"]`, default: `"read"`)
- Updated description to reflect the new semantics
- Object schema uses `additionalProperties: false` for strict validation

## API Contract

```python
# OLD: match_allowed_external_path(path: str) -> bool
# NEW: match_allowed_external_path(path: str) -> tuple[bool, str]
#
# Returns:
#   (True, "read")      - matched, read-only access
#   (True, "readwrite")  - matched, full access
#   (False, "")          - not matched
```

## Breaking Changes

1. **Return type change**: `match_allowed_external_path()` now returns `tuple[bool, str]` instead of `bool`. All callers must be updated.
2. **Default mode for string entries**: String entries in `allowedExternalPaths` now default to `"read"` mode. Previously they were effectively `"readwrite"`. Users wanting write access must use object format.

## Callers Requiring Updates

| Caller | Location | Status |
|--------|----------|--------|
| `run_path_guardian_hook()` | `_guardian_utils.py:2317` | Updated (Change 2) |
| `tests/regression/test_allowed_external.py` | Lines 173-547 | NOT updated (has pre-existing import error; Test Writer's responsibility) |

Note: `bash_guardian.py` does NOT call `match_allowed_external_path()` directly.

## Test Results

- **Core tests**: 180/180 PASS (no regressions)
- **Security tests**: Pre-existing failures (17 failures, 3 bypasses) -- none related to this change
- **Regression tests**: Pre-existing import error (`_protection_utils` module not found) -- not caused by this change

## External Review

Consulted with Codex (via clink) for security review. Key feedback:
- Validated that fail-safe to "read" is reasonable (they suggested "deny bypass" as an alternative, but plan specifies "read")
- Confirmed first-match-wins is the correct precedence strategy
- Confirmed the validation loop conflict (which we handled by excluding `allowedExternalPaths` from the generic loop)
- Noted defense-in-depth ordering is preserved: after external bypass, self-guardian/zeroAccess/readOnly checks still run

## Dependencies

- Enhancement 2 (bash_guardian.py) can proceed -- it does not directly call `match_allowed_external_path()`
- Test Writer needs to account for the tuple return type in new tests
