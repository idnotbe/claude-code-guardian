# V1 Accuracy Verification Report

## Date: 2026-02-16
## Reviewer: v1-accuracy teammate
## Scope: README.md and CLAUDE.md verified against implementation code

---

## INACCURATE Items (Must Fix)

### 1. INACCURATE: Ask pattern count is wrong
**README.md line 230, 611**: Says "17 ask patterns"
**Actual**: `guardian.default.json` has **18** ask patterns (counted programmatically).
**Fix**: Change "17 ask patterns" to "18 ask patterns" in both locations.

### 2. INACCURATE: zeroAccessPaths count is wrong
**README.md line 615**: Says "26 zero-access" patterns.
**Actual**: `guardian.default.json` has **27** zeroAccessPaths entries.
**Fix**: Change "26 zero-access" to "27 zero-access".

### 3. INACCURATE: readOnlyPaths count is wrong
**README.md line 615**: Says "17 read-only" patterns.
**Actual**: `guardian.default.json` has **18** readOnlyPaths entries.
**Fix**: Change "17 read-only" to "18 read-only".

### 4. INACCURATE: noDeletePaths count is wrong
**README.md line 615**: Says "26 no-delete" patterns.
**Actual**: `guardian.default.json` has **27** noDeletePaths entries.
**Fix**: Change "26 no-delete" to "27 no-delete".

### 5. INACCURATE: LOC counts in CLAUDE.md are stale
**CLAUDE.md line 10**: Says "~3,900 LOC total".
**Actual**: 4,142 LOC total across all 6 files.

**CLAUDE.md coverage table** LOC values:
| Script | Documented | Actual |
|--------|-----------|--------|
| `bash_guardian.py` | 1,231 | 1,289 |
| `_guardian_utils.py` | 2,308 | 2,426 |
| `edit_guardian.py` | 75 | 86 |
| `read_guardian.py` | 71 | 82 |
| `write_guardian.py` | 75 | 86 |
| `auto_commit.py` | 173 | 173 (correct) |

**Fix**: Update all LOC numbers and total in CLAUDE.md.

### 6. INACCURATE: Test method count is stale
**CLAUDE.md line 11 and README.md line 834**: Says "~1,009 test methods across 6 subdirectories".
**Actual**: **1,117** test methods across **7** subdirectories (core, patterns, review, _archive, usability, security, regression).
**Fix**: Update to "~1,117 methods across 7 subdirectories".

### 7. INACCURATE: CLAUDE.md line 36 -- wrong line number for `--no-verify`
**CLAUDE.md**: Says `auto_commit.py:145`.
**Actual**: The `no_verify=True` call is at line **146**.
**Fix**: Change to `auto_commit.py:146`.

### 8. INACCURATE: "type" missing from log-skip command list in README
**README.md line 601**: Says "Simple commands (`ls`, `cd`, `pwd`, `echo`, `cat`) under 10 characters are not even logged when allowed."
**Actual code** (bash_guardian.py:1248-1250): The skip list also includes `type`. Additionally, the code logic is: commands over 10 chars that DON'T start with these prefixes are logged -- meaning commands starting with `ls` (even if long) are also not logged.
**Fix**: Add `type` to the list. Consider rephrasing for precision: "Allowed commands under 10 characters, or commands starting with `ls`, `cd`, `pwd`, `echo`, `cat`, or `type`, are not logged."

---

## ACCURATE Items (Confirmed Correct)

### Configuration

