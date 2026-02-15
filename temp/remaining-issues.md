# Remaining Issues from Enhancement 1 & 2

> Created: 2026-02-15
> Status: Deferred to next session
> Related PR: Enhancement 1 (allowedExternalReadPaths/WritePaths split) + Enhancement 2 (bash external path extraction)

---

## Issue 1: Tuple truthiness landmine (MEDIUM)

### Background
`match_allowed_external_path()` returns `tuple[bool, str]`. In Python, a tuple is truthy if it's non-empty — so `(False, "")` is **truthy** because it's a 2-element tuple.

```python
>>> bool((False, ""))
True  # Surprise!
```

### Current state
All current callers are safe:
- `_guardian_utils.py:2297`: `matched, ext_mode = match_allowed_external_path(path_str)` — unpacking
- `bash_guardian.py:522,556,563`: `match_allowed_external_path(str(path))[0]` — indexing
- `bash_guardian.py:1065`: `ext_matched, ext_mode = match_allowed_external_path(path_str)` — unpacking

But if a future developer writes `if match_allowed_external_path(path):` it will **always be True**, silently bypassing the security check.

### Goal
Change the return type to eliminate the landmine. Options:

**Option A**: Return `Optional[str]` instead of `tuple[bool, str]`
```python
def match_allowed_external_path(path: str) -> str | None:
    """Returns mode string ("read" or "readwrite") if matched, None if not."""
    # ...
    return "readwrite"  # or "read" or None
```
- Callers: `mode = match_allowed_external_path(path); if mode:` — natural, safe
- `None` is falsy, `"read"` and `"readwrite"` are truthy

**Option B**: Keep tuple but make it `(bool, str)` and add linter/test guard
- Less clean but no API change

**Recommendation**: Option A. Cleaner, Pythonic, eliminates the footgun entirely.

### Files to modify
- `hooks/scripts/_guardian_utils.py:1221-1246` — function body + return type
- `hooks/scripts/_guardian_utils.py:2297` — caller in `run_path_guardian_hook()`
- `hooks/scripts/bash_guardian.py:522,556,563` — callers in `extract_paths()`
- `hooks/scripts/bash_guardian.py:1065` — caller in enforcement loop
- `tests/core/test_external_path_mode.py` — update all assertions

### Related code (current implementation)
```python
# _guardian_utils.py:1221
def match_allowed_external_path(path: str) -> tuple:
    config = load_guardian_config()
    write_patterns = config.get("allowedExternalWritePaths", [])
    if any(match_path_pattern(path, p) for p in write_patterns if isinstance(p, str)):
        return (True, "readwrite")
    read_patterns = config.get("allowedExternalReadPaths", [])
    if any(match_path_pattern(path, p) for p in read_patterns if isinstance(p, str)):
        return (True, "read")
    return (False, "")
```

---

## Issue 2: No deprecation warning for old `allowedExternalPaths` key (MEDIUM)

### Background
Enhancement 1 replaced the single `allowedExternalPaths` config key with two new keys:
- `allowedExternalReadPaths` (Read only)
- `allowedExternalWritePaths` (Read + Write + Edit)

The old key is silently ignored. Any user with an existing config that uses `allowedExternalPaths` will lose that protection without any warning after updating.

### Current state
- The old key was a rarely-used feature (the enhancement brief notes this)
- `load_guardian_config()` simply doesn't look for `allowedExternalPaths` anymore
- No warning is logged when the old key is present in config

### Goal
Add a deprecation warning in `load_guardian_config()` or `validate_guardian_config()` that:
1. Detects the old `allowedExternalPaths` key in loaded config
2. Logs a WARNING to guardian.log
3. Optionally prints a warning to stderr (visible to user)
4. Suggests the migration: "Rename 'allowedExternalPaths' to 'allowedExternalReadPaths' (for read-only) or 'allowedExternalWritePaths' (for read+write)"

### Files to modify
- `hooks/scripts/_guardian_utils.py` — `validate_guardian_config()` (~line 710) or `load_guardian_config()` (~line 430)
- `tests/core/test_external_path_mode.py` — add test for deprecation warning

### Related code
```python
# _guardian_utils.py:652 — validate_guardian_config()
# This is already called during config loading and returns a list of error strings.
# Could add a warning-level message here.
```

---

## Issue 3: Loose type hint `-> tuple` (LOW)

### Background
The function signature uses `-> tuple` without specifying element types. Python 3.9+ supports `tuple[bool, str]`.

### Current state
```python
def match_allowed_external_path(path: str) -> tuple:
```

### Goal
If keeping tuple return (see Issue 1), tighten the type hint:
```python
def match_allowed_external_path(path: str) -> tuple[bool, str]:
```

If switching to Option A from Issue 1, this becomes moot — the return type would be `str | None`.

### Files to modify
- `hooks/scripts/_guardian_utils.py:1221`

---

## Cross-references

- Enhancement brief: `temp/guardian-enhancement-brief.md`
- Team coordination: `temp/team-coordination.md`
- Security review: `temp/review-security-v1.md`
- Compat review: `temp/review-compat-v1.md`
- Architecture review: `temp/verify-arch-v2.md`
- Integration test results: `temp/verify-integration-v2.md`
- New test file: `tests/core/test_external_path_mode.py`
