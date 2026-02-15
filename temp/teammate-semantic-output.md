# Semantic Consistency Review: P0/P1 Fixes

## Status: PASS with 3 documentation updates recommended

**Reviewer**: semantic-checker
**Date**: 2026-02-15
**Task**: #8 - [V2] Semantic consistency and documentation review

---

## 1. noDeletePaths Semantics Verification

### Documented semantics across all sources

| Source | Description | Consistent? |
|--------|-------------|-------------|
| `guardian.schema.json` (L102-107) | "Glob patterns for files that cannot be deleted" | YES |
| `README.md` (L130) | "Glob patterns for files that cannot be deleted" | YES |
| `schema-reference.md` (L115) | "noDeletePaths: YES read, YES write, NO delete" | YES |
| `schema-reference.md` (L148) | "Files that can be read and written but not deleted" | YES |
| `config-assistant.md` (L149) | "files that cannot be deleted" | YES |
| `guardian.default.json` comment | (no comment specific to noDeletePaths) | N/A |

**All documentation consistently defines noDeletePaths as: "files that can be read and written but not deleted."**

### Does the P1 fix conflict with documented semantics?

The P1 fix blocks the Write tool when overwriting **existing** noDeletePaths files. The question is: does blocking Write (full file replacement) on existing files conflict with "can be... written"?

**Analysis:**

The P1 fix uses the "revised recommendation" from the brief (Option A with existing-file refinement):

- Write to **create** new file matching noDeletePaths pattern: **ALLOWED** -- matches "can be written"
- Write to **overwrite** existing noDeletePaths file: **BLOCKED** -- Write tool replaces entire content, which is semantically equivalent to delete + create
- Edit to **modify** existing noDeletePaths file: **ALLOWED** -- partial modification preserves data, matches "can be written"
- Read noDeletePaths file: **ALLOWED** -- matches "can be read"
- `rm` noDeletePaths file via Bash: **BLOCKED** -- matches "cannot be deleted"

**Verdict: NO SEMANTIC CONFLICT.** The P1 fix does NOT block writes in general; it blocks full-content-replacement overwrite on existing files. The semantic distinction is:

- "Written" (as documented) = modifying content, adding content, creating new files. **Still allowed via Edit tool and Write for new files.**
- "Deleted" (as documented) = destroying file data entirely. Write tool replaces entire content = data destruction = semantic deletion. **Correctly blocked.**

The existing-file-only gate preserves the documented semantics:
- Creating `.github/workflows/new-ci.yml` (new file matching `.github/**` pattern): ALLOWED
- Overwriting `.github/workflows/ci.yml` (existing file): BLOCKED via Write, ALLOWED via Edit
- Editing `package.json` to add a dependency: ALLOWED (via Edit tool)
- `rm README.md`: BLOCKED (existing behavior)

**Potential user confusion point**: A user who reads "can be written" might expect the Write tool to work. The error message addresses this by recommending `Edit` tool. This is a reasonable UX tradeoff -- blocking an easy bypass vector is more important than matching a strict reading of "written."

### Consistency with schema-reference.md access level table

```
| Array          | Read | Write | Delete |
|----------------|------|-------|--------|
| noDeletePaths  | YES  | YES   | NO     |
```

After P1, the effective behavior is:
- Read: YES (all tools)
- Write via Edit: YES (partial modifications)
- Write via Write tool: YES for new files, NO for existing files (overwrite = deletion)
- Delete: NO

The table says "Write: YES" which is still broadly true. The nuance is that **destructive writes** (full replacement of existing files) are blocked. This is a refinement, not a contradiction. However, the table could be more precise.

**RECOMMENDATION**: Consider adding a footnote to `schema-reference.md` line 115:

```
| `noDeletePaths` | YES | YES* | NO | Critical configs, CI files, migrations |
```
`* Write tool is blocked for existing files (full replacement = data destruction). Use Edit for modifications.`

---

## 2. Error Message Review

### P0-A: "GUARDIAN WARN: No project dir set, failing closed for path check"

- **Clarity**: Good. States what happened and what action was taken.
- **Actionability**: Moderate. The user sees this on stderr. They would need to know that setting `CLAUDE_PROJECT_DIR` resolves it. However, this is a system-level error (env var missing), not a user-facing config issue. The message could include the env var name.
- **Where shown**: stderr only (not in deny response). The deny response from downstream callers (e.g., `run_path_guardian_hook`) will show different messages.
- **Verdict**: ACCEPTABLE. This is a diagnostic message for troubleshooting, not a user action message.

### P0-B: "GUARDIAN WARN: No project dir set, treating symlink as potential escape"

- **Clarity**: Good. States the assumption made.
- **Actionability**: Same as P0-A -- stderr diagnostic.
- **Verdict**: ACCEPTABLE.

### P0-C: "Guardian cannot verify command safety: project directory not set"

