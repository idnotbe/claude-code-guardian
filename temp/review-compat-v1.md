# Compatibility Review V1: Enhancement 1 & 2

**Reviewer:** Compatibility Reviewer V1
**Date:** 2026-02-15
**Status:** COMPLETE
**Overall verdict:** 1 CRITICAL, 3 HIGH, 2 MEDIUM, 1 LOW issues found

---

## Review Checklist

### 1. Breaking Change Handling

**Verdict: FAIL (HIGH)**

The old `allowedExternalPaths` key is removed entirely. Any existing user configs that use this key will **silently lose their external path allowlist** -- all previously-allowed external paths will be blocked without warning.

**Evidence:**

- `_guardian_utils.py:1221-1246`: `match_allowed_external_path()` only reads `allowedExternalReadPaths` and `allowedExternalWritePaths`. The old key is completely ignored.
- `_guardian_utils.py:653-735`: `validate_guardian_config()` does not check for unknown/deprecated keys. There is no warning emitted when the old key is present.
- `_guardian_utils.py:508-512`: Config validation is warn-only ("warn but don't block for backwards compatibility"), but even this warning will not fire because the validator does not detect unknown keys.
- `tests/core/test_external_path_mode.py:610-624`: Test explicitly asserts old key is ignored -- this is by design but with no mitigation.

**Behavior for affected users:**
- Old `allowedExternalPaths` config entries are silently ignored
- External paths that were previously allowed become blocked (fail-closed)
- No log warning, no error, no migration guidance
- This is *safe* (fail-closed) but *operationally disruptive*

**No migration path exists.** There are no migration notes, no deprecation shim, no CHANGELOG entry, and no version bump.

**Recommendation:**
1. Add a deprecation shim in `load_guardian_config()`: if `allowedExternalPaths` is present in loaded config, log a clear WARN message like `"DEPRECATED: 'allowedExternalPaths' is no longer supported. Migrate to 'allowedExternalReadPaths' and/or 'allowedExternalWritePaths'."`
2. Optionally auto-map: if old key exists and new keys are absent, map old entries to `allowedExternalWritePaths` (preserving old semantics where all entries granted read+write).
3. Add a CHANGELOG entry documenting the breaking change.

---

### 2. API Consistency

**Verdict: WARN (MEDIUM)**

The new key names `allowedExternalReadPaths` and `allowedExternalWritePaths` follow the existing naming convention well. They are parallel to `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths` (camelCase, "Paths" suffix, string arrays).

However, there is a **function signature inconsistency**:

| Function | Returns |
|----------|---------|
| `match_zero_access(path)` | `bool` |
| `match_read_only(path)` | `bool` |
| `match_no_delete(path)` | `bool` |
| `match_allowed_external_path(path)` | `tuple[bool, str]` |

The tuple return is justified (it needs to convey the mode: "read" vs "readwrite"), but it creates a landmine for future callers. A caller expecting `bool` would get a truthy tuple instead, since non-empty tuples are always truthy in Python. The Enhancement 2 code in `bash_guardian.py` correctly uses `[0]` indexing, but this pattern is fragile.

**Evidence:**
- `_guardian_utils.py:1179-1218`: `match_zero_access`, `match_read_only`, `match_no_delete` all return `bool`
- `_guardian_utils.py:1221-1246`: `match_allowed_external_path` returns `tuple`
- `bash_guardian.py:522,556,563`: Calls use `[0]` to extract boolean

**Recommendation:** This is acceptable for now given the justification, but consider either:
- Adding a simple `is_allowed_external_path(path) -> bool` wrapper for callers that only need the boolean
- Or documenting the return type prominently in a code comment near the import

---

### 3. Function Signature (Tuple Return)

**Verdict: WARN (MEDIUM)** -- Covered in item 2 above. The tuple return is intentional and documented. The `team-coordination.md` API contract explicitly defined this. The real risk is in bash_guardian discarding the mode (see item 8 below).

---

### 4. Schema Completeness

**Verdict: PASS**

Both new keys are properly defined in the JSON schema:

```json
// guardian.schema.json lines 109-124
"allowedExternalReadPaths": {
    "type": "array",
    "description": "Glob patterns for paths outside the project that are allowed for read-only access...",
    "items": { "type": "string" },
    "default": []
},
"allowedExternalWritePaths": {
    "type": "array",
    "description": "Glob patterns for paths outside the project that are allowed for read and write access...",
    "items": { "type": "string" },
    "default": []
}
```

Both include:
- Proper descriptions distinguishing read-only vs read+write
- Mention of `~` expansion and `**` matching
- Note that only the "outside project" check is bypassed
- Default values of `[]`

