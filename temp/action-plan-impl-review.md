# Implementation Review: SessionStart Auto-Activate Action Plan

**Reviewer**: impl-reviewer
**Date**: 2026-02-22
**Document reviewed**: `action-plans/session-start-auto-activate.md`
**Verdict**: **Approve with required changes** (3 must-fix, 4 should-fix, 2 notes)

---

## 1. Completeness

**Overall**: The plan is thorough and implementation-ready. Someone could implement this from the plan alone, with the exceptions noted below.

### What's covered well
- Step-by-step implementation with exact file paths and code
- Comprehensive edge case table (16 scenarios, risk-rated, with mitigations)
- Testing plan with 14 specific test cases matching existing test patterns
- Rollback plan is clear and minimal-impact
- Design decision appendix with rationale for each tradeoff
- Dependency table with status tracking

### Gaps in completeness

**G1 (should-fix): No explicit file permission specification for created config.**
The plan says `chmod +x` for the script itself but doesn't specify what permissions the created `config.json` should have. By default, `cp` preserves source permissions. If `guardian.recommended.json` in the repo has overly permissive permissions (e.g., 0644 is fine, but 0666 would be a concern), the created config inherits them. This is likely fine but should be stated explicitly.

**G2 (note): Documentation updates (Step 3) are described at a high level.**
Step 3a/3b/3c describe what to update but don't provide exact text. This is acceptable for docs -- the implementer can draft appropriate text -- but it makes Step 3 less "implementable from the plan alone" compared to Steps 1-2.

---

## 2. Correctness

### Shell Script Review

The script was reviewed by Gemini 3 Pro (via pal clink) and by this reviewer. The script is well-structured with excellent quoting, consistent fail-open behavior, and a sound atomic write strategy.

**Three issues were identified:**

#### C1 (must-fix): Race condition -- use `mv -n` instead of re-check + `mv`

**Location**: Lines 72-79 of the script in the plan.

```bash
# Current (racy):
if [ -f "$CONFIG" ]; then
  exit 0
fi
if ! mv "$TMPFILE" "$CONFIG" 2>/dev/null; then
  exit 0
fi
```

**Problem**: Two concurrent sessions can both pass the `-f` check and both execute `mv`. Standard `mv` overwrites the destination, so the second session clobbers the first. While both write identical content (making this functionally harmless for the v1 use case), this is architecturally fragile -- if a future change allows per-session customization, it becomes a data loss bug.

**Fix**: Replace the re-check + mv with `mv -n` (no-clobber):
```bash
# Fixed (atomic no-clobber):
if ! mv -n "$TMPFILE" "$CONFIG" 2>/dev/null; then
  exit 0
fi
```

**Portability**: `mv -n` is supported on:
- GNU coreutils (Linux) -- yes
- BSD/macOS `mv` -- yes (supported since macOS 10.x)
- BusyBox -- **no** (but BusyBox environments are unlikely for Claude Code)

The re-check `[ -f "$CONFIG" ]` block can be removed entirely since `mv -n` makes it redundant.

#### C2 (should-fix): Use `mktemp` instead of predictable `$$` PID suffix

**Location**: Line 64 of the script in the plan.

```bash
# Current (predictable):
TMPFILE="$CONFIG_DIR/.config.json.tmp.$$"
```

**Problem**: CWE-377 -- predictable temporary file naming. The PID (`$$`) is easily guessable. A compromised dependency or malicious actor with local write access could pre-create a symlink at the predicted path, redirecting `cp`'s output to an arbitrary file. The threat model is narrow (attacker needs write access to `.claude/guardian/`), but the fix is trivial.

**Fix**:
```bash
TMPFILE=$(mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX") || exit 0
```

`mktemp` atomically creates the file with a random suffix, preventing symlink preemption. It's available on all platforms where Claude Code runs (GNU coreutils, macOS, WSL).

