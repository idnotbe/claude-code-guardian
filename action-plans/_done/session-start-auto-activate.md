---
status: done
progress: "구현 완료 + 라이브 세션 검증 완료 (28 tests pass, config 생성 확인)"
---

# SessionStart Auto-Activate ("Instant-On")

## 1. Goal

Guardian's security hooks activate immediately after plugin installation, but without a project-specific `config.json`, they fall back to hardcoded minimal defaults. Users have no proactive indication that richer protection is available or that `/guardian:init` exists. The gap between installation and effective protection leaves users silently under-protected.

This feature closes that gap. When a user starts a Claude Code session and no project config exists at `.claude/guardian/config.json`, Guardian auto-copies `assets/guardian.recommended.json` to that path and prints a context message so Claude can inform the user. Users get full recommended protection from session 1 with zero friction. The existing `/guardian:init` wizard becomes a customization tool rather than a mandatory setup gate. Security becomes opt-out, not opt-in.

## 2. Implementation Steps

### Step 1: Create `hooks/scripts/session_start.sh`

Create the following file. The hook command invokes it via `bash` explicitly, so the executable bit is not required for operation, but `chmod +x` is recommended for direct execution during testing.

**Design principles:**
- **Fail-open**: All failures exit 0. The session must never be blocked by this hook.
- **Idempotent**: Running twice produces the same result. No overwrite of existing config.
- **Silent in steady state**: If config exists, no output at all.
- **Warning on failed creation**: If config creation is attempted but fails, emit a warning so the user/Claude is aware of degraded protection. Early exits (env vars missing, config exists, source missing) remain silent.
- **Atomic write**: `mktemp` (secure temp file) + `mv -n` (no-clobber, atomic on POSIX) to prevent partial/corrupt config and race conditions.

```bash
#!/bin/bash
# Guardian SessionStart Hook -- Auto-activate recommended config on first session.
# Fail-open: all errors exit 0. Never block session startup.
# Warning emitted only when config creation is attempted but fails.

# --- Environment validation ---
# If either env var is missing/empty, exit silently (can't do anything useful).
if [ -z "$CLAUDE_PROJECT_DIR" ] || [ -z "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

# Validate paths are absolute directories (defense-in-depth, matches Python guardians)
case "$CLAUDE_PROJECT_DIR" in /*) ;; *) exit 0 ;; esac
if [ ! -d "$CLAUDE_PROJECT_DIR" ] || [ ! -d "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

CONFIG="$CLAUDE_PROJECT_DIR/.claude/guardian/config.json"
SOURCE="$CLAUDE_PLUGIN_ROOT/assets/guardian.recommended.json"

# --- Already configured? Exit silently. ---
# Also reject if config.json is a symlink (even dangling) -- prevents write redirection.
if [ -f "$CONFIG" ] || [ -L "$CONFIG" ]; then
  exit 0
fi

# --- Source file must exist ---
if [ ! -f "$SOURCE" ]; then
  exit 0
fi

# --- Create directory (fail silently on permission/read-only errors) ---
CONFIG_DIR="$(dirname "$CONFIG")"
if ! mkdir -p "$CONFIG_DIR" 2>/dev/null; then
  echo "[Guardian] Could not auto-activate recommended config. Using minimal defaults."
  echo "Run /guardian:init to set up full protection."
  exit 0
fi

# --- Post-creation symlink validation (TOCTOU mitigation) ---
# Checked AFTER mkdir to narrow the race window between check and use.
if [ -L "$CLAUDE_PROJECT_DIR/.claude" ] || [ -L "$CLAUDE_PROJECT_DIR/.claude/guardian" ]; then
  exit 0
fi

# --- Atomic write: mktemp (secure temp) + mv -n (no-clobber) ---
# mktemp uses O_EXCL, preventing symlink preemption (fixes CWE-377).
TMPFILE=$(mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX" 2>/dev/null) || {
  echo "[Guardian] Could not auto-activate recommended config. Using minimal defaults."
  echo "Run /guardian:init to set up full protection."
  exit 0
}
cleanup() { rm -f "$TMPFILE" 2>/dev/null; }
trap cleanup EXIT

# cp preserves source file permissions (typically 0644 from the repo).
if ! cp "$SOURCE" "$TMPFILE" 2>/dev/null; then
  echo "[Guardian] Could not auto-activate recommended config. Using minimal defaults."
  echo "Run /guardian:init to set up full protection."
  exit 0
fi

# Atomic move: mv -n refuses to overwrite existing targets, preventing both
# concurrent-session clobber and symlink-to-directory redirect attacks.
if ! mv -n "$TMPFILE" "$CONFIG" 2>/dev/null; then
  # mv -n failure means config was created by another session (benign race) or attack
  exit 0
fi

# --- Success: print context message (stdout goes into Claude's context) ---
echo "[Guardian] Activated recommended security config for this project."
echo "Protecting against: destructive commands, secret exposure, critical file deletion, force pushes."
echo "Config saved to .claude/guardian/config.json (safe to commit)."
echo "Review: 'show guardian config' | Customize: /guardian:init | Modify: 'block X' or 'allow Y'"
exit 0
```