- **ACCURATE**: Config option names all match exactly (`version`, `hookBehavior`, `bashToolPatterns`, `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths`, `allowedExternalReadPaths`, `allowedExternalWritePaths`, `gitIntegration`, `bashPathScan`)
- **ACCURATE**: `hookBehavior` defaults (`onTimeout: "deny"`, `onError: "deny"`, `timeoutSeconds: 10`) match code and config
- **ACCURATE**: `hookBehavior` valid values (`"allow"`, `"deny"`, `"ask"`) match schema enum
- **ACCURATE**: `timeoutSeconds` range `1-60` matches schema (`minimum: 1, maximum: 60`)
- **ACCURATE**: Config resolution chain (3-step) matches implementation in `load_guardian_config()`
- **ACCURATE**: Config path `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` matches code
- **ACCURATE**: Plugin default path `$CLAUDE_PLUGIN_ROOT/assets/guardian.default.json` matches code
- **ACCURATE**: Emergency fallback includes `.git`, `.claude`, `_archive`, `.env`, `*.pem`, `*.key`, `~/.ssh/**` -- confirmed in `_FALLBACK_CONFIG`
- **ACCURATE**: JSON syntax error behavior (falls back to plugin default, logs `[FALLBACK]`) matches code
- **ACCURATE**: `bashToolPatterns.block` patterns checked before `ask` and short-circuit on match -- confirmed in `main()` at line 990-997
- **ACCURATE**: Block pattern count is 18 -- confirmed
- **ACCURATE**: All path arrays (zeroAccessPaths, readOnlyPaths, noDeletePaths) content matches `guardian.default.json` exactly (every pattern verified)
- **ACCURATE**: `allowedExternalReadPaths` and `allowedExternalWritePaths` default to `[]` -- confirmed in config
- **ACCURATE**: `gitIntegration` all sub-options and defaults match the config file exactly
- **ACCURATE**: `autoCommit.messagePrefix` default is `"auto-checkpoint"` -- matches config
- **ACCURATE**: `preCommitOnDangerous.messagePrefix` default is `"pre-danger-checkpoint"` -- matches config
- **ACCURATE**: `identity.email` default `"guardian@claude-code.local"` -- matches config
- **ACCURATE**: `identity.name` default `"Guardian Auto-Commit"` -- matches config
- **ACCURATE**: `bashPathScan` all 4 sub-options (`enabled`, `scanTiers`, `exactMatchAction`, `patternMatchAction`) with defaults match config and schema exactly
- **ACCURATE**: `bashPathScan.scanTiers` valid values `["zeroAccess", "readOnly", "noDelete"]` match schema enum
- **ACCURATE**: `bashPathScan.exactMatchAction` valid values `["deny", "ask"]` match schema enum
- **ACCURATE**: `messagePrefix` max 30 chars -- matches `COMMIT_PREFIX_MAX_LENGTH = 30`

### Architecture

- **ACCURATE**: Five hooks registered via `hooks/hooks.json` -- confirmed (Bash, Read, Edit, Write in PreToolUse; auto_commit in Stop)
- **ACCURATE**: Hook scripts match: `bash_guardian.py`, `read_guardian.py`, `edit_guardian.py`, `write_guardian.py`, `auto_commit.py`
- **ACCURATE**: Fail modes: All 4 security hooks are fail-closed, auto-commit is fail-open -- confirmed in code
- **ACCURATE**: JSON output format with `hookSpecificOutput.permissionDecision` matches `deny_response()` and `ask_response()` helpers
- **ACCURATE**: Three decision types (`deny`, `ask`, `allow`) with correct prefix tags (`[BLOCKED]`, `[CONFIRM]`) -- confirmed in helper functions
- **ACCURATE**: "allow" = no stdout output -- confirmed (hooks call `sys.exit(0)` with no print for allow)
- **ACCURATE**: Verdict aggregation precedence `deny > ask > allow` -- confirmed in `_VERDICT_PRIORITY` dict

### Bash Guardian