The schema has `additionalProperties: false` at the top level, so configs with the old `allowedExternalPaths` would **fail strict JSON Schema validation** -- this is actually a helpful signal for users who validate configs, but see item 1 for the silent runtime behavior.

---

### 5. Default Config

**Verdict: FAIL (HIGH)**

`assets/guardian.default.json` line 238 still contains the OLD key:
```json
"allowedExternalPaths": []
```

This file could not be read directly (it is self-guarded), but the `grep` search confirms the stale reference. The E1v2 implementer noted this as a known follow-up item: *"Self-guarded file, could not read/modify; likely needs update."*

**Impact:** The `/guardian:init` command uses `assets/guardian.default.json` as its template. Any config generated from this template will contain the deprecated key, which is silently ignored by the new code. New users will believe they can add entries to `allowedExternalPaths` when it has no effect.

**Recommendation:** Update `guardian.default.json` to replace `"allowedExternalPaths": []` with:
```json
"allowedExternalReadPaths": [],
"allowedExternalWritePaths": []
```

---

### 6. Init Wizard / Config Guide / Config Assistant

**Verdict: FAIL (HIGH)**

All three documentation/UX files still reference the old key:

| File | Line | Stale Content |
|------|------|---------------|
| `agents/config-assistant.md` | 150 | `allowedExternalPaths -- paths outside project allowed for writes` |
| `skills/config-guide/references/schema-reference.md` | 17 | `"allowedExternalPaths": [ ... ]` in top-level structure example |
| `skills/config-guide/references/schema-reference.md` | 161-169 | Full `### allowedExternalPaths` section with description and JSON example |
| `README.md` | 131 | Config table: `allowedExternalPaths \| Paths outside the project allowed for writes` |

**Impact:** Users consulting any of these resources will be guided to use a key that no longer works. The config assistant agent (`agents/config-assistant.md`) is particularly concerning because it is an AI agent that actively helps users configure Guardian -- it will suggest the wrong key.

**Recommendation:** Update all four files to reference `allowedExternalReadPaths` and `allowedExternalWritePaths`, with descriptions that distinguish between them.

---

### 7. Test Coverage

**Verdict: PASS (with notes)**

The new test file `tests/core/test_external_path_mode.py` is thorough with **26 tests across 5 classes**:

| Group | Tests | Coverage |
|-------|-------|----------|
| Config Parsing | 7 | Read mode, write mode, unmatched, both lists, empty, write-only, non-string entries |
| Mode Enforcement | 7 | Read/Write/Edit tool combinations with read and readwrite modes |
| extract_paths() External | 5 | External read extraction, non-allowed exclusion, project paths, write paths, mixed |
| zeroAccess on External | 3 | .env, .key, .pem files in external dirs still blocked |
| Backward Compatibility | 4 | Old key ignored, fallback has new keys, fallback no old key, old+new coexistence |

All 26 tests pass: `Ran 26 tests in 0.024s -- OK`

**Gaps noted:**
- No test for the bash guardian mode enforcement gap (item 8 below) -- this is a test for behavior that doesn't exist yet
- The old regression test `tests/regression/test_allowed_external.py` has a pre-existing `ModuleNotFoundError: No module named '_protection_utils'` and uses old config format; it needs to be rewritten or removed

---

### 8. Error Messages

**Verdict: PASS**

The deny message for write attempts on read-only external paths is clear and actionable:

```
External path is read-only: {filename}
Add this path to allowedExternalWritePaths to allow writes.
```

This is at `_guardian_utils.py:2306-2307`. It tells the user exactly what happened and how to fix it.

---

### 9. Old Key References (Codebase-Wide Search)

**Verdict: FAIL (see items 5, 6)**

Complete inventory of non-temp/non-archive files still referencing `allowedExternalPaths`:

| File | Status | Action Needed |
|------|--------|---------------|
| `assets/guardian.default.json:238` | **STALE** | Replace with new keys |
| `agents/config-assistant.md:150` | **STALE** | Update to new keys |
| `skills/config-guide/references/schema-reference.md:17,161` | **STALE** | Update to new keys |
| `README.md:131` | **STALE** | Update to new keys |
| `tests/regression/test_allowed_external.py` (throughout) | **STALE** | Rewrite or remove |
| `tests/README.md:64` | **STALE** | Update description |
| `tests/core/test_external_path_mode.py` | OK | References old key in backward-compat tests (intentional) |
| `hooks/scripts/_guardian_utils.py` | OK | Old key fully removed from logic |
| `hooks/scripts/bash_guardian.py` | OK | Only uses new function |
| `assets/guardian.schema.json` | OK | Old key fully removed |
| `temp/*`, `_archive/*` | N/A | Planning/archive files, low priority |