**Note**: When using `mktemp`, the `cp` should become `cp "$SOURCE" "$TMPFILE"` (overwrite mode, which is the default), since the temp file already exists (created empty by mktemp). This is a behavioral difference from the current approach where `cp` creates the file.

#### C3 (should-fix): Broaden trap to catch signals

**Location**: Line 66 of the script in the plan.

```bash
# Current:
trap cleanup EXIT
```

**Problem**: In some shell environments, `EXIT` alone may not fire on `SIGINT`, `SIGTERM`, or `SIGHUP`, potentially leaving orphaned temp files.

**Fix**:
```bash
trap cleanup EXIT INT TERM HUP
```

This is a minor hardening -- orphaned dotfiles in `.claude/guardian/` are harmless and cleaned up on next successful run -- but the fix costs nothing.

### hooks.json Changes

**C4 (must-fix): Verify `"startup"` matcher value before implementation.**

The plan uses `"matcher": "startup"` but explicitly flags this as unverified in the dependency table:

> `"startup"` matcher value verification | **Must verify** | Confirm that `"startup"` is the exact matcher string Claude Code uses for new-session SessionStart events

This is the single highest-risk dependency in the entire plan. If the matcher value is wrong, the feature is **silently non-functional** -- no error, no log, just a dead hook. The existing `hooks.json` uses matchers like `"Bash"`, `"Read"`, `"Edit"`, `"Write"` for PreToolUse (which match tool names), and the Stop hook has **no matcher at all**.

**Recommendation**: Before implementation begins, verify the exact matcher value by:
1. Checking Claude Code's plugin documentation for SessionStart event matcher semantics
2. Testing with a minimal hook: `"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "echo test"}]}]` and confirming it fires
3. If `"startup"` doesn't work, try `"*"` as a wildcard matcher, or omit the matcher entirely (like the Stop hook does)

If the matcher semantics cannot be verified, consider omitting the matcher (matching all SessionStart events) and filtering inside the script. This adds one check but eliminates the silent-failure risk:
```bash
# Inside session_start.sh, if matcher can't be verified:
# Accept that this runs on resume/clear/compact too -- the [ -f "$CONFIG" ] check
# makes extra runs harmless (they exit silently).
```

### hooks.json Structure

The proposed hooks.json change is structurally correct. Adding `"SessionStart"` as a new top-level key alongside `"PreToolUse"` and `"Stop"` follows the established pattern. The nesting structure (`event -> [matcher objects] -> hooks array`) matches the existing entries.

---

## 3. Edge Cases

### Edge cases handled well
- Empty/unset env vars (high risk, caught early)
- Symlink attacks on parent directories AND target file
- Read-only filesystem / permission denied
- Disk full / partial write (atomic temp+mv)
- Concurrent sessions (re-check pattern, identical content)
- Git worktrees (correct: each gets own config)
- Non-UTF8 locale (ASCII-only messages)

### Edge cases to add or clarify

**E1 (must-fix): Author's notes vs. script inconsistency on symlink check.**

The author's working notes state:
> "Did NOT add a check on config.json itself because it doesn't exist yet"

But the script in the plan **does** check `[ -L "$CONFIG" ]` (line 43), and the edge case table (row "Symlink at `config.json` itself") documents this check. The script is correct; the author's notes are stale. This inconsistency should be resolved to avoid confusion during implementation. No code change needed -- just update or remove the stale note.

**E2 (note): `CLAUDE_PROJECT_DIR` containing special characters.**

The script quotes all variables correctly, which handles spaces and most special characters. However, if `CLAUDE_PROJECT_DIR` contains a newline character (theoretically possible on some filesystems), the `echo` output could be confusing. This is an extreme edge case with no practical mitigation needed, but it's not listed in the edge case table.

**E3 (should-fix): Missing edge case -- `.claude/guardian/config.json` is a regular file with size 0.**