- **ACCURATE**: Multi-layer defense architecture (Layer 0, 0b, 1, 2, 3, 4) -- all confirmed in `main()`
- **ACCURATE**: Layer 0 blocks commands exceeding 100KB (padding attack) -- `MAX_COMMAND_LENGTH = 100_000` in code
- **ACCURATE**: Layer 1 uses `bashPathScan` config for word-boundary matching -- confirmed in `scan_protected_paths()`
- **ACCURATE**: Layer 2 splits on `;`, `&&`, `||`, `|`, `&`, newlines -- confirmed in `split_commands()`
- **ACCURATE**: Layer 3 extracts paths from arguments and redirections (`>`, `>>`, `2>`, `&>`) -- confirmed in `extract_paths()` and `extract_redirection_targets()`
- **ACCURATE**: ANSI-C quoting (`$'...'`) is a known parser limitation -- confirmed in `split_commands()` docstring
- **ACCURATE**: Fail-closed safety net for write/delete with no resolved paths -- confirmed in code line 1033-1038
- **ACCURATE**: All layers complete before decision -- confirmed by verdict aggregation pattern

### Path Guardian

- **ACCURATE**: Check order for Read/Edit/Write matches the implementation in `run_path_guardian_hook()`:
  1. Malformed JSON input -> Deny (all)
  2. Null bytes -> Deny (all)
  3. Path resolution failure -> Deny (all)
  4. Symlink escape -> Deny (all)
  5. Outside project (+ external path checks) -> Deny/Allow
  6. Self-guardian path -> Deny (all)
  7. Zero-access path -> Deny (all)
  8. Read-only path -> Skip for Read, Deny for Edit/Write
  9. No-delete path (existing file) -> Skip for Read/Edit, Deny for Write
- **ACCURATE**: `noDeletePaths` only enforced for Write tool on existing files -- confirmed at line 2388-2406
- **ACCURATE**: Edit tool can still modify noDelete files -- confirmed (no noDelete check for Edit)
- **ACCURATE**: External read-only paths block Write/Edit -- confirmed at line 2328

### Auto-Commit

- **ACCURATE**: Fail-open by design (ImportError exits with 0) -- confirmed
- **ACCURATE**: Skipped when circuit breaker open -- confirmed
- **ACCURATE**: Skipped when detached HEAD -- confirmed
- **ACCURATE**: Skipped when rebase/merge in progress -- confirmed
- **ACCURATE**: Skipped when no changes -- confirmed
- **ACCURATE**: Skipped when dry-run active -- confirmed
- **ACCURATE**: Skipped when `enabled=false` or `onStop=false` -- confirmed
- **ACCURATE**: Commit message format `{prefix}: {timestamp}` -- confirmed at line 133
- **ACCURATE**: Max 72 characters per Git convention -- `COMMIT_MESSAGE_MAX_LENGTH = 72`
- **ACCURATE**: Uses `--no-verify` unconditionally -- confirmed at line 146
- **ACCURATE**: `includeUntracked: true` warning about secrets -- matches documented security risk

### Archive-Before-Delete

- **ACCURATE**: Archive location `_archive/{YYYYMMDD_HHMMSS}_{title}/` -- confirmed in `archive_files()`
- **ACCURATE**: `_deletion_log.json` contains timestamp, command, original paths -- confirmed in `create_deletion_log()`
- **ACCURATE**: Max 100MB per file -- `ARCHIVE_MAX_FILE_SIZE_MB = 100`
- **ACCURATE**: Max 500MB total -- `ARCHIVE_MAX_TOTAL_SIZE_MB = 500`
- **ACCURATE**: Max 50 files -- `ARCHIVE_MAX_FILES = 50`
- **ACCURATE**: Symlinks preserved as symlinks (`symlinks=True`) -- confirmed at line 823, 828
- **ACCURATE**: Archive failure warning about permanent data loss -- confirmed at line 1149-1156

### Self-Guarding

- **ACCURATE**: Protects `.claude/guardian/config.json` -- confirmed in `SELF_GUARDIAN_PATHS`
- **ACCURATE**: Also protects whichever config was loaded (dynamic path) -- confirmed in `is_self_guardian_path()`
- **ACCURATE**: Cannot be disabled via configuration -- it's hardcoded
- **ACCURATE**: Blocks Read, Edit, and Write tools -- confirmed (check runs for all tool_names in `run_path_guardian_hook`)

### Circuit Breaker

