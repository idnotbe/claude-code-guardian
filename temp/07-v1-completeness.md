# V1 Completeness Verification Report

**Reviewer**: v1-completeness
**Date**: 2026-02-16
**Method**: Independent fresh scan of ALL implementation files, compared against README.md and CLAUDE.md

## Summary

The README.md is **very thorough** -- it covers the vast majority of features, config options, and behaviors present in the implementation. However, a fresh scan uncovered several undocumented or under-documented items. Most are minor implementation details, but a few are user-facing behaviors that would be helpful to document.

## Findings

### FINDING-01: Constants not documented (Minor)

**What's missing**: The specific numeric values for internal constants are not documented in the README.

**Where in code**: `_guardian_utils.py` lines 79-102

| Constant | Value | Documented? |
|----------|-------|-------------|
| `MAX_COMMAND_LENGTH` | 100,000 bytes | YES (mentioned as "100KB" in README) |
| `MAX_LOG_SIZE_BYTES` | 1,000,000 (1MB) | YES (mentioned in README) |
| `REGEX_TIMEOUT_SECONDS` | 0.5s | Partially (README says "0.5s timeout" for regex) |
| `COMMIT_MESSAGE_MAX_LENGTH` | 72 chars | YES ("max 72 characters") |
| `COMMIT_PREFIX_MAX_LENGTH` | 30 chars | YES ("max 30 chars" in table) |
| `HOOK_DEFAULT_TIMEOUT_SECONDS` | 10 | YES (in hookBehavior table) |
| `CIRCUIT_TIMEOUT_SECONDS` | 3600 (1 hour) | YES ("auto-expires after 1 hour") |
| `MAX_PATH_PREVIEW_LENGTH` | 60 chars | NO |
| `MAX_COMMAND_PREVIEW_LENGTH` | 80 chars | NO |

**Assessment**: LOW priority. The undocumented constants (`MAX_PATH_PREVIEW_LENGTH`, `MAX_COMMAND_PREVIEW_LENGTH`) are purely internal logging display limits, not user-facing.

---

### FINDING-02: `HookTimeoutError` and `with_timeout()` mechanism not documented

**What's missing**: The code defines a `HookTimeoutError` exception class and a `with_timeout()` function (lines 110-169 in `_guardian_utils.py`) that uses SIGALRM on Unix and threading on Windows. However, this mechanism is **explicitly NOT used** -- see `bash_guardian.py` lines 1256-1262 which has a TODO comment explaining why.

**Assessment**: NO ACTION NEEDED. This is dead/unused code. Documenting it would be misleading since it's not actually used.

---

### FINDING-03: `sanitize_stderr_for_log()` function not documented

**What's missing**: `_guardian_utils.py` line 1345 defines `sanitize_stderr_for_log()` which masks home directory references in stderr output before logging (privacy measure). Not mentioned in docs.

**Assessment**: LOW priority. Internal implementation detail. Users don't interact with this.

---

### FINDING-04: `_get_git_env()` forces `LC_ALL=C` -- not documented

**What's missing**: `_guardian_utils.py` line 1527 shows that all git subprocess calls force `LC_ALL=C` to ensure consistent English output regardless of system locale. This is a reliability measure for internationalized systems.

**Where in code**: `_guardian_utils.py:1527-1540`

**Assessment**: MEDIUM priority for troubleshooting. Users on non-English systems might wonder why Guardian's git operations always produce English output. Worth a brief note in Troubleshooting.

**Suggested doc addition**: Add to Troubleshooting:
> **Note**: Guardian forces `LC_ALL=C` for all git operations to ensure consistent parsing. Git output in Guardian logs will be in English regardless of your system locale.

---

### FINDING-05: Git lock file retry mechanism not documented

**What's missing**: `git_add_all()`, `git_add_tracked()`, and `git_commit()` all have retry logic (default `max_retries=3`) with exponential backoff (0.5s, 1.0s, 1.5s) when encountering git lock files or timeouts. This is defined in `_guardian_utils.py` lines 1658-1998.