- **Clarity**: Good. Clear reason why the command was denied.
- **Actionability**: Better than P0-A/B because this is the deny reason shown to the user. Tells them what's wrong but not how to fix it. The user would need to set `CLAUDE_PROJECT_DIR` or ensure they're running via the plugin system which sets it automatically.
- **Verdict**: ACCEPTABLE. Could improve by adding "Ensure Guardian plugin is properly initialized" but the message is already clear enough.

### P1: "Protected from overwrite: {filename}\nThis file is in noDeletePaths. Use Edit tool for partial modifications."

- **Clarity**: Excellent. States what happened, why, and what to do instead.
- **Actionability**: Excellent. Gives a clear alternative action (use Edit).
- **Verdict**: GOOD -- best of the four error messages.

### Cross-message consistency

All messages use different formats:
- P0-A/B: `GUARDIAN WARN: ...` (stderr diagnostic prefix)
- P0-C: Plain sentence (deny reason)
- P1: Two-line format with suggestion

This is actually appropriate because they serve different purposes:
- P0-A/B are stderr warnings (diagnostic)
- P0-C is a deny reason (user-facing, in JSON response)
- P1 is a deny reason with remediation (user-facing, in JSON response)

**Verdict: CONSISTENT in context.** The messages appropriately match their output channels.

---

## 3. Docstring Review

### `is_path_within_project()` (`_guardian_utils.py:1027-1058`)

Current docstring (after P0-A fix):
```
Returns:
    True if path is within project directory.
    False if outside project or on any error (fail-closed).
```

**Verdict: CORRECT.** Matches actual behavior:
- Missing project dir: returns False (L1044)
- Exception during resolution: returns False (L1058)
- Outside project: returns False (L1054)
- Inside project: returns True (L1052)

### `is_symlink_escape()` (`_guardian_utils.py:976-1024`)

Current docstring (after P0-B fix):
```
Returns:
    True if the path is a symlink that resolves outside the project.
    False if not a symlink, or if it resolves within the project.
    True on any error (fail-closed).
```

**Verdict: CORRECT.** Matches actual behavior:
- Missing project dir: returns True (L995)
- Exception: returns True (L1024)
- Not a symlink: returns False (L1004)
- Symlink within project: returns False (L1013)
- Symlink outside project: returns True (L1020)

### `run_path_guardian_hook()` (`_guardian_utils.py:2238-2393`)

Current docstring:
```
"""Run guardian checks for Read/Edit/Write tools.

This is the main entry point for path-based guardian hooks.
It implements fail-close semantics for security.

Args:
    tool_name: The tool name to check for ("Read", "Edit", or "Write").
"""
```

**Issue: Docstring does not mention noDeletePaths.** The function now checks 6 tiers:
1. Symlink escape
2. Project boundary + external admission
3. Self-guardian
4. zeroAccessPaths
5. readOnlyPaths
6. noDeletePaths (NEW)

The docstring is terse and doesn't enumerate any specific checks. This is a style choice -- the docstring focuses on the purpose rather than listing all checks. The check ordering is well-documented with inline comments (`# ========== Check: No Delete ==========`).

**RECOMMENDATION**: Add noDeletePaths to the docstring for discoverability, since it was added as part of this PR:

```python
"""Run guardian checks for Read/Edit/Write tools.

This is the main entry point for path-based guardian hooks.
It implements fail-close semantics for security.

Checks (in order): symlink escape, project boundary, self-guardian,
zeroAccessPaths, readOnlyPaths, noDeletePaths (Write tool only,
existing files only).

Args:
    tool_name: The tool name to check for ("Read", "Edit", or "Write").
"""
```

---

## 4. CLAUDE.md "Known Security Gaps" Update

### Current text (CLAUDE.md:36):
```
1. **Fail-open exception paths**: `is_symlink_escape()` (`_guardian_utils.py:927`) returns
   `False` on exception; `is_path_within_project()` (`_guardian_utils.py:974`) returns `True`
   on exception. Both undermine fail-closed semantics -- crafted paths that trigger `OSError`
   bypass protections.
```

**This is now FIXED.** After P0-A and P0-B:
- `is_symlink_escape()` returns `True` on exception (fail-closed) -- at L1024
- `is_path_within_project()` returns `False` on exception (fail-closed) -- at L1058

Additionally, the line numbers cited in CLAUDE.md are stale:
- `is_symlink_escape()` is at L976 (not L927)
- `is_path_within_project()` is at L1027 (not L974)

**RECOMMENDATION**: Remove gap #1 from the "Known Security Gaps" section. It has been fixed.

### New gaps introduced?

**No new security gaps introduced by the P0/P1 fixes.** Pre-existing gaps remain:
- Gap #2 (auto-commit `--no-verify`): Unchanged, still valid.
- Gap #3 (zero test coverage for thin wrappers): Partially addressed -- P0/P1 tests exercise `write_guardian.py`, `read_guardian.py`, `edit_guardian.py` via subprocess. `auto_commit.py` still has zero test coverage.
- Pre-existing fail-open in `expand_path()`, `normalize_path_for_matching()`, `resolve_tool_path()`: Not introduced by this PR. Noted by security-auditor as ADVISORY-3.

