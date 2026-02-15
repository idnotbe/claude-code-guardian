# Guardian P0/P1 Fix Brief (v2 — post-verification)

> Created: 2026-02-15
> Updated: 2026-02-15 (incorporated 2 rounds of independent verification + 4 cross-model reviews)
> Target repo: /home/idnotbe/projects/claude-code-guardian
> Purpose: Fix security issues discovered during ops project config analysis
> Open this file in a Claude Code session in the guardian project to execute

---

## Background

During Guardian config analysis for the ops project, source code review revealed security issues in the path protection pipeline. Cross-model validation (Codex 5.3 + Gemini 3 Pro) confirmed all findings. Two rounds of independent verification completed with corrections incorporated.

Analysis files (in ops/temp/):
- `guardian-path-tier-analysis.md` — Control flow analysis
- `guardian-architecture-improvements.md` — Full improvement catalog
- `guardian-p0p1-brief-v1-review.md` — V1 verification (accuracy review)
- `guardian-p0p1-brief-v2-review.md` — V2 verification (completeness review)

## IMPORTANT: Verification Corrections Applied
The following bugs/gaps were found during verification and are now incorporated:
1. P1 code used `Path(file_path).exists()` (wrong — CWD-relative) → fixed to `resolved.exists()`
2. `run_path_guardian_hook()` starts at line 2231, not ~2330 → line refs corrected
3. `log_guardian()` is a no-op when project dir is missing → fix code now uses stderr
4. Added P0-C: bash_guardian.py also fails open on missing project dir
5. Added related: `expand_path()` and `normalize_path_for_matching()` fail-open patterns

---

## P0-A: `is_path_within_project()` Fail-Open on Exception

### Location
`hooks/scripts/_guardian_utils.py`, function `is_path_within_project()` (~line 1023-1051)

### Current Behavior
```python
def is_path_within_project(path: str) -> bool:
    project_dir = get_project_dir()
    if not project_dir:
        return True  # ← PROBLEM: No project dir = allow everything

    try:
        resolved = expand_path(path)
        project_resolved = Path(project_dir).resolve()
        try:
            resolved.relative_to(project_resolved)
            return True
        except ValueError:
            return False
    except Exception as e:
        log_guardian("WARN", f"Error checking if path is within project '{path}': {e}")
        return True  # ← PROBLEM: Exception = allow everything
```

### Problem
Two fail-open paths:
1. `if not project_dir: return True` — If CLAUDE_PROJECT_DIR is not set, ALL paths treated as "inside project", bypassing the entire external admission gate
2. `except Exception: return True` — Any exception during path resolution treats unknown path as inside project

### Impact
- **CRITICAL**: Bypasses the admission gate entirely
- An external path `/etc/passwd` could be treated as "inside project" if path resolution errors out
- Undermines the foundation of the "Admission Gate + Global Policy" architecture

### Proposed Fix
```python
def is_path_within_project(path: str) -> bool:
    project_dir = get_project_dir()
    if not project_dir:
        # SECURITY: No project dir = can't verify boundaries, deny by default
        # NOTE: log_guardian() is a no-op when project dir is missing (line 1315-1318),
        # so we also emit to stderr to ensure visibility
        print("GUARDIAN WARN: No project dir set, failing closed for path check", file=sys.stderr)
        return False  # ← Fail-closed

    try:
        resolved = expand_path(path)
        project_resolved = Path(project_dir).resolve()
        try:
            resolved.relative_to(project_resolved)
            return True
        except ValueError:
            return False
    except Exception as e:
        # SECURITY: Error during resolution = treat as outside project (fail-closed)
        log_guardian("WARN", f"Error checking if path is within project '{path}': {e}")
        return False  # ← Fail-closed
```

### Considerations
- **Usability risk**: If `CLAUDE_PROJECT_DIR` is unset (e.g., subagent loses env var), ALL file operations would be blocked. This is intentional — failing open is worse.
- **Existing behavior**: The docstring already says "False if outside project or on error" but the code returns True. The fix aligns code with documented intent.
- **log_guardian() no-op**: `log_guardian()` returns early when `CLAUDE_PROJECT_DIR` is unset (line 1315-1318). The `if not project_dir` branch must use `print(..., file=sys.stderr)` instead. The `except Exception` branch can still use `log_guardian()` since project_dir exists at that point.