**Assessment**: LOW priority. Automatic retry is transparent to users. Could be briefly mentioned in Troubleshooting if users report slow operations.

---

### FINDING-06: `sanitize_commit_message()` behavior not documented

**What's missing**: `_guardian_utils.py` line 1556 defines `sanitize_commit_message()` which:
1. Removes control characters (except newline and tab)
2. Preserves all printable UTF-8 (Korean, Japanese, emojis)
3. Falls back to "[auto-commit]" if message is empty after sanitization
4. Enforces 72-char limit

**Assessment**: LOW priority. Internal implementation detail.

---

### FINDING-07: `deprecated allowedExternalPaths` config key detection

**What's missing**: `validate_guardian_config()` at line 736 checks for the deprecated `allowedExternalPaths` config key and warns to use `allowedExternalReadPaths` or `allowedExternalWritePaths` instead. This deprecation is not mentioned in the README.

**Where in code**: `_guardian_utils.py:736-742`

**Assessment**: MEDIUM priority. Users migrating from an older config version might still have this key. The README should mention this for upgrading users.

**Suggested doc addition**: Add to Upgrading section:
> **Deprecated config key**: If your config has `allowedExternalPaths`, rename it to `allowedExternalReadPaths` (for read-only) or `allowedExternalWritePaths` (for read+write). The old key is no longer supported.

---

### FINDING-08: `noDeletePaths` enforcement scope partially documented

**What's missing**: The README mentions `noDeletePaths` blocks Write tool overwrite of existing files, but doesn't clarify that the Write tool check specifically calls `expand_path()` and `exists()` to verify the file exists, and fails-closed (assumes file exists) if the existence check errors.

**Where in code**: `_guardian_utils.py:2387-2406` (`run_path_guardian_hook`)

**Assessment**: LOW priority. The README already documents the behavior adequately with the limitation note. The fail-closed implementation detail is for CLAUDE.md, which already covers it.

---

### FINDING-09: Fallback config content not documented