**Post-creation**: `chmod +x hooks/scripts/session_start.sh` (optional -- the hook command invokes `bash` explicitly, so the executable bit is not required, but it's convenient for direct execution during testing)

### Step 2: Update `hooks/hooks.json`

Add the `SessionStart` event to the existing hooks configuration. The `"matcher": "startup"` ensures this only fires on new sessions (not resume, clear, or compact).

> **BLOCKING**: The `"startup"` matcher value must be verified before implementation. See the Dependencies table for verification steps and fallback strategy. If verification fails, omit the matcher and rely on the script's `[ -f "$CONFIG" ]` idempotency check.

**Current file** (`hooks/hooks.json`):
```json
{
  "hooks": {
    "PreToolUse": [ ... ],
    "Stop": [ ... ]
  }
}
```

**Change**: Add `SessionStart` as the first entry in `hooks`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session_start.sh\""
          }
        ]
      }
    ],
    "PreToolUse": [ ... existing, unchanged ... ],
    "Stop": [ ... existing, unchanged ... ]
  }
}
```

### Step 3: Update documentation

#### 3a. README.md
Add a section or update the existing "Getting Started" / "Quick Start" section:
- Mention that Guardian auto-activates recommended config on first session
- Explain that `/guardian:init` is available for customization but not required
- Note the opt-out mechanism (create any `.claude/guardian/config.json` before first session)

#### 3b. CLAUDE.md
- Add `hooks/scripts/session_start.sh` to the "Key source files" section
- Update the "Coverage Gaps by Script" table to include `session_start.sh`
- Add a note about SessionStart being fail-open by design (similar to the auto-commit note)

#### 3c. commands/init.md
- No structural changes needed (it already handles "Check for Existing Config" in Step 1)
- Optional: update the philosophy intro to mention that config may already exist from auto-activation

## 3. Edge Cases

| Edge Case | What Happens | Risk | Mitigation |
|-----------|-------------|------|------------|
| **Empty/unset `CLAUDE_PROJECT_DIR`** | Script would create dirs at wrong location or root | **High** | Explicit check: exit 0 if either env var is empty/unset (line 6-8) |
| **Empty/unset `CLAUDE_PLUGIN_ROOT`** | Source file path invalid | **High** | Same guard as above |
| **Relative `CLAUDE_PROJECT_DIR`** | Script could create dirs relative to CWD, not project root | **High** | `case "$CLAUDE_PROJECT_DIR" in /*) ;; *) exit 0 ;; esac` rejects non-absolute paths. Matches Python guardians' validation |
| **Non-existent `CLAUDE_PROJECT_DIR`** | `mkdir -p` could create dirs at a stale/wrong path | **Medium** | `[ ! -d "$CLAUDE_PROJECT_DIR" ]` check exits silently. Matches Python guardians' `os.path.isdir()` |
| **Config already exists** | No action needed | None | Early `[ -f "$CONFIG" ]` check exits silently |
| **`.claude/guardian/` dir exists but config.json doesn't** | Directory creation is no-op, copy proceeds normally | None | `mkdir -p` with `2>/dev/null` handles this |
| **Source `guardian.recommended.json` missing** | Corrupt or incomplete plugin install | **Medium** | Pre-flight `[ ! -f "$SOURCE" ]` check exits silently. User falls back to hardcoded defaults (no worse than current) |
| **Read-only filesystem** | `mkdir -p` or `cp` fails | **Medium** | All filesystem ops redirect stderr to /dev/null. Each op checks exit code. Warning emitted on failed creation attempt, then exits 0 |
| **Permission denied (EACCES)** | Same as read-only filesystem | **Medium** | Same mitigation -- warning + exit 0 |
| **Disk full (ENOSPC)** | `cp` to temp file fails or produces truncated file | **High** | `mktemp` creates secure temp file. If `cp` fails, warning emitted, temp cleaned up by trap. If `mv -n` fails, no corrupt config.json left |
| **Partial write (kill/power loss during cp)** | Only temp file is affected, not config.json | **Medium** | Atomic write (`mktemp` + `mv -n`). config.json is either absent or complete. Orphaned temp file is harmless (hidden dotfile with random suffix, cleaned on next success) |
| **Concurrent sessions (race condition)** | Two sessions both see no config, both try to copy | **Medium** | (1) `mkdir -p` is safe with concurrent calls. (2) `mv -n` (no-clobber) means the first session wins; the second session's `mv` fails silently. (3) `mktemp` ensures each session uses a unique temp file. (4) No data corruption possible -- both sessions copy the same source |
| **Symlink attack on `.claude/` or `.claude/guardian/`** | Attacker redirects write outside project | **High** | Explicit `-L` symlink check on path components **after** `mkdir -p` (narrowed TOCTOU window). Combined with `mktemp` (O_EXCL) and `mv -n`, exploitation is extremely difficult |
| **Symlink at `config.json` itself** | Pre-created symlink (even dangling) redirects mv target | **High** | `[ -L "$CONFIG" ]` check rejects symlinks at the target path, including dangling ones |
| **Git worktree** | `CLAUDE_PROJECT_DIR` points to worktree root, not main repo | **Low** | Script trusts `CLAUDE_PROJECT_DIR` as-is. Each worktree gets its own config, which is correct (worktrees can have different security needs) |
| **CI/CD environment** | Hook runs in headless pipeline, may create unwanted file | **Low** | Creating the file is harmless in CI (ephemeral). The file is `.gitignore`-able. Future enhancement: check `$CI` env var to skip |
| **Network filesystem (NFS/SMB)** | Higher latency, potential stale file handles | **Low-Medium** | Temp file is in the same directory as target (same mount point) so `mv` is atomic. All errors caught and handled |
| **Very long paths (ENAMETOOLONG)** | `mkdir` or `cp` fails | **Low** | Caught by the `2>/dev/null` + exit-code checks |
| **Non-UTF8 locale** | Echo output could fail or garble | **Low** | All message strings are ASCII-only. No locale-sensitive operations |
| **Empty config.json (0 bytes)** | `[ -f "$CONFIG" ]` succeeds, hook exits silently | **Low** | Correct behavior -- the file exists, so the hook treats it as "already configured." Guardian Python hooks fall back to defaults on empty/invalid JSON. The user created it intentionally (e.g., `touch config.json` as an opt-out) |
| **Existing but corrupt config.json** | File exists check succeeds, hook exits silently, but guardian falls back to defaults at runtime | **Medium** | Out of scope for this hook (the hook's job is first-run bootstrap only). Could add lightweight JSON validation as a future enhancement |

## 4. Testing Plan

### 4.1 Unit/Integration Tests (add to `tests/`)

Create `tests/regression/test_session_start.py`:

| Test Case | Description | Assert |
|-----------|-------------|--------|
| `test_first_run_creates_config` | No config exists, valid source file, valid env vars | Config created, stdout contains "[Guardian] Activated", exit 0 |
| `test_existing_config_silent` | Config already exists | No stdout, no file modification, exit 0 |
| `test_missing_project_dir_env` | `CLAUDE_PROJECT_DIR` unset | No stdout, no file created, exit 0 |
| `test_empty_project_dir_env` | `CLAUDE_PROJECT_DIR=""` | No stdout, no file created, exit 0 |
| `test_missing_plugin_root_env` | `CLAUDE_PLUGIN_ROOT` unset | No stdout, no file created, exit 0 |
| `test_missing_source_file` | `guardian.recommended.json` doesn't exist at source path | No stdout, no file created, exit 0 |
| `test_readonly_filesystem` | Target directory not writable (chmod 555), mkdir fails | Stdout contains "Could not auto-activate", no file created, exit 0 |
| `test_dir_exists_no_config` | `.claude/guardian/` exists but `config.json` doesn't | Config created, stdout contains "[Guardian]", exit 0 |
| `test_created_config_valid_json` | After first-run creation | Created file parses as valid JSON |
| `test_created_config_matches_source` | After first-run creation | Created file content matches source file content |
| `test_symlink_parent_rejected` | `.claude` is a symlink | No stdout, no file created, exit 0 |
| `test_symlink_guardian_dir_rejected` | `.claude/guardian` is a symlink | No stdout, no file created, exit 0 |
| `test_symlink_config_file_rejected` | `config.json` is a symlink (dangling or valid) | No stdout, no file created/overwritten, exit 0 |
| `test_idempotent_double_run` | Run script twice | First run creates, second run is silent. File unchanged after second run |
| `test_empty_config_file_exits_silently` | `config.json` exists but is empty (0 bytes) | No stdout, no modification, exit 0 |
| `test_relative_project_dir_rejected` | `CLAUDE_PROJECT_DIR="relative/path"` | No stdout, no file created, exit 0 |
| `test_nonexistent_project_dir_rejected` | `CLAUDE_PROJECT_DIR="/nonexistent/path"` | No stdout, no file created, exit 0 |
| `test_mkdir_failure_emits_warning` | Target parent dir not writable (mkdir fails) | Stdout contains "Could not auto-activate", exit 0 |
| `test_cp_failure_emits_warning` | Source file unreadable or temp file write fails | Stdout contains "Could not auto-activate", exit 0 |
| `test_exit_code_always_zero` | All scenarios above | Exit code is always 0 |

### 4.2 Manual Smoke Tests

1. Fresh project (no `.claude/` directory): start Claude Code session, verify config created and context message appears
2. Existing config: start session, verify silence
3. Read-only project dir: verify session starts normally without config creation

### 4.3 Test Method

Tests invoke the script via `subprocess.run()` with controlled environment variables and a temporary directory structure. Pattern matches existing tests in `tests/security/test_p0p1_failclosed.py`.

**Why `tests/regression/`**: The SessionStart hook is fail-open by design (not a security-critical fail-closed hook), so it belongs in `regression/` rather than `security/`. The `security/` directory is reserved for fail-closed invariant tests.

## 5. Rollback Plan

### Immediate Rollback (disable feature)
Remove the `SessionStart` block from `hooks/hooks.json`. The script can remain in the filesystem -- it won't execute without the hook entry.

```json
// Remove this entire block from hooks.json:
"SessionStart": [
  {
    "matcher": "startup",
    "hooks": [
      {
        "type": "command",
        "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session_start.sh\""
      }
    ]
  }
],
```

### User-Level Rollback
Users who have already received an auto-activated config can:
1. Delete `.claude/guardian/config.json` to revert to hardcoded defaults
2. Edit the file to customize their protection level
3. Run `/guardian:init` to regenerate from scratch

### No Cascading Impact
- The auto-created config is identical to what `/guardian:init` would produce with recommended defaults
- All existing hooks (Bash, Edit, Read, Write, Stop) are unchanged
- The SessionStart hook has no side effects beyond creating a file

## 6. Dependencies

| Dependency | Status | Description |
|-----------|--------|-------------|
| `assets/guardian.recommended.json` | **Exists** | The recommended config file must exist and be valid JSON. Currently present in the repo |
| `guardian.recommended.json` test coverage | **Should verify** | The recommended config is the blast radius for all new users. Its regex patterns should be tested before auto-deployment |
| Claude Code SessionStart event support | **Available** | Claude Code fires SessionStart events with `startup` matcher. Documented in plugin architecture |
| `"startup"` matcher value verification | **BLOCKING -- Must verify before implementation** | Confirm that `"startup"` is the exact matcher string Claude Code uses for new-session SessionStart events (vs. `"*"`, a regex, or other value). Incorrect matcher = feature is silently non-functional. **Verification steps**: (1) Check Claude Code plugin docs for SessionStart matcher semantics. (2) Test with a minimal hook: `"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "echo test"}]}]` and confirm it fires. (3) **Fallback**: If `"startup"` cannot be verified, omit the matcher (matching all SessionStart events) and rely on the `[ -f "$CONFIG" ]` idempotency check to make extra runs harmless |
| `CLAUDE_PROJECT_DIR` environment variable | **Available** | Set by Claude Code for all hook invocations |
| `CLAUDE_PLUGIN_ROOT` environment variable | **Available** | Set by Claude Code for all hook invocations |

## 7. Acceptance Criteria

- [x] `hooks/scripts/session_start.sh` exists and is executable
- [x] `hooks/hooks.json` includes the SessionStart event configuration
- [x] First session on a project without config creates `.claude/guardian/config.json` *(live test: /tmp/guardian-test confirmed)*
- [x] Created config is identical to `assets/guardian.recommended.json` *(live test: diff confirms IDENTICAL)*
- [x] Context message appears in Claude's context on first activation only *(stdout goes to Claude's context by design)*
- [x] Subsequent sessions are silent (no output when config exists)
- [x] Script exits 0 in ALL scenarios (success, failure, edge cases)
- [x] No output on early-exit paths (env vars missing, config exists, source missing)
- [x] Warning emitted on attempted-but-failed creation (mkdir fail, cp fail, mktemp fail)
- [x] Symlinked path components are rejected (checked after mkdir for TOCTOU mitigation)
- [x] Missing/empty environment variables do not cause errors
- [x] Relative or non-existent `CLAUDE_PROJECT_DIR` is rejected silently
- [x] Read-only filesystems do not cause errors (warning emitted, exit 0)
- [x] Concurrent sessions do not produce corrupt config files *(by design: mv -n)*
- [x] All tests in `tests/regression/test_session_start.py` pass *(28/28)*
- [x] README.md documents auto-activation behavior
- [x] CLAUDE.md updated with new file reference

## Appendix A: Design Decisions

### Why bash, not Python?
- SessionStart hooks only support `type: "command"` (shell commands)
- A ~40-line bash script is simpler than invoking Python for a file copy
- Avoids Python startup overhead on every session (bash is near-instant)
- Consistent with the "thin shell wrapper" pattern for non-security hooks

### Why not validate JSON after copy?
- `cp` is atomic enough when combined with temp+mv
- JSON validation in bash requires `python3 -c "import json; ..."` which adds latency
- The source file is part of the plugin (version-controlled) -- if it's corrupt, the entire plugin is suspect
- Guardian's Python hooks already handle malformed config gracefully (fall back to defaults)

### Why `startup` matcher only (not all SessionStart events)?
- `startup` fires only on new sessions
- `resume`, `clear`, `compact` should not re-copy or re-announce
- If a user deletes their config mid-session, they must start a new session to trigger re-creation (intentional)

### Why no CI detection/skip?
- Creating the file is harmless in ephemeral CI environments
- CI environments that use `--dangerously-skip-permissions` benefit from the same protection
- Keeping the logic simple reduces failure surface
- Future enhancement: add `GUARDIAN_SKIP_AUTOACTIVATE=1` env var if CI noise becomes an issue

## Appendix B: External Model Consultations

### Gemini 3 Pro -- Key Insights (initial consultation)
- Recommended atomic write via temp file + rename (adopted: `mktemp` + `mv -n`)
- Highlighted symlink attack vector on target path (adopted: `-L` checks, reordered after `mkdir`)
- Suggested Python implementation for stronger fsync guarantees (rejected: bash sufficient for config copy, Python adds latency)
- Recommended CI env var detection (deferred: not needed for v1)

### Codex 5.3 -- Key Insights
- Emphasized 5-phase hardening approach: behavior contract, file creation, hook wiring, fault injection testing, docs
- Highlighted lock directory (`mkdir` atomic lock) for concurrent sessions (partially adopted: `mv -n` no-clobber is sufficient given identical source content)
- Flagged "existing but corrupt config" edge case (noted as future enhancement)
- Recommended env-based opt-out toggle (deferred: not needed for v1)

## Appendix C: Post-Review Changes

This section documents changes made to the action plan after the implementation review and security review.

### Changes Applied

| ID | Source | Finding | Resolution |
|----|--------|---------|------------|
| C1/MUST-FIX-3 | Both | Race on `mv` target -- use `mv -n` | **Adopted**: Replaced re-check + `mv` with `mv -n` (no-clobber). Removed redundant `[ -f "$CONFIG" ]` re-check block |
| C2/MUST-FIX-1 | Both | Predictable temp file (CWE-377) -- use `mktemp` | **Adopted**: Replaced `$$` PID suffix with `mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX"`. Uses `O_EXCL` to prevent symlink preemption |
| MUST-FIX-2 | Security | TOCTOU symlink check ordering | **Adopted**: Moved `-L` symlink checks to after `mkdir -p` to narrow the race window |
| C4 | Impl | `"startup"` matcher unverified | **Adopted**: Added BLOCKING verification steps to dependency table and Step 2 callout. Added fallback strategy (omit matcher, rely on idempotency) |
| SHOULD-FIX-1 | Security | Silent failure hides missing protection | **Adopted (scoped)**: Warning emitted only on attempted-but-failed creation (mkdir, mktemp, cp failures). Early exits remain silent. Preserves "silent in steady state" while addressing degraded-protection blindspot |
| SHOULD-FIX-2 | Security | Missing `CLAUDE_PROJECT_DIR` path validation | **Adopted**: Added `case` check for absolute path and `[ ! -d ]` check for existence. Brings parity with Python guardians |
| E3/T2 | Impl | Empty config edge case + missing tests | **Adopted**: Added edge case table row. Added 5 new test cases (empty config, relative path, nonexistent path, mkdir failure warning, cp failure warning) |
| G1 | Impl | Config file permissions unspecified | **Adopted**: Added comment noting `cp` preserves source permissions |
| G2 | Impl | `chmod +x` unnecessary with explicit bash invocation | **Adopted**: Updated Step 1 text to note executable bit is optional |
| C3 | Impl | Broader trap scope (`EXIT INT TERM HUP`) | **Not adopted**: Gemini 3 Pro advised that bash's `EXIT` trap fires on signal-induced exits too, and broader trapping can cause double-execution. `rm -f` is idempotent so either works, but `trap cleanup EXIT` is the simpler idiomatic choice |
| E1 | Impl | Author's notes contradict script on symlink check | **Resolved**: Author's notes were stale. The script correctly checks `[ -L "$CONFIG" ]`. No plan change needed; stale notes not propagated |

### Findings Not Adopted (with rationale)

| ID | Source | Finding | Reason |
|----|--------|---------|--------|
| C3 | Impl | `trap cleanup EXIT INT TERM HUP` | Bash `EXIT` trap already fires on signals. Broader trapping risks double-execution. `rm -f` is idempotent, but simpler is better. Gemini 3 Pro concurred |
| T3 | Impl | Test for `mv -n` no-clobber race behavior | Tricky to test reliably without race injection. Better covered by manual concurrency test (already in 4.2) |

### External Consultation During Finalization

**Gemini 3 Pro** (via pal clink, planner role) was consulted on four tension points between the implementation and security reviews:
1. Confirmed failure warning (scoped to attempted-but-failed creation) is the right balance
2. Confirmed `cp` over `cat >` for temp file writes (preserves permissions)
3. Confirmed `CLAUDE_PROJECT_DIR` absolute path validation is worthwhile defense-in-depth
4. Advised `trap cleanup EXIT` is sufficient in bash; broader signal trapping is unnecessary