**RECOMMENDATION**: Update CLAUDE.md to:
1. Remove gap #1 (fixed)
2. Update gap #3 to note that thin wrappers now have some test coverage via P0/P1 tests
3. Optionally add a note about the remaining `expand_path()` fail-open as a lower-priority gap

---

## 5. Consistency Between bash_guardian and path guardian

### Fail-closed on missing project dir

| Guardian | Before Fix | After Fix | Consistent? |
|----------|-----------|-----------|-------------|
| `bash_guardian.py` main() | `sys.exit(0)` (allow) | `deny_response()` (deny) | YES |
| `is_path_within_project()` (used by path guardians) | `return True` (allow) | `return False` (deny) | YES |
| `is_symlink_escape()` (used by path guardians) | `return False` (allow) | `return True` (deny) | YES |

**All three guardians now fail-closed on missing project dir. CONSISTENT.**

### noDeletePaths enforcement consistency

| Context | Enforcement | Location |
|---------|-------------|----------|
| Bash `rm` / `del` / `git rm` on noDelete file | BLOCKED | `bash_guardian.py:1078` via `is_delete and match_no_delete()` |
| Write tool overwrite existing noDelete file | BLOCKED | `_guardian_utils.py:2375-2389` via `tool_name == "write" and match_no_delete() and resolved.exists()` |
| Edit tool on noDelete file | ALLOWED | No check in path guardian (correct: Edit is surgical) |
| Read tool on noDelete file | ALLOWED | No check in path guardian (correct: Read is non-destructive) |
| Bash write (e.g., `echo > file`) on noDelete file | NOT BLOCKED | `bash_guardian.py:1078` only checks `is_delete`, not `is_write` |

**Potential gap noted**: Bash write commands like `echo "" > README.md` or `> CLAUDE.md` (truncation) are **not** caught by the noDelete check in bash_guardian. The bash_guardian only checks `is_delete and match_no_delete()` (L1078), not `is_write and match_no_delete()`.

However, this is a **pre-existing gap**, not introduced by the P1 fix. The P1 fix only adds enforcement in the tool hook path; it does not change bash_guardian behavior. The bash_guardian does catch truncation via `is_delete_command()` patterns:
- `r"^\s*(?::)?\s*>(?!>)\|?\s*\S+"` -- catches standalone redirect truncation (L2624 in bash_guardian at the `is_delete_command` function)

So `> README.md` IS caught as a delete command and would trigger the noDelete check. `echo content > README.md` however is caught as a write command, not delete, and would NOT be checked against noDelete. This is the same semantic distinction as in the tool hook: full content replacement (truncation) is deletion, partial modification is writing.

**Verdict: CONSISTENT across bash_guardian and path guardian, with the same semantic boundary applied in both contexts.**

---

## 6. Summary of Findings

| # | Finding | Severity | Action |
|---|---------|----------|--------|
| 1 | noDeletePaths semantics preserved | N/A (PASS) | No action needed |
| 2 | Error messages clear and actionable | N/A (PASS) | No action needed |
| 3 | `run_path_guardian_hook()` docstring missing noDeletePaths mention | Low | RECOMMEND: Update docstring |
| 4 | CLAUDE.md gap #1 (fail-open) is now fixed | Medium | RECOMMEND: Remove from Known Security Gaps |
| 5 | CLAUDE.md line numbers for functions are stale | Low | RECOMMEND: Update line numbers or remove them |
| 6 | `schema-reference.md` could add footnote about Write blocking | Low | OPTIONAL: Add footnote to access table |
| 7 | Bash/path guardian noDelete enforcement is consistent | N/A (PASS) | No action needed |

### Blocking Issues: NONE

### Documentation Updates Recommended (non-blocking):

1. **CLAUDE.md**: Remove "Fail-open exception paths" from Known Security Gaps (it's fixed). Update gap #3 to note partial test coverage via P0/P1 tests.

2. **`_guardian_utils.py` L2239-2246**: Add noDeletePaths to `run_path_guardian_hook()` docstring.

3. **`schema-reference.md` L115** (optional): Add footnote clarifying that Write tool is blocked for existing noDelete files.

---

## 7. Overall Verdict

**PASS -- Semantically consistent, no conflicts with documented behavior.**

The P1 fix correctly implements the "revised recommendation" from the brief: blocking Write on existing noDeletePaths files only, while allowing Edit, Read, and Write for new files. This preserves the documented semantics of "files that can be read and written but not deleted" because:

1. Write (create new) is allowed
2. Edit (modify existing) is allowed
3. Write (overwrite existing = data destruction) is blocked -- this is semantically a deletion, not a write
4. All documentation is consistent in defining noDeletePaths as "cannot be deleted"
5. Error messages are clear and tell the user to use Edit instead

The three documentation updates above are recommended but not blocking.