- **ACCURATE**: Auto-resets after 1 hour -- `CIRCUIT_TIMEOUT_SECONDS = 3600`
- **ACCURATE**: Stored at `.claude/guardian/.circuit_open` -- confirmed
- **ACCURATE**: Can be manually reset by deleting the file -- confirmed in code
- **ACCURATE**: Cleared on successful auto-commit -- confirmed (`clear_circuit()` at line 154 of auto_commit.py)
- **ACCURATE**: Only affects auto-commit, not security hooks -- confirmed (only checked in auto_commit.py and bash_guardian pre-commit)

### Security Model

- **ACCURATE**: Null byte injection detection -- confirmed in `run_path_guardian_hook()` at line 2296
- **ACCURATE**: Padding attack prevention (>100KB) -- confirmed
- **ACCURATE**: Symlink escape checks -- confirmed
- **ACCURATE**: Path traversal via `Path.resolve(strict=False)` -- confirmed
- **ACCURATE**: ReDoS protection with 0.5s timeout when `regex` package installed -- confirmed

### Environment Variables

- **ACCURATE**: `CLAUDE_PROJECT_DIR` -- confirmed in `get_project_dir()`
- **ACCURATE**: `CLAUDE_PLUGIN_ROOT` -- confirmed in `_get_plugin_root()`
- **ACCURATE**: `CLAUDE_HOOK_DRY_RUN` with values `1`, `true`, `yes` (case-insensitive) -- confirmed in `is_dry_run()`

### Log Levels

- **ACCURATE**: All documented log levels (`[ALLOW]`, `[BLOCK]`, `[ASK]`, `[SCAN]`, `[ARCHIVE]`, `[DRY-RUN]`, `[ERROR]`, `[WARN]`, `[FALLBACK]`) are used in code

### Runtime Files

- **ACCURATE**: `.claude/guardian/guardian.log` -- confirmed in `log_guardian()`
- **ACCURATE**: Auto-rotates at 1MB, keeps one backup as `.log.1` -- `MAX_LOG_SIZE_BYTES = 1_000_000`, backup pattern confirmed in `_rotate_log_if_needed()`
- **ACCURATE**: `.claude/guardian/.circuit_open` -- confirmed
- **ACCURATE**: `_archive/` directory -- confirmed in `archive_files()`

---

## MINOR Discrepancies (Non-Critical)

### M1. "100KB" approximation
**README.md**: Says "commands exceeding 100KB" and "commands >100KB denied"
**Actual**: `MAX_COMMAND_LENGTH = 100_000` bytes = ~97.7 KB (not exactly 100KB = 102,400 bytes)
**Impact**: Very minor. The approximation is standard and acceptable for documentation purposes. No fix needed.

### M2. Case sensitivity wording
**README.md line 394**: Says "Case-sensitive on Linux, case-insensitive on Windows and macOS"
**Code**: `if sys.platform != "linux"` -- which means non-Linux platforms are case-insensitive. This is correct for macOS (darwin) and Windows (win32). Accurate.

### M3. Pre-danger checkpoint "enabled" code default vs config default
**Code** (`bash_guardian.py:1182`): `pre_commit_config.get("enabled", False)` -- code defaults to `False`.
**Config** (`guardian.default.json`): `"enabled": true`
**README**: Documents the config default as `true`.
**Impact**: The README correctly documents the shipped config default. The code fallback only matters when config is missing the field entirely, which wouldn't happen with the default config. No fix needed, but a note could be helpful.

---

## Summary

| Category | Count |
|----------|-------|
| INACCURATE (must fix) | 8 |
| ACCURATE (confirmed) | 80+ individual claims |
| MINOR (non-critical) | 3 |

### Priority Fixes
1. **Pattern/path counts** (items 1-4): Fix all four counts in README.md
2. **LOC counts** (item 5): Update CLAUDE.md coverage table
3. **Test counts** (item 6): Update both CLAUDE.md and README.md
4. **Line number** (item 7): Fix CLAUDE.md line number reference
5. **Log-skip list** (item 8): Add `type` to README list