If a user creates an empty `config.json` (e.g., `touch .claude/guardian/config.json`), the `[ -f "$CONFIG" ]` check passes and the script exits silently. This is correct behavior per the plan's opt-out mechanism. However, the guardian Python hooks may then fail to parse the empty file and fall back to hardcoded defaults -- which is the same behavior as having no config. This means the user has a file that looks like it should be doing something but isn't.

This is out of scope for the SessionStart hook (acknowledged in the edge case table under "Existing but corrupt config.json"), but the testing plan should include a test case for this scenario to verify the expected silent-exit behavior.

---

## 4. Testing Plan

### Strengths
- 14 well-defined test cases covering the critical paths
- Test method (subprocess.run with controlled env) matches existing patterns in the codebase
- Tests will live in `tests/regression/` which is the correct category per `tests/README.md`
- Idempotency test is included (critical for hook safety)
- Manual smoke tests complement automated tests

### Gaps

**T1 (should-fix): Missing test for `mktemp` failure.**
If the `mktemp` recommendation (C2) is adopted, add a test case:
| `test_mktemp_failure` | `$CONFIG_DIR` not writable (simulate mktemp failure) | No stdout, no file created, exit 0 |

**T2 (should-fix): Missing test for empty config file (E3).**
| `test_empty_config_file_exits_silently` | `config.json` exists but is empty (0 bytes) | No stdout, no modification, exit 0 |

**T3 (note): Consider a test for `mv -n` no-clobber behavior.**
If C1 is adopted, a test that creates `config.json` between `cp` and `mv` (simulating the race) would verify the no-clobber behavior. This is tricky to test reliably without race injection, so it may be better covered by a manual concurrency test.

**T4 (should-fix): Test file placement.**
The plan says `tests/regression/test_session_start.py` but the test cases are closer to integration tests (subprocess execution with env var control). The existing precedent is `tests/security/test_p0p1_failclosed.py` which uses the same subprocess pattern but lives in `security/`. Since this hook is fail-open (not fail-closed), `regression/` is the correct home. The plan is correct here, but the reasoning should be stated.

---

## 5. Dependencies

### Verified
- `assets/guardian.recommended.json` -- **exists** in the repo (confirmed by reading it)
- `CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_ROOT` -- standard Claude Code env vars, used by existing hooks
- Test infrastructure (`_bootstrap.py`, `conftest.py`) -- ready for new test files

### Unverified (blocking)
- **`"startup"` matcher value** -- See C4 above. This MUST be verified before implementation. It's the difference between the feature working and being silently dead.

### Implicit dependency not listed
- **`chmod +x` on the created script**: The plan mentions this but it's not in the acceptance criteria. CI/CD systems or Windows/WSL may not preserve the executable bit. Consider using `bash "$SCRIPT"` in the hook command (which the plan already does) as the primary execution method, making `chmod +x` unnecessary. The existing hooks already use `python3 "$SCRIPT"` rather than relying on the shebang, so this is consistent.

Actually, reviewing the hooks.json command: `bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session_start.sh"` -- this invokes `bash` explicitly, so the executable bit is **not required**. The plan should note this and can drop the `chmod +x` instruction (or keep it as a convenience for direct execution during testing).

---

## 6. Summary of Findings

### Must-Fix (3)

| ID | Finding | Severity | Fix |
|----|---------|----------|-----|
| C1 | Race condition: `mv` can overwrite concurrent session's config | High | Use `mv -n` (no-clobber) instead of re-check + `mv` |
| C4 | `"startup"` matcher value is unverified | High | Verify against Claude Code docs or test empirically before implementation |
| E1 | Author's notes contradict script on symlink check at `config.json` | Medium | Notes say no check, script has check -- resolve inconsistency |

### Should-Fix (4)