**What's missing**: The README mentions there's a "hardcoded minimal config" as emergency fallback but doesn't list what it protects. The actual fallback (`_FALLBACK_CONFIG` in `_guardian_utils.py:369-417`) protects:
- Block patterns: root deletion, .git deletion, .claude deletion, _archive deletion, force push, interpreter deletion
- Ask patterns: force push with lease, hard reset
- zeroAccess: .env, .env.*, *.pem, *.key, ~/.ssh/**, ~/.gnupg/**, ~/.aws/**, secrets.json, secrets.yaml
- readOnly: .claude/guardian/config.json, node_modules/**, __pycache__/**, .venv/**, poetry.lock
- noDelete: .git/**, .claude/**, _archive/**, CLAUDE.md

**Assessment**: MEDIUM priority. Users should know what's protected when the fallback is active. The README already says "protecting `.git`, `.claude`, `_archive`, `.env`, `*.pem`, `*.key`, and `~/.ssh/**`" which covers the highlights but is incomplete.

**Suggested doc addition**: Expand the emergency fallback description to include all protected paths, or add a note: "See `_FALLBACK_CONFIG` in `_guardian_utils.py` for the complete fallback rule set."

---

### FINDING-10: `allow_response()` helper exists but not used for actual allow decisions

**What's missing**: The code defines `allow_response()` at `_guardian_utils.py:1416` which generates an explicit allow response. The README says "allow: Permit the operation silently (or: produce no stdout output)." In practice, the code mostly uses `sys.exit(0)` without printing for allow decisions, but `allow_response()` is used in one place: `run_path_guardian_hook` when file_path is empty.

**Assessment**: NO ACTION NEEDED. The README accurately describes both options.

---

### FINDING-11: Config validation details not fully documented

**What's missing**: `validate_guardian_config()` at line 653 performs extensive validation:
- Required sections: `bashToolPatterns`, `zeroAccessPaths`
- hookBehavior value validation (must be "allow", "deny", or "ask")
- timeoutSeconds must be positive number
- Regex pattern syntax validation (compiles each pattern)
- Path array type checking
- gitIntegration.autoCommit.enabled type checking
- Deprecated key detection

The README mentions "Config validation warnings" in the troubleshooting table but doesn't detail what gets validated.

**Assessment**: LOW priority. The troubleshooting entry is sufficient for users. Detailed validation rules are implementation details.

---

### FINDING-12: `match_path_pattern` `default_on_error` parameter behavior

**What's missing**: `_guardian_utils.py:1121` `match_path_pattern()` has a `default_on_error` parameter. Deny-list checks (zeroAccess, readOnly, noDelete) use `default_on_error=True` (fail-closed: assume match on error), while allow-list checks (allowedExternalReadPaths, allowedExternalWritePaths) use `default_on_error=False` (fail-closed: assume no match on error). This dual-default is a critical security design decision.

**Assessment**: LOW priority for README (user docs), but worth noting in CLAUDE.md security model. CLAUDE.md already says "Helper functions used for boundary checks must not fail-open" which covers the spirit of this.

---

### FINDING-13: Self-guarding also blocks Read tool (not just Edit/Write)

**What's missing**: The README's Self-Guarding section says: "The Edit, Write, or Read tools are all blocked from accessing `.claude/guardian/config.json`." This is actually correct! The `run_path_guardian_hook()` function applies the self-guardian check for all three tools (Read, Edit, Write). However, the narrative description might give the impression it's only Edit/Write. The current text is accurate.

**Assessment**: NO ACTION NEEDED. Already correctly documented.

---

### FINDING-14: `$comment` field in config not documented

**What's missing**: The JSON schema (`guardian.schema.json`) and default config (`guardian.default.json`) support a `$comment` field at the root level and inside `bashToolPatterns`. This allows users to add documentation comments to their config files. Not mentioned in the README.

**Where in code**: `guardian.schema.json:20-22`, `guardian.schema.json:69-72`

**Assessment**: LOW priority. Nice-to-know feature but `$comment` is a common JSON convention.

---

### FINDING-15: `$schema` field support in config not documented

**What's missing**: The JSON schema allows a `$schema` field in config files, which enables IDE validation. Users could add `"$schema": "./path/to/guardian.schema.json"` for autocompletion and validation in VS Code.

**Where in code**: `guardian.schema.json:14-17`

**Assessment**: MEDIUM priority. This is a useful developer experience feature that should be mentioned.

**Suggested doc addition**: Add to Configuration section:
> **IDE validation**: Add `"$schema": "../../assets/guardian.schema.json"` (adjust path to your plugin install) to your config file for autocompletion and validation in VS Code and other JSON Schema-aware editors.

---

### FINDING-16: Plugin UX components (commands, skills, agents) not documented in README

**What's missing**: `plugin.json` registers:
- `./commands/init.md` (the `/guardian:init` wizard)
- `./skills/config-guide` (the config guide skill)
- `./agents/config-assistant.md` (the config assistant agent)

The README mentions `/guardian:init` and "the config assistant" but doesn't explicitly list these as distinct plugin components or explain how to invoke the config guide skill vs the config assistant agent.

**Assessment**: LOW-MEDIUM priority. The README mentions the functionality but not the invocation mechanism for skills/agents beyond `/guardian:init`.

---

### FINDING-17: Case sensitivity behavior documented but not all platforms

**What's missing**: The code at multiple places (`_guardian_utils.py:945-946`, `1081-1082`, `1146-1147`, `2190-2191`) uses `sys.platform != "linux"` for case-insensitive path matching. This means:
- Linux: case-sensitive
- macOS: case-insensitive
- Windows: case-insensitive

The README says "Case-sensitive on Linux, case-insensitive on Windows and macOS" in the Glob Pattern Syntax section and in Common Pitfalls. This is correctly documented.

**Assessment**: NO ACTION NEEDED.

---

### FINDING-18: `is_using_fallback_config()` and `get_active_config_path()` exist as API

**What's missing**: These utility functions exist for programmatic use but are only used internally. Not documented.

**Assessment**: NO ACTION NEEDED. Internal API, not user-facing.

---

### FINDING-19: Windows compatibility details (`sys.platform == "win32"`) scattered throughout

**What's missing**: The code has several Windows-specific behaviors:
- `shlex.split(posix=False)` on Windows with quote stripping (`bash_guardian.py:498-501`)
- `rm_cmd = "del"` on Windows in error messages
- Circuit breaker file: `backup_file.unlink()` before rename on Windows
- Case-insensitive path matching on Windows

The README says "Default patterns cover both Unix and Windows commands" and has Windows-specific ask patterns (del, Remove-Item). General Windows compatibility is implied but not explicitly stated as a supported platform.

**Assessment**: LOW-MEDIUM priority. Could add a brief note about Windows support status.

---

### FINDING-20: `evaluate_rules()` function exists as a simplified API

**What's missing**: `_guardian_utils.py:1435` defines `evaluate_rules()` as a simpler orchestration function that only checks block and ask patterns (no path analysis). This is exported but not used by any hook directly (bash_guardian does its own multi-layer evaluation). Could be useful for external tooling.

**Assessment**: NO ACTION NEEDED. Internal API.

---

## Issues Summary Table

| # | Finding | Priority | Action Needed? |
|---|---------|----------|---------------|
| 01 | Internal constants | LOW | No |
| 02 | Unused timeout mechanism | N/A | No (dead code) |
| 03 | `sanitize_stderr_for_log` | LOW | No |
| 04 | `LC_ALL=C` for git | MEDIUM | Yes - Troubleshooting note |
| 05 | Git retry mechanism | LOW | No |
| 06 | Commit message sanitization | LOW | No |
| 07 | Deprecated `allowedExternalPaths` key | MEDIUM | Yes - Upgrading note |
| 08 | `noDeletePaths` fail-closed on exists check | LOW | No |
| 09 | Fallback config incomplete listing | MEDIUM | Yes - small expansion |
| 10 | `allow_response()` usage | N/A | No |
| 11 | Config validation details | LOW | No |
| 12 | `default_on_error` dual-default | LOW | No |
| 13 | Self-guarding blocks Read too | N/A | Already documented |
| 14 | `$comment` field in config | LOW | No |
| 15 | `$schema` field for IDE validation | MEDIUM | Yes - developer experience |
| 16 | Plugin UX components listing | LOW-MEDIUM | Optional |
| 17 | Case sensitivity per platform | N/A | Already documented |
| 18 | Internal utility APIs | N/A | No |
| 19 | Windows compatibility status | LOW-MEDIUM | Optional |
| 20 | `evaluate_rules()` function | N/A | No |

## Recommended Documentation Changes (Priority Order)

### Must Fix (MEDIUM priority)

1. **FINDING-04**: Add note about `LC_ALL=C` in Troubleshooting
2. **FINDING-07**: Add deprecated `allowedExternalPaths` note in Upgrading
3. **FINDING-15**: Add `$schema` IDE validation tip in Configuration
4. **FINDING-09**: Expand fallback config description slightly

### Nice to Have (LOW priority)

5. **FINDING-16**: Briefly mention config-guide skill invocation
6. **FINDING-19**: Add a brief Windows support note

## Overall Assessment

**Documentation completeness: 92-95%**

The README is remarkably comprehensive for the implementation. All major features, config options, security behaviors, and edge cases are documented. The gaps found are primarily:
- Minor implementation details (internal constants, retry logic)
- Migration/upgrade aids (deprecated config keys, fallback details)
- Developer experience features ($schema support)
- Operational notes (LC_ALL=C)

No critical user-facing features or security behaviors are undocumented. The documentation accurately reflects the code's behavior in all tested areas.