---

## P0-B: `is_symlink_escape()` Fail-Open on Exception

### Location
`hooks/scripts/_guardian_utils.py`, function `is_symlink_escape()` (~line 976-1021)

### Current Behavior
```python
def is_symlink_escape(path: str) -> bool:
    project_dir = get_project_dir()
    if not project_dir:
        return False  # ← PROBLEM: No project dir = assume safe

    try:
        # ... symlink check logic ...
    except Exception as e:
        log_guardian("WARN", f"Error checking symlink escape for {path}: {e}")
        return False  # ← PROBLEM: Exception = assume safe (no escape)
```

### Problem
Two fail-open paths:
1. `if not project_dir: return False` — No project dir = symlinks assumed safe
2. `except Exception: return False` — Error during symlink check = assumed safe

### Impact
- **CRITICAL**: A malicious symlink like `project/link -> /etc/shadow` could bypass detection if symlink resolution errors out
- Combined with P0-A, both boundary checks fail open, completely removing the security perimeter

### Proposed Fix
```python
def is_symlink_escape(path: str) -> bool:
    project_dir = get_project_dir()
    if not project_dir:
        # SECURITY: No project dir = can't verify symlink safety, assume escape
        # NOTE: log_guardian() is a no-op when project dir is missing, use stderr
        print("GUARDIAN WARN: No project dir set, treating symlink as potential escape", file=sys.stderr)
        return True  # ← Fail-closed (assume escape)

    try:
        # ... existing symlink check logic unchanged ...
    except Exception as e:
        # SECURITY: Error during symlink check = assume escape (fail-closed)
        log_guardian("WARN", f"Error checking symlink escape for {path}: {e}")
        return True  # ← Fail-closed (assume escape)
```

### Considerations
- **Usability risk**: If an exception fires on a non-symlink path (unlikely but possible on permission errors), the operation would be blocked. This is confusing but safe.
- **Error messaging**: After this fix, the deny message would say "Symlink points outside project" when the real cause may be an exception during path resolution. Consider a distinct error message: "Unable to verify path safety (possible symlink escape): {path}" to avoid misleading users.
- **log_guardian() no-op**: Same as P0-A — the `if not project_dir` branch must use stderr.

---

## P0-C: `bash_guardian.py` Fails Open on Missing Project Dir

### Location
`hooks/scripts/bash_guardian.py`, main execution path (~line 960-962)

### Current Behavior
```python
project_dir_str = get_project_dir()
if not project_dir_str:
    sys.exit(0)  # ← PROBLEM: No project dir = allow ALL bash commands
```

### Problem
When `CLAUDE_PROJECT_DIR` is unset, the bash guardian exits with code 0 (allow), silently permitting ALL bash commands without any path or pattern checks.

### Impact
- **CRITICAL**: Combined with P0-A/P0-B, this means if `CLAUDE_PROJECT_DIR` is unset, ALL protection mechanisms (tool hooks AND bash guardian) fail open simultaneously
- `rm -rf /`, force push, and any blocked bash pattern would be allowed

### Proposed Fix
```python
project_dir_str = get_project_dir()
if not project_dir_str:
    # SECURITY: No project dir = can't verify safety, deny by default
    print("GUARDIAN WARN: No project dir set, failing closed for bash guardian", file=sys.stderr)
    reason = "Guardian cannot verify command safety: project directory not set"
    print(_json.dumps(deny_response(reason)))
    sys.exit(0)  # ← Fail-closed (deny)
```

### Considerations
- **High impact**: This would block ALL bash commands if `CLAUDE_PROJECT_DIR` is missing. Same usability tradeoff as P0-A/P0-B — failing open is worse.
- **Consistency**: All three guardians (tool hook, symlink check, bash guardian) should have the same fail-closed behavior.

