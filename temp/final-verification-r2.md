# Final Verification Round 2 -- SessionStart Auto-Activate

**Reviewer**: Independent R2 (adversarial mindset)
**Date**: 2026-02-22
**Files reviewed**: `session_start.sh`, `hooks.json`, `test_session_start.py`, `session-start-auto-activate.md`, `README.md`, `CLAUDE.md`, `commands/init.md`

---

## 1. Script vs. Action Plan Diff

Compared the implemented script (`hooks/scripts/session_start.sh`, 78 lines) against the action plan code block (`action-plans/session-start-auto-activate.md`, Step 1, lines 27-103).

### Differences Found

| # | Location | Action Plan Script | Implemented Script | Intentional? |
|---|----------|-------------------|-------------------|-------------|
| 1 | Line 56 (cp comment) | `# cp preserves source file permissions (typically 0644 from the repo).` | `# cp to mktemp file inherits the temp file's permissions (0600 from O_EXCL).` | **YES -- improvement.** The plan's comment was factually wrong. `cp` to an *existing* file (the mktemp output) does NOT preserve source permissions -- it writes to the existing file descriptor, inheriting the temp file's 0600 mode. The implemented comment is technically correct. |
| 2 | Lines 70-71 (chmod 644) | Not present | `chmod 644 "$CONFIG" 2>/dev/null` added after `mv -n` | **YES -- bug fix.** Without this, the config would be created with 0600 permissions (from mktemp's O_EXCL), which would prevent other users/processes from reading it. The `chmod 644` ensures the config matches the expected permissions for a committed config file. |
| 3 | Line count | 102 lines (lines 27-103 in plan, after subtracting fences) = 76 lines of script | 78 lines | **Expected.** Two extra lines from the `chmod` addition. |

### Verdict: All differences are intentional improvements

The two changes are causally related: the comment fix (diff #1) corrects a factual error about how `cp` interacts with mktemp'd files, and the chmod addition (diff #2) fixes the resulting permission problem. Both are correct.

---

## 2. End-to-End Flow Analysis

### Step-by-step trace

| Step | Action | What Could Go Wrong | Tested? |
|------|--------|-------------------|---------|
| 1. Plugin load | Claude Code loads plugin from `--plugin-dir` | Wrong path; plugin dir doesn't contain `hooks/hooks.json` | **UNVERIFIED** -- can only test in live session. If `hooks.json` is missing/malformed, Claude Code likely ignores the plugin silently. |
| 2. hooks.json parse | Claude Code parses `hooks/hooks.json` | JSON syntax error; unknown event name; malformed matcher | **PARTIALLY VERIFIED** -- `hooks.json` is valid JSON (confirmed via structure review). SessionStart event name and `"startup"` matcher are NOT confirmed against Claude Code's runtime. |
| 3. SessionStart fires | Claude Code fires SessionStart event with source="startup" | Event may not fire; source string may differ; event may fire on resume/clear/compact too | **UNVERIFIED** -- requires live session. The `"startup"` matcher is still the #1 uncertainty in this feature. |
| 4. Matcher match | `"startup"` matcher matches the event source | Matcher semantics unknown -- could be regex, glob, exact match, or something else. If it's a prefix match, "startup" could match unexpected strings | **UNVERIFIED** -- requires live session. Fallback: if matcher doesn't work, remove it and rely on idempotency. |
| 5. Script execution | `bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session_start.sh"` | (a) `CLAUDE_PLUGIN_ROOT` not set -- script exits silently (tested). (b) `bash` not found -- would fail, but bash is essentially universal. (c) Script path wrong -- would fail with non-zero, but Claude Code may swallow it. | **PARTIALLY VERIFIED** -- the script itself handles env var missing (tested). The invocation path is correct relative to the JSON. |
| 6. Env var injection | `CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_ROOT` set | Either could be unset, empty, relative, non-existent, or pointing to a symlink | **VERIFIED** -- all these cases are tested in `TestSessionStartEnvValidation`. |
| 7. Config creation | mktemp + cp + mv -n | Permission denied, disk full, race condition, symlink attack | **VERIFIED** -- filesystem tests cover readonly, cp failure. Symlink tests cover all three attack vectors (.claude, .claude/guardian, config.json). |
| 8. chmod 644 | `chmod 644 "$CONFIG" 2>/dev/null` | chmod fails (e.g., file no longer exists due to race) | **PARTIALLY VERIFIED** -- the `2>/dev/null` swallows errors, and chmod failure after successful mv is benign. No dedicated test for chmod failure, but the risk is extremely low. |
| 9. stdout context | Echo lines go into Claude's context | Claude Code may truncate long stdout; may not inject SessionStart hook output into context; may prepend/append framework text | **UNVERIFIED** -- requires live session. If stdout is not injected, the feature is cosmetically degraded but functionally complete (config still gets created). |

### Gaps Not Covered by Tests

1. **`"startup"` matcher verification** -- The most critical unknown. If the matcher doesn't match, the hook never fires, and the entire feature is silently non-functional. The action plan explicitly marked this as BLOCKING (Section 6, dependency table), yet it is still unverified.

2. **`mv -n` portability across macOS** -- On GNU coreutils 9.4 (this system), `mv -n` returns exit code 1 when target exists and prints `mv: not replacing '...'` to stderr. On macOS (BSD mv), `mv -n` returns exit code 0 even when it declines to move. This means the `if ! mv -n ...` guard is **silently bypassed on macOS** -- the `mv` succeeds (returns 0) but doesn't actually move the file, so the script falls through to print the success message even though config was NOT created by this session. **Impact**: On macOS, a race condition could cause two sessions to both print the activation message, but only one actually creates the config. The second session would print "Activated" but didn't actually write the file. This is cosmetically wrong but not a security issue (the file content is identical either way).

3. **stdout injection into Claude's context** -- No way to test without a live Claude Code session. If SessionStart hook stdout is not displayed/injected, the user never sees the activation message.

4. **Orphaned temp file cleanup** -- If the script is killed between mktemp and mv (e.g., Claude Code timeout), a `.config.json.tmp.XXXXXX` file is left in `.claude/guardian/`. The `trap cleanup EXIT` handles normal exits and signals, but not `kill -9`. This is a minor concern (hidden dotfile, cleaned on next successful run).

5. **`CLAUDE_PLUGIN_ROOT` not a directory** -- The script checks `[ ! -d "$CLAUDE_PLUGIN_ROOT" ]` but does NOT validate that it's an absolute path. A relative `CLAUDE_PLUGIN_ROOT` would construct a relative `SOURCE` path, which could work unexpectedly depending on CWD. However, Claude Code almost certainly sets this to an absolute path, so the risk is negligible.

---

## 3. Acceptance Criteria Audit

From Section 7 of the action plan:

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `hooks/scripts/session_start.sh` exists and is executable | **VERIFIED** | File exists, permissions are `-rwxr-xr-x` (755). |
| 2 | `hooks/hooks.json` includes the SessionStart event configuration | **VERIFIED** | Confirmed: SessionStart is the first entry in hooks, with `"matcher": "startup"` and correct command path. |
| 3 | First session on a project without config creates `.claude/guardian/config.json` | **VERIFIED (tests)** / **UNVERIFIED (live)** | `test_first_run_creates_config` passes. Live behavior depends on step 3/4 of flow analysis. |
| 4 | Created config is identical to `assets/guardian.recommended.json` | **VERIFIED** | `test_created_config_matches_source` does byte-for-byte comparison. |
| 5 | Context message appears in Claude's context on first activation only | **VERIFIED (tests)** / **UNVERIFIED (live)** | `test_first_run_stdout_messages` checks all 4 lines. Live stdout injection untested. |
| 6 | Subsequent sessions are silent (no output when config exists) | **VERIFIED** | `test_existing_config_silent` and `test_idempotent_double_run` both confirm empty stdout. |
| 7 | Script exits 0 in ALL scenarios (success, failure, edge cases) | **VERIFIED** | `TestSessionStartExitCodes` class covers 6 scenarios. All other tests also assert `returncode == 0`. |
| 8 | No output on early-exit paths (env vars missing, config exists, source missing) | **VERIFIED** | `TestSessionStartEnvValidation` and `TestSessionStartExistingConfig` all assert `stdout == ""`. |
| 9 | Warning emitted on attempted-but-failed creation (mkdir fail, cp fail, mktemp fail) | **PARTIALLY VERIFIED** | mkdir fail and cp fail have dedicated tests. mktemp fail is NOT directly tested (hard to simulate mktemp failure without root or full disk). |
| 10 | Symlinked path components are rejected (checked after mkdir for TOCTOU mitigation) | **VERIFIED** | 4 symlink tests: `.claude` symlink, `.claude/guardian` symlink, dangling config symlink, valid-target config symlink. |
| 11 | Missing/empty environment variables do not cause errors | **VERIFIED** | `test_missing_project_dir_env`, `test_empty_project_dir_env`, `test_missing_plugin_root_env`. |
| 12 | Relative or non-existent `CLAUDE_PROJECT_DIR` is rejected silently | **VERIFIED** | `test_relative_project_dir_rejected`, `test_nonexistent_project_dir_rejected`. |
| 13 | Read-only filesystems do not cause errors (warning emitted, exit 0) | **VERIFIED** | `test_readonly_filesystem` uses chmod 555. |
| 14 | Concurrent sessions do not produce corrupt config files | **UNVERIFIED** | The design (mktemp + mv -n) is sound for preventing corruption. Testing concurrency requires race injection, which the plan acknowledged as infeasible in automated tests. |
| 15 | All tests in `tests/regression/test_session_start.py` pass | **VERIFIED** | 27/27 passed in 0.19s. |
| 16 | README.md documents auto-activation behavior | **VERIFIED** | Quick Start steps 3 and 5 describe auto-activation. "How auto-activation works" callout block explains opt-out. Architecture table includes Auto-Activate row. FAQ entry updated. |
| 17 | CLAUDE.md updated with new file reference | **VERIFIED** | Key source files includes `session_start.sh`. Coverage Gaps table includes `session_start.sh` with "Full (27 tests)". Security invariants includes "SessionStart auto-activate is fail-open by design". Repository Layout updated to "6 Python files + 1 bash script". |

### Summary: 13 VERIFIED, 3 PARTIALLY VERIFIED, 1 UNVERIFIED

---

## 4. Remaining Work

### MUST DO (blocking for "done" status)

1. **Live session verification of `"startup"` matcher** -- Start a Claude Code session with `--plugin-dir` pointing to this repo, on a project with no `.claude/guardian/config.json`. Confirm:
   - (a) The hook fires on `claude` startup (new session)
   - (b) The config file is created at the expected path
   - (c) The context message appears in Claude's conversation context
   - (d) On a second session (config now exists), the hook is silent
   - (e) On `resume`, the hook does NOT re-fire (or if it does, is still silent due to idempotency)

   This is the single most critical verification. Without it, the feature could be entirely non-functional in production.

2. **Live session verification of stdout injection** -- Confirm that SessionStart hook stdout actually appears in Claude's context (not swallowed or discarded by the runtime). If it doesn't appear, the feature still works (config gets created) but the UX is degraded.

### SHOULD DO (improvements, not blocking)

1. **Add a test for created file permissions (0644)** -- The `chmod 644` was added as a bug fix, but there's no test asserting the created config has 0644 permissions. A test like:
   ```python
   def test_created_config_permissions(self):
       _run_session_start(...)
       mode = os.stat(self.config_path).st_mode & 0o777
       self.assertEqual(mode, 0o644)
   ```
   This would catch regressions if the chmod line is accidentally removed.

2. **Document macOS `mv -n` behavior** -- On macOS (BSD), `mv -n` returns exit 0 even when declining to overwrite. This means the `if ! mv -n ...` guard is ineffective on macOS (the script will fall through to print "Activated" even if another session already created the config). Add a comment in the script noting this platform difference and why it's acceptable (config content is identical, so the cosmetic duplicate message is harmless).

3. **Add mktemp failure test** -- Criterion 9 (mktemp fail warning) is hard to test directly, but could be simulated by making the config directory read-only AFTER mkdir succeeds:
   ```python
   def test_mktemp_failure_emits_warning(self):
       config_dir = os.path.join(self.project_dir, ".claude", "guardian")
       os.makedirs(config_dir, exist_ok=True)
       os.chmod(config_dir, stat.S_IRUSR | stat.S_IXUSR)  # can't create temp files
       result = _run_session_start(...)
       self.assertIn("Could not auto-activate", result.stdout)
   ```

4. **Update `commands/init.md`** -- The action plan (Step 3c) noted an optional update to mention that config may already exist from auto-activation. Currently, `init.md` Step 1 says "If found, read it and ask..." which works fine with auto-activated configs, but doesn't mention auto-activation as a reason why the config might exist. Low priority.

### NICE TO HAVE (future enhancements)

1. **`GUARDIAN_SKIP_AUTOACTIVATE=1` environment variable** -- Mentioned in the action plan as a future enhancement for CI environments. Not needed for v1.

2. **JSON validation after copy** -- The plan explicitly decided against this (Appendix A: "Why not validate JSON after copy?"). The reasoning is sound.

3. **Orphaned temp file cleanup on next run** -- The script could detect and clean stale `.config.json.tmp.*` files in the config directory. Low value since they're hidden dotfiles and rare.

4. **`CLAUDE_PLUGIN_ROOT` absolute path validation** -- Add a `case` check like the one for `CLAUDE_PROJECT_DIR`. Negligible risk since Claude Code controls this variable.

---

## 5. Overall Assessment

The implementation is solid. The script is well-defended against the edge cases listed in the action plan. The test suite covers 27 scenarios with good breadth across environment validation, filesystem edge cases, symlink attacks, and exit code invariants. The two deviations from the plan (comment fix and chmod 644 addition) are both genuine improvements.

**The only blocking item is live session verification.** The `"startup"` matcher is the linchpin -- if it doesn't match, the feature silently does nothing. The action plan was clear about this being a BLOCKING dependency, and it remains the final gate before marking this as "done."

**Risk assessment**: LOW. Even if the live verification reveals the matcher is wrong, the fix is a one-line change to `hooks.json` (change/remove the matcher). The script itself is production-ready.