---

## Additional Issues Found

### CRITICAL: Bash Guardian Does Not Enforce External Path Mode

**Severity: CRITICAL**
**Files:** `hooks/scripts/bash_guardian.py` lines 522, 556, 563

The bash guardian's `extract_paths()` function calls `match_allowed_external_path(str(path))[0]` at three locations, extracting only the boolean (whether the path is in any allowed external list) and discarding the mode string ("read" or "readwrite").

Once extracted, external paths flow through the standard security checks:
- `match_zero_access()` -- works correctly (blocks all access)
- `match_read_only()` -- checks `readOnlyPaths` config, **NOT the external path mode**
- `match_no_delete()` -- checks `noDeletePaths` config

**The problem:** A path in `allowedExternalReadPaths` (meant to be read-only) is extracted into the path list. During enforcement, `match_read_only()` checks the `readOnlyPaths` config section, which is a completely separate configuration. Unless the user ALSO adds the external path to `readOnlyPaths`, write commands like `sed -i /external/file` will NOT be blocked.

**Contrast with `run_path_guardian_hook()`:** The Read/Write/Edit tool guardian at `_guardian_utils.py:2298-2308` correctly checks the mode:
```python
if ext_mode == "read" and tool_name.lower() in ("write", "edit"):
    # deny -- read-only external path
```

This mode check is completely absent from the bash guardian.

**Attack scenario:**
1. Config: `"allowedExternalReadPaths": ["/sibling-project/**"]`
2. User runs via bash: `sed -i 's/old/new/' /sibling-project/important.py`
3. `extract_paths()` extracts `/sibling-project/important.py` (matched by read list)
4. Bash guardian checks: not zero-access, not in readOnlyPaths, not a delete -- **ALLOWS the write**
5. The path was supposed to be read-only

**Recommendation:** After extracting external paths, the bash guardian must also track the mode and enforce it. Options:
- Store a mapping of `{path: mode}` alongside the path list
- Or check the mode at enforcement time by calling `match_allowed_external_path()` again when `is_write` is true
- At minimum: if an external path has mode "read" and the sub-command is a write, deny

---

## Summary of Issues

| # | Severity | Issue | Files Affected |
|---|----------|-------|----------------|
| 1 | **CRITICAL** | Bash guardian does not enforce read/write mode for external paths | `bash_guardian.py` |
| 2 | **HIGH** | Silent backward-compat break: old `allowedExternalPaths` silently ignored, no deprecation warning | `_guardian_utils.py` |
| 3 | **HIGH** | Default config template still uses old key | `assets/guardian.default.json` |
| 4 | **HIGH** | Docs and config assistant still reference old key | `README.md`, `agents/config-assistant.md`, `skills/.../schema-reference.md` |
| 5 | **MEDIUM** | API return type inconsistency (tuple vs bool) | `_guardian_utils.py` |
| 6 | **MEDIUM** | No migration path, no CHANGELOG, no version bump | Project-wide |
| 7 | **LOW** | Old regression test broken with pre-existing import error + old config format | `tests/regression/test_allowed_external.py` |

## External Validation

- **Codex clink:** Independently confirmed all findings. Highlighted the same critical issues: default config template with old key, silent backward-compat break, and stale documentation. Recommended deprecation shim with auto-mapping old key to `allowedExternalWritePaths`.
- **Gemini chat (vibe check):** Confirmed the bash guardian mode enforcement gap as the most critical issue. Noted that the tuple return type creates a Python truthiness landmine. Suggested additional investigation of `readOnlyPaths` vs external path mode precedence and path overlap resolution.

## Recommendations (Priority Order)

1. **Fix bash guardian mode enforcement** (CRITICAL): The bash guardian must respect the read/write distinction for allowed external paths. Without this, the split into ReadPaths/WritePaths provides no protection via the Bash tool.

2. **Add deprecation shim** (HIGH): In `load_guardian_config()`, detect `allowedExternalPaths` and either auto-map to `allowedExternalWritePaths` with a WARN log, or at minimum emit a clear warning that the key is deprecated.

3. **Update `guardian.default.json`** (HIGH): Replace old key with new split keys.

4. **Update all documentation** (HIGH): `README.md`, `agents/config-assistant.md`, `skills/config-guide/references/schema-reference.md`, `tests/README.md`.

5. **Add CHANGELOG entry and consider version bump** (MEDIUM): Document the breaking change.

6. **Rewrite or remove old regression test** (LOW): `tests/regression/test_allowed_external.py` is already broken (pre-existing) and uses old config format.
