# Security Review V1: Enhancement 1 & 2

## Reviewer: Security Reviewer V1
## Date: 2026-02-15
## Status: COMPLETE

---

## Executive Summary

Enhancement 1 (splitting `allowedExternalPaths` into `allowedExternalReadPaths`/`allowedExternalWritePaths`) is **correctly implemented** in the tool-hook path (`run_path_guardian_hook()`). The mode enforcement, check ordering, and fail-closed defaults are sound for Read/Write/Edit tools.

However, Enhancement 2 (bash guardian `extract_paths()` external path inclusion) introduces a **HIGH severity gap**: the bash guardian extracts external paths but **discards the mode**, meaning `allowedExternalReadPaths` entries become effectively writable through bash commands. A pre-existing gap in `extract_redirection_targets()` compounds this.

**Overall Assessment: Enhancement 1 PASS. Enhancement 2 has a material security gap that should be addressed before release.**

---

## Security Checklist

### 1. Fail-closed semantics: Missing/invalid config denies by default

**VERDICT: PASS**

**Evidence:**

- **Fallback config** (`_guardian_utils.py:415-416`): Both `allowedExternalReadPaths: []` and `allowedExternalWritePaths: []` are empty arrays. Empty arrays mean no external access is granted -- fail-closed.
  ```python
  "allowedExternalReadPaths": [],
  "allowedExternalWritePaths": [],
  ```

- **`match_allowed_external_path()`** (`_guardian_utils.py:1239-1246`): Uses `config.get("allowedExternalWritePaths", [])` and `config.get("allowedExternalReadPaths", [])` -- defaults to empty list if key is missing. Empty list means `any(...)` returns `False` -- fail-closed.

- **`isinstance(p, str)` guard** (`_guardian_utils.py:1240, 1244`): Non-string entries in the arrays are silently skipped, which is fail-closed behavior (invalid entries cannot grant access).

- **Schema defaults** (`guardian.schema.json:115, 123`): Both arrays have `"default": []`.

- **`validate_guardian_config()`** (`_guardian_utils.py:715`): Both new keys are in the `path_sections` validation list, receiving the same string-array validation as other path tiers.

No issues found. Fail-closed semantics are preserved.

---

### 2. Mode enforcement completeness: Can any code path bypass the read-only check?

**VERDICT: FAIL** -- HIGH severity gap in bash guardian

**Evidence:**

**Tool hooks (PASS):** `run_path_guardian_hook()` (`_guardian_utils.py:2297-2309`) correctly enforces mode:
```python
matched, ext_mode = match_allowed_external_path(path_str)
if matched:
    if ext_mode == "read" and tool_name.lower() in ("write", "edit"):
        # DENY -- correctly blocks Write/Edit on read-only external paths
```
This covers the Read, Write, and Edit tool entrypoints (`read_guardian.py`, `write_guardian.py`, `edit_guardian.py`).

**Bash guardian (FAIL):** `extract_paths()` in `bash_guardian.py` discards the mode:
```python
# Line 522, 556, 563 -- only [0] (boolean) is used, mode is discarded:
elif match_allowed_external_path(str(path))[0]:
    paths.append(path)
```

Once extracted, the path enters the enforcement loop (`bash_guardian.py:1036-1069`). This loop checks:
- `is_symlink_escape()` -- catches symlink attacks
- `match_zero_access()` -- checks `zeroAccessPaths` config
- `match_read_only()` -- checks `readOnlyPaths` config (NOT `allowedExternalReadPaths`)
- `match_no_delete()` -- checks `noDeletePaths` config

**The loop never re-checks the external path's mode.** `match_read_only()` only consults the `readOnlyPaths` config key, not `allowedExternalReadPaths`. This means:

**Attack scenario:**
1. Config: `allowedExternalReadPaths: ["/sibling-project/**"]`, `allowedExternalWritePaths: []`
2. User runs: `sed -i 's/old/new/g' /sibling-project/important.py`
3. `extract_paths()` extracts `/sibling-project/important.py` (because `match_allowed_external_path()[0]` is True)
4. `is_write_command("sed -i ...")` returns True
5. `match_read_only("/sibling-project/important.py")` returns False (it's not in `readOnlyPaths`)
6. Write proceeds -- **read-only protection bypassed**

**Callers of `match_allowed_external_path`:**
| Location | Uses mode? | Verdict |
|----------|-----------|---------|
| `_guardian_utils.py:2297` (run_path_guardian_hook) | Yes -- `ext_mode` checked | PASS |
| `bash_guardian.py:522` (extract_paths, flag-concat) | No -- `[0]` only | FAIL |
| `bash_guardian.py:556` (extract_paths, glob) | No -- `[0]` only | FAIL |
| `bash_guardian.py:563` (extract_paths, normal) | No -- `[0]` only | FAIL |

---

### 3. zeroAccess still wins: Path in both allowedExternalWritePaths and zeroAccessPaths

**VERDICT: PASS** (for tool hooks); **PASS** (for bash guardian)

**Evidence:**

**Tool hooks:** In `run_path_guardian_hook()`, the check order is:
1. Symlink escape (line 2286)
2. Path within project / external path check (line 2294-2321) -- if external, falls through
3. Self-guardian (line 2323)
4. **Zero access (line 2332)** -- checked AFTER external path is allowed through
5. Read-only (line 2347)

If a path matches `allowedExternalWritePaths` AND `zeroAccessPaths`, the external check at step 2 allows it to "fall through" (line 2314 comment: "Fall through to remaining checks"), and zeroAccess at step 4 blocks it. **Correct.**

**Bash guardian:** The enforcement loop (`bash_guardian.py:1047-1053`) checks `match_zero_access()` on ALL extracted paths, including external ones. zeroAccess patterns match on filename (e.g., `.env`, `*.pem`), which works regardless of whether the path is internal or external. **Correct.**

**Test coverage:** Tests 20-22 in `test_external_path_mode.py` verify that `match_zero_access()` catches `.env`, `*.key`, and `*.pem` files in allowed external directories. Tests are unit-level (call both functions separately) rather than integration-level, but the logic is sound.

---

### 4. Bash guardian path extraction: Could an attacker craft a command where the external path is extracted but NOT checked?

**VERDICT: PARTIAL FAIL** -- see item #2 above and additional note below

**Evidence:**

Once an external path is extracted by `extract_paths()`, it enters the same enforcement loop as internal paths. The loop correctly applies:
- `match_zero_access()` -- applied to ALL paths
- `match_read_only()` -- applied when `is_write` is True (but only checks `readOnlyPaths`, not external read mode)
- `match_no_delete()` -- applied when `is_delete` is True

The extracted path IS checked. The problem is that the check is incomplete -- it doesn't enforce the external read-only mode (covered in item #2).

**Additional concern -- `extract_redirection_targets()`:**
`extract_redirection_targets()` (`bash_guardian.py:431-475`) does NOT filter by project boundary OR external path allowlist. It appends ALL redirection targets. This means:
```bash
echo "malicious" > /etc/cron.d/backdoor
```
The path `/etc/cron.d/backdoor` would be extracted as a redirection target, enter the enforcement loop, and... only be checked against `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths`. If none of those match, it passes.

**However:** This is a **pre-existing issue**, not introduced by E1/E2. The E2 implementer correctly noted this as out-of-scope (impl-e2-output.md line 101). The pre-existing behavior was that `extract_redirection_targets()` collected all paths, and the enforcement loop had no "outside project" boundary check. E2 did not change this function.

**Still, the E2 changes create an inconsistency:** `extract_paths()` now correctly includes allowed external paths (and excludes non-allowed ones), but `extract_redirection_targets()` includes ALL paths regardless. This inconsistency could confuse future maintainers.

---

### 5. Symlink escape: Are symlink checks still before external path checks?

**VERDICT: PASS**

**Evidence:**

**Tool hooks:** In `run_path_guardian_hook()`:
- Line 2286: `is_symlink_escape()` check -- **first**
- Line 2294: `is_path_within_project()` / external path check -- **second**

Symlink escape is checked before the external path allowlist is consulted. A symlink inside the project pointing to an external allowed path would be caught. **Correct.**

**Bash guardian:** In the enforcement loop:
- Line 1040: `is_symlink_escape()` -- **first** in the loop
- Lines 1047+: `match_zero_access()`, `match_read_only()`, etc.

The bash guardian does not check external paths in the enforcement loop (it only checks them during extraction). The symlink check in the loop applies to all extracted paths. **Correct.**

**Pre-existing caveat (not introduced by E1/E2):** `is_symlink_escape()` (`_guardian_utils.py:968-980`) returns `False` on exception (fail-open), as documented in CLAUDE.md. This is a known pre-existing gap.

---

### 6. Path traversal: Could `../../` in external paths bypass protections?

**VERDICT: PASS**

**Evidence:**

`match_path_pattern()` (`_guardian_utils.py:1126-1128`) normalizes both the path and pattern through `normalize_path_for_matching()` which calls `expand_path()` which calls `Path.resolve()`. `Path.resolve()` resolves `../` components to their canonical form.

Example: If `allowedExternalReadPaths: ["/sibling/**"]`, and the request is for `/sibling/../../etc/passwd`:
1. `Path("/sibling/../../etc/passwd").resolve()` -> `/etc/passwd`
2. Pattern `/sibling/**` does not match `/etc/passwd`
3. External path check returns `(False, "")` -- blocked

In `run_path_guardian_hook()`, the path is resolved at line 2279 via `resolve_tool_path()` before any checks are performed.

In `extract_paths()`, paths are resolved via `Path(expanded_part)` and then checked. If a path contains `../`, it would resolve to its canonical form before being checked against `match_allowed_external_path()`.

**No traversal bypass found.**

---

### 7. Input validation: Non-string entries, null entries, empty strings

**VERDICT: PASS**

**Evidence:**

- **Non-string entries in config arrays:** `match_allowed_external_path()` uses `isinstance(p, str)` guard (lines 1240, 1244). Non-string entries (int, None, dict, bool, list) are silently skipped. Test #7 (`test_non_string_entries_ignored`) verifies this.

- **Empty strings in arrays:** An empty string `""` would be `isinstance("", str)` = True, so it would reach `match_path_pattern("", path)`. Inside `match_path_pattern`, `normalize_path_for_matching("")` would expand to the project directory (via `expand_path`), and `fnmatch.fnmatch(norm_path, "")` would return False for any non-empty path. **Safe** -- empty string patterns don't match.

- **`validate_guardian_config()`** (line 722): Reports non-string entries as validation errors, giving users feedback about misconfiguration.

- **Null bytes in paths:** Checked in `run_path_guardian_hook()` at line 2273. Not relevant to the config parsing, but the enforcement path is covered.

---

### 8. No regression: Existing security checks for project-internal paths

**VERDICT: PASS**

**Evidence:**

The changes are additive:

1. **`match_allowed_external_path()`** is a new function. It doesn't modify any existing function.

2. **`run_path_guardian_hook()`** change is within the existing `if not is_path_within_project()` block (line 2294). For project-internal paths, this block is never entered. No regression.

3. **`extract_paths()`** changes add `elif` branches after existing checks:
   - Line 522: `elif` after project-internal and allow_nonexistent checks
   - Line 556: `elif` after project-internal check in glob loop
   - Line 563: `elif` after project-internal and allow_nonexistent checks

   These are only reached if the path is NOT project-internal. For project-internal paths, the existing `if` branches handle them first. No regression.

4. **`validate_guardian_config()`** adds two new keys to `path_sections` list. Existing keys unchanged.

5. **Fallback config** replaces `allowedExternalPaths: []` with two new keys. The old key had no consumers in the new code. No regression.

6. **Test results** confirm: 180/180 core tests pass, 143/143 adversarial tests pass, 20/20 cross-model tests pass. Pre-existing failures are unrelated.

---

## Issues Found

### ISSUE 1: Bash guardian does not enforce read-only mode for external paths
- **Severity: HIGH**
- **Location:** `bash_guardian.py:522, 556, 563` (extraction) and `bash_guardian.py:1036-1069` (enforcement loop)
- **Description:** `extract_paths()` uses `match_allowed_external_path()[0]` (boolean only), discarding the mode string. The enforcement loop checks `match_read_only()` which only consults `readOnlyPaths`, not `allowedExternalReadPaths`. A write command (e.g., `sed -i`, `cp`, `tee`, `echo >`) targeting a path in `allowedExternalReadPaths` will succeed.
- **Impact:** `allowedExternalReadPaths` is effectively `allowedExternalWritePaths` for bash commands. The read-only restriction only applies to the Read/Write/Edit tools.
- **Recommendation:** In the bash guardian enforcement loop, add a check: for each extracted path that is outside the project, call `match_allowed_external_path()` to get the mode, and deny writes when `ext_mode == "read"` and `is_write or is_delete`.

### ISSUE 2: `extract_redirection_targets()` not updated for external path filtering
- **Severity: MEDIUM** (pre-existing, but now inconsistent)
- **Location:** `bash_guardian.py:431-475`
- **Description:** `extract_redirection_targets()` appends all resolved paths without checking project boundaries or external allowlists. This was the pre-existing behavior, but E2's changes to `extract_paths()` now create an inconsistency: argument paths are filtered (internal OR allowed-external only), but redirection targets are not filtered at all.
- **Impact:** Bash commands using redirections can target arbitrary external paths. However, the enforcement loop still applies `zeroAccessPaths` checks to these paths. The inconsistency is more of a design debt than a new vulnerability.
- **Recommendation:** Apply the same external path filtering to `extract_redirection_targets()` in a follow-up enhancement. Note: this is acknowledged as out-of-scope by the E2 implementer.

### ISSUE 3: Delete semantics under-specified for external paths
- **Severity: MEDIUM**
- **Location:** `bash_guardian.py:1063-1069` and `_guardian_utils.py:2294-2314`
- **Description:** The mode check in `run_path_guardian_hook()` only checks for `"write"` and `"edit"` tool names. If a hypothetical "Delete" tool were added, it would not be caught. In the bash guardian, delete commands on `allowedExternalReadPaths` are not blocked (same as Issue 1 -- mode is not checked).
- **Impact:** Low for now (no Delete tool exists). But delete commands via bash (`rm`, `rmdir`) on read-only external paths would succeed.
- **Recommendation:** When fixing Issue 1, treat `is_delete` the same as `is_write` for external mode enforcement.

### ISSUE 4: Test coverage gap -- mode enforcement not tested through actual code flow
- **Severity: LOW** (informational)
- **Location:** `tests/core/test_external_path_mode.py` Group 2
- **Description:** The `TestModeEnforcement` class tests a `_would_deny()` helper that reproduces the conditional from `run_path_guardian_hook()`, but does not actually call `run_path_guardian_hook()` (due to `sys.exit()`). Similarly, there are no tests verifying bash guardian behavior when a write command targets a read-only external path -- which would have caught Issue 1.
- **Impact:** The test suite gives false confidence about bash guardian mode enforcement.
- **Recommendation:** Add subprocess-based tests that invoke the bash guardian with write commands targeting read-only external paths and verify the deny response.

---

## Positive Findings

1. **Tool hook enforcement is correct and explicit.** `run_path_guardian_hook()` properly checks `ext_mode == "read"` and blocks Write/Edit. The log messages are clear and the deny response directs users to the correct config key.

2. **Check ordering is correct.** Symlink escape is checked first, then external path, then self-guardian, then zeroAccess, then readOnly. zeroAccess always overrides external path allowances.

3. **Fail-closed defaults are correct.** Empty fallback arrays, `config.get()` defaults to `[]`, `isinstance` guards on non-string entries.

4. **Schema is well-defined.** Both new keys have clear descriptions, `default: []`, and `items: { type: string }`.

5. **No regressions.** All existing test suites pass with zero regressions.

6. **Clean separation.** The `match_allowed_external_path()` function is simple, well-documented, and follows the same pattern as `match_zero_access()`, `match_read_only()`, etc.

---

## Cross-validation

The Codex code reviewer independently identified the same top issues:
1. Bash redirection targets not filtered (confirmed as pre-existing)
2. Bash extraction discards external mode (confirmed as Issue 1)
3. Bash enforcement never re-checks external mode (confirmed as Issue 1)

The vibe-check meta-review also flagged the bash mode enforcement gap as the critical item to investigate.

---

## Overall Security Assessment

| Component | Assessment |
|-----------|-----------|
| Enhancement 1 (config split + tool hooks) | **PASS** -- correctly implemented, fail-closed, well-tested |
| Enhancement 2 (bash extract_paths) | **CONDITIONAL PASS** -- extraction logic is correct, but mode enforcement gap (Issue 1) must be addressed |
| Schema changes | **PASS** -- clean, consistent |
| Test coverage | **ADEQUATE** -- 26 tests cover the new functionality; gap noted for bash mode enforcement |

**Recommendation:** Fix Issue 1 (HIGH) before merging. Issues 2-3 (MEDIUM) can be addressed in follow-up work. Issue 4 (LOW) should inform the test plan for the Issue 1 fix.

---

## Files Reviewed

| File | Lines Reviewed | Verdict |
|------|---------------|---------|
| `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py` | 415-416, 714-723, 1110-1170, 1221-1246, 2250-2361 | PASS |
| `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py` | 45-60, 306-365, 431-475, 478-568, 670-685, 1000-1079 | CONDITIONAL PASS (Issue 1) |
| `/home/idnotbe/projects/claude-code-guardian/assets/guardian.schema.json` | 109-124 | PASS |
| `/home/idnotbe/projects/claude-code-guardian/tests/core/test_external_path_mode.py` | 1-696 (full file) | PASS (adequate, gap noted) |