---

## Related: `expand_path()` and `normalize_path_for_matching()` Fail-Open

### `expand_path()` (~line 954-973)
```python
except Exception:
    return Path(path)  # ← Returns unresolved path on error
```
If path resolution fails, returns the raw `Path(path)` object. This could cause `is_path_within_project()` to compare an unresolved path against a resolved project dir, potentially yielding incorrect results.

**Recommendation**: Consider alongside P0-A/P0-B. The fail-closed fix on `is_path_within_project()` mitigates this (if expand_path fails, the outer except catches it and returns False). Document as defense-in-depth.

### `normalize_path_for_matching()` (~line 1082)
```python
except Exception:
    return path  # ← Returns original string on error
```
Similar fail-open pattern in path normalization. Lower risk since it's used for pattern matching, not boundary checks.

**Recommendation**: Fix for consistency but lower priority than P0-A/P0-B/P0-C.

---

## P1: `noDeletePaths` Not Enforced in Tool Hooks

### Location
`hooks/scripts/_guardian_utils.py`, function `run_path_guardian_hook()` (~line 2231-2369)

### Current Behavior
The Read/Edit/Write tool hook checks these tiers in order:
1. Symlink escape → line ~2253
2. Project boundary + external admission → line ~2260
3. Self-guardian → line ~2295
4. `zeroAccessPaths` → line ~2310
5. `readOnlyPaths` (skip for Read) → line ~2340
6. **ALLOW** ← `noDeletePaths` is never checked

Meanwhile, the Bash guardian (`bash_guardian.py:1074`) DOES check `noDeletePaths` for delete commands.

### Problem
The Write tool can overwrite a `noDeletePaths`-protected file with empty or different content — effectively deleting its data. The Edit tool can also replace all content. Only Bash-based deletion (`rm`, `del`) is caught.

Example:
```
# BLOCKED by Bash guardian:
rm README.md                    → "Protected from deletion: README.md"

# ALLOWED by tool hook (no noDelete check):
Write(file_path="README.md", content="")   → Succeeds, data destroyed
```

### Why This Matters
`noDeletePaths` protects files like:
- `.gitignore`, `.gitattributes`, `.gitmodules`
- `CLAUDE.md`, `LICENSE`, `README.md`
- `.github/**`, `Dockerfile`, `Makefile`
- `pyproject.toml`, `package.json`, `tsconfig.json`, `Cargo.toml`, `go.mod`

These files could be silently wiped via the Write tool.

### Proposed Fix — Option A (Minimal, Recommended)

Add a noDelete check to `run_path_guardian_hook()` for the Write tool, AFTER the readOnly check:

```python
    # ========== Check: Read Only ==========
    # (existing code unchanged)

    # ========== Check: No Delete (Write tool — content destruction prevention) ==========
    if tool_name.lower() == "write" and match_no_delete(path_str):
        # Write tool REPLACES entire file content = effective deletion
        log_guardian("BLOCK", f"No-delete path (Write = content destruction) ({tool_name}): {path_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", f"Would DENY {tool_name} (no-delete)")
            sys.exit(0)
        reason = (
            f"Protected from overwrite: {Path(file_path).name}"
            "\nThis file is in noDeletePaths. Use Edit tool for partial modifications."
        )
        print(_json.dumps(deny_response(reason)))
        sys.exit(0)

    # ========== Allow ==========
```