| ID | Finding | Severity | Fix |
|----|---------|----------|-----|
| C2 | Predictable temp file naming (CWE-377) | Medium | Use `mktemp` instead of `$$` PID suffix |
| C3 | Narrow trap scope | Low | Add `INT TERM HUP` to trap alongside `EXIT` |
| E3 | Empty config.json edge case undocumented | Low | Add to edge case table and testing plan |
| T2 | Missing test cases for mktemp failure and empty config | Low | Add 2 test cases to testing plan |

### Notes (2)

| ID | Finding | Notes |
|----|---------|-------|
| G1 | Config file permissions not specified | Likely fine (cp preserves source), but should be stated |
| G2 | `chmod +x` is unnecessary since bash is invoked explicitly | Can remove or keep as convenience; note the distinction |

---

## 7. Corrected Script (incorporating must-fix and should-fix)

For reference, here is the script with all recommended changes applied:

```bash
#!/bin/bash
# Guardian SessionStart Hook -- Auto-activate recommended config on first session.
# Fail-open: all errors exit 0 silently. Never block session startup.

# --- Environment validation ---
if [ -z "$CLAUDE_PROJECT_DIR" ] || [ -z "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

CONFIG="$CLAUDE_PROJECT_DIR/.claude/guardian/config.json"
SOURCE="$CLAUDE_PLUGIN_ROOT/assets/guardian.recommended.json"

# --- Already configured? Exit silently. ---
if [ -f "$CONFIG" ] || [ -L "$CONFIG" ]; then
  exit 0
fi

# --- Source file must exist ---
if [ ! -f "$SOURCE" ]; then
  exit 0
fi

# --- Symlink safety: reject if target path or parent dirs are symlinks ---
if [ -L "$CLAUDE_PROJECT_DIR/.claude" ] || [ -L "$CLAUDE_PROJECT_DIR/.claude/guardian" ]; then
  exit 0
fi

# --- Create directory (fail silently on permission/read-only errors) ---
CONFIG_DIR="$(dirname "$CONFIG")"
if ! mkdir -p "$CONFIG_DIR" 2>/dev/null; then
  exit 0
fi

# --- Atomic write: copy to secure temp file, then mv (no-clobber) ---
TMPFILE=$(mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX" 2>/dev/null) || exit 0
cleanup() { rm -f "$TMPFILE" 2>/dev/null; }
trap cleanup EXIT INT TERM HUP

if ! cp "$SOURCE" "$TMPFILE" 2>/dev/null; then
  exit 0
fi

if ! mv -n "$TMPFILE" "$CONFIG" 2>/dev/null; then
  exit 0
fi

# --- Success: print context message (stdout goes into Claude's context) ---
echo "[Guardian] Activated recommended security config for this project."
echo "Protecting against: destructive commands, secret exposure, critical file deletion, force pushes."
echo "Config saved to .claude/guardian/config.json (safe to commit)."
echo "Review: 'show guardian config' | Customize: /guardian:init | Modify: 'block X' or 'allow Y'"
exit 0
```

**Changes from original**:
1. `mktemp` replaces `$$` PID suffix (C2)
2. `mv -n` replaces re-check + `mv` (C1)
3. `trap cleanup EXIT INT TERM HUP` replaces `trap cleanup EXIT` (C3)
4. Removed the redundant `[ -f "$CONFIG" ]` re-check block (superseded by `mv -n`)

---

## Appendix: Gemini 3 Pro Review Summary

Gemini 3 Pro (via pal clink) independently identified:
1. **High**: TOCTOU race condition on `mv` -- recommended `mv -n` (adopted as C1)
2. **Medium**: Predictable temp file naming -- recommended `mktemp` (adopted as C2)
3. **Low**: Narrow trap scope -- recommended broader signal trapping (adopted as C3)
4. **Low**: Symlink TOCTOU inherent in bash -- acknowledged, mitigated by `mktemp` + `mv -n` defense-in-depth

Gemini confirmed the script's quoting, atomic write pattern, and fail-open behavior are all well-implemented.