### Why Write Only (Not Edit)?
- **Write** replaces the ENTIRE file → equivalent to delete + create → should be blocked
- **Edit** makes surgical replacements → preserves most content → should be allowed
- This matches the intent: "don't DELETE the file or its data" vs "don't modify the file at all" (that's readOnlyPaths)

### Proposed Fix — Option B (Stricter)

Block BOTH Write and Edit for noDeletePaths:

```python
    if tool_name.lower() in ("write", "edit") and match_no_delete(path_str):
```

**Tradeoff**: This makes noDeletePaths behave similarly to readOnlyPaths for tools. The difference remains:
- `readOnlyPaths`: blocks Write + Edit tools
- `noDeletePaths` (with Option B): blocks Write + Edit tools (same!)

So Option B essentially makes noDeletePaths = readOnlyPaths for tool hooks, which may cause confusion. **Option A (Write only) is recommended** because it preserves the semantic difference: noDelete protects against data DESTRUCTION, not against all modifications.

### Proposed Fix — Option C (Action-Aware, Long-term)

Refactor to an action-aware authorization model:
```python
def authorize(path: str, action: str) -> tuple[bool, str]:
    """action: 'read', 'write', 'edit', 'delete', 'truncate'"""
    # Unified logic for all tools and bash
```

This is the ideal long-term solution (endorsed by both Codex and Gemini) but requires significant refactoring. Not recommended for this fix cycle.

### Recommendation
**Implement Option A with the "existing files only" refinement** (see Revised Recommendation below in Cross-Model Validation). Block Write on noDeletePaths only when the file already exists (overwrite = data destruction), but allow Write to create new files matching noDelete patterns. This preserves the documented semantics: "files that can be read and written but not deleted." Consider Option C for a future architectural revision.

---

## Testing Requirements

### P0-A Tests
1. `is_path_within_project("")` with no CLAUDE_PROJECT_DIR → returns False (was True)
2. `is_path_within_project("/some/path")` with no CLAUDE_PROJECT_DIR → returns False
3. Mock path resolution exception → returns False (was True)
4. Normal paths still work: project path → True, external path → False
5. Verify stderr output when CLAUDE_PROJECT_DIR is unset (log_guardian is no-op)

### P0-B Tests
1. `is_symlink_escape("/some/path")` with no CLAUDE_PROJECT_DIR → returns True (was False)
2. Mock symlink resolution exception → returns True (was False)
3. Normal symlinks still work: internal → False, external → True
4. Non-symlinks still work: → False
5. Verify stderr output when CLAUDE_PROJECT_DIR is unset
6. Deep symlink escape: `ln -s / outside_dir` → `Read("outside_dir/etc/passwd")` should be caught

### P0-C Tests
1. Bash command with no CLAUDE_PROJECT_DIR → BLOCKED (was allowed via sys.exit(0))
2. Verify deny response includes meaningful error message
3. Normal bash commands with project dir set → unchanged behavior

### P1 Tests
1. Write tool on EXISTING noDeletePaths file → BLOCKED with "Protected from overwrite" message
2. Write tool to CREATE new file matching noDeletePaths pattern → ALLOWED (file doesn't exist yet)
3. Edit tool on noDeletePaths file → ALLOWED
4. Read tool on noDeletePaths file → ALLOWED
5. Bash `rm` on noDeletePaths file → BLOCKED (existing behavior, unchanged)
6. Write tool on non-noDeletePaths file → ALLOWED (no regression)

### Integration Tests
1. Full hook pipeline with sys.exit() behavior (not just unit tests for individual functions)
2. `expand_path()` exception → `is_path_within_project()` outer except catches → returns False (defense-in-depth)

---

## Execution Order

1. **P0-A + P0-B + P0-C first** (security-critical, minimal code changes, low risk)
2. **P1 after P0** (more impact on behavior, needs testing)
3. Run existing test suite after each change to check for regressions
4. Update CHANGELOG.md

---

## Cross-Model Validation Summary (Round 1)

### Codex CLI (codex 5.3) — APPROVE WITH CONCERNS

**P0-A/P0-B**: Correct. Fail-closed is mandatory.
- **Warning**: `log_guardian()` is a no-op when `CLAUDE_PROJECT_DIR` is unset (line 1315-1318). Proposed logging in the `if not project_dir` branches won't emit anything. Consider using `print()` to stderr as fallback.
- **Warning**: P0-B error messaging — after fix, deny says "Symlink points outside project" when real cause is exception. Consider a distinct error message or tri-state return.

**P1**: **SEMANTIC CONFLICT flagged.**
- noDeletePaths is documented as "read AND written but not deleted" (schema-reference.md, README.md)
- Blocking Write tool changes the semantics to "read only, no write, no delete" = essentially readOnlyPaths
- `.github/**` pattern in noDeletePaths would block creating new workflow files
- **Recommendation**: Narrow enforcement — block Write ONLY for existing files being overwritten, not file creation. Or block only when content would be empty/truncated.

**Additional findings**:
- Line number: `run_path_guardian_hook()` starts at line 2231 (not ~2330)
- P0-A docstring contradicts code — docstring says "False on error" but code returns True
- Need integration tests with sys.exit() behavior, not just unit tests
- resolve_tool_path (line 963-973) also has fail-open pattern — consider fixing

### Gemini CLI (gemini 3 pro) — APPROVE

**P0-A**: Most critical fix. `is_path_within_project` is the ONLY defense against deep symlink escapes (`is_symlink_escape` is shallow — checks only final component).
**P0-B**: Correct. Consistent with security best practices.
**P1**: Correct. Write = full content replacement = semantically delete + create.

**Missing test cases**:
1. Deep symlink escape: `ln -s / outside_dir` → `Read("outside_dir/etc/passwd")`
2. noDelete file creation: `CLAUDE.md` doesn't exist → `Write("CLAUDE.md", "content")` — should this be blocked?

### Synthesis

| Item | Codex | Gemini | My Assessment |
|------|-------|--------|---------------|
| P0-A/B | APPROVE | APPROVE | APPROVE — unanimous |
| P1 scope | Narrow (existing files only) | Block all Write | **Narrow** — Codex's semantic conflict point is valid |
| P1 Edit | Allow | Allow | Allow — unanimous |
| Error messaging | Fix needed | OK | Fix needed (Codex's point is valid) |
| Log no-op | Fix needed | Not flagged | Fix needed |

### P1 Revised Recommendation

Based on Codex's semantic analysis, P1 Option A should be refined:

```python
# REVISED: Only block Write on EXISTING noDeletePaths files (not creation)
if tool_name.lower() == "write" and match_no_delete(path_str):
    # Only block if file already exists (overwrite = data destruction)
    # Creating a new file that happens to match noDeletePaths is allowed
    resolved = expand_path(file_path)  # Use resolved path, not raw file_path
    if resolved.exists():
        log_guardian("BLOCK", f"No-delete path overwrite ({tool_name}): {path_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", f"Would DENY {tool_name} (no-delete overwrite)")
            sys.exit(0)
        reason = (
            f"Protected from overwrite: {Path(file_path).name}"
            "\nThis file is in noDeletePaths. Use Edit tool for partial modifications."
        )
        print(_json.dumps(deny_response(reason)))
        sys.exit(0)
```

This preserves the documented semantics:
- Write (create new file matching noDelete pattern) → ALLOWED
- Write (overwrite existing noDelete file) → BLOCKED (data destruction)
- Edit (modify existing noDelete file) → ALLOWED
- Bash rm (delete noDelete file) → BLOCKED (existing behavior)

---

## Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `hooks/scripts/_guardian_utils.py` | P0-A: `is_path_within_project()` fail-closed + stderr logging | ~1035, ~1051 |
| `hooks/scripts/_guardian_utils.py` | P0-B: `is_symlink_escape()` fail-closed + stderr logging + error message | ~981, ~1021 |
| `hooks/scripts/_guardian_utils.py` | P0-A: Update docstring (currently contradicts behavior — says "False on error" but returns True) | ~1025 |
| `hooks/scripts/_guardian_utils.py` | P0-B: Update docstring (currently says fail-open) | ~988-989 |
| `hooks/scripts/_guardian_utils.py` | P1: Add noDelete check in `run_path_guardian_hook()` | After readOnly check, before ALLOW (~line 2350) |
| `hooks/scripts/bash_guardian.py` | P0-C: Fail-closed on missing project dir | ~960-962 |
| `tests/` | New tests for P0-A, P0-B, P0-C, P1 + deep symlink + noDelete creation + integration | New test cases |
| `CHANGELOG.md` | Document changes | Append |
| `README.md` | Update noDeletePaths documentation if semantics change | If needed |
