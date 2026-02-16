# Claude Code Guardian - Comprehensive Code Analysis

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [File-by-File Analysis](#file-by-file-analysis)
3. [Configuration Reference](#configuration-reference)
4. [Security Mechanisms](#security-mechanisms)
5. [Permission Decision Paths](#permission-decision-paths)
6. [Environment Variables](#environment-variables)
7. [Inter-File Dependencies](#inter-file-dependencies)
8. [Edge Cases and Special Behaviors](#edge-cases-and-special-behaviors)

---

## 1. Architecture Overview

### Hook System
Claude Code Guardian is a security guardrails plugin for Claude Code's `--dangerously-skip-permissions` mode. It intercepts tool calls via Claude Code's PreToolUse hook system for Bash, Edit, Read, and Write tools, and the Stop hook event for auto-commit.

### Hook Output Protocol
All hooks communicate decisions via JSON on stdout with the structure:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny" | "ask" | "allow",
    "permissionDecisionReason": "Human-readable reason"
  }
}
```
- **deny**: Block the operation unconditionally
- **ask**: Prompt user for confirmation before proceeding
- **allow**: Permit the operation (also: producing no stdout output = allow)

Reason strings are prefixed with `[BLOCKED]` for deny and `[CONFIRM]` for ask (text prefixes used instead of emoji for Windows cp949 encoding compatibility).

### Input Protocol
Hooks receive JSON on stdin with:
```json
{
  "tool_name": "Bash" | "Edit" | "Read" | "Write",
  "tool_input": {
    "command": "...",      // Bash tool
    "file_path": "..."    // Edit/Read/Write tools
  }
}
```

### Layered Security Architecture (Bash Guardian)
The bash guardian uses a multi-layer defense-in-depth approach:

| Layer | Name | Purpose |
|-------|------|---------|
| 0 | Block Patterns | Catastrophic command regex matching (short-circuits to deny) |
| 0b | Ask Patterns | Dangerous-but-legitimate command regex matching |
| 1 | Protected Path Scan | Raw string scan for protected filenames in command text |
| 2 | Command Decomposition | Split compound commands (`;`, `&&`, `\|\|`, `\|`, `&`, newlines) |
| 3 | Path Extraction | Extract file paths from parsed arguments and redirections |
| 4 | Command Type Detection | Classify sub-commands as write/delete operations |

**Verdict Aggregation**: All layers complete before any decision is emitted (C-1 fix). Verdicts are aggregated with precedence: deny > ask > allow. Unknown verdict strings default to deny priority (fail-closed).

### Fail-Close vs Fail-Open Design
- **Security hooks (Bash, Edit, Read, Write)**: Fail-closed -- deny on error or timeout
- **Auto-commit (Stop hook)**: Fail-open by design -- commit failure must never block session termination
- **Logging**: Silent fail -- never breaks hook execution
- **Git operations**: Generally fail-open (return False/empty on error)
- **Path normalization**: Returns unresolved path on exception (fail-open, but mitigated by independent checks)

---

## 2. File-by-File Analysis

### 2.1 `bash_guardian.py` (~1290 LOC)

**Purpose**: Intercepts and evaluates all Bash tool calls.

#### Entry Point
- Reads JSON from stdin
- Only processes events where `tool_name == "Bash"`
- Extracts `tool_input.command`

#### Import Failure Handling
If `_guardian_utils` import fails, immediately emits a deny response and exits (fail-closed).

#### Execution Flow (main function)
1. Get project directory (deny if unset)
2. Parse stdin JSON (deny on malformed JSON)
3. Verify tool_name is "Bash" (exit silently otherwise)
4. Load config once
5. **Layer 0**: Block patterns -- short-circuits on deny
6. **Layer 0b**: Ask patterns -- accumulates verdict
7. **Layer 1**: Protected path scan -- accumulates verdict
8. **Layer 2+3+4**: For each sub-command:
   - Detect write/delete type
   - Extract paths from arguments (with `allow_nonexistent` for write/delete)
   - Extract redirection targets
   - Check each path against: symlink escape, zeroAccess, readOnly (for writes), external read-only (for writes/deletes), noDelete (for deletes)
   - **Fail-closed safety net**: If write/delete detected but no paths resolved, escalate to "ask"
9. Emit final verdict
10. Handle deletions with archiving (if applicable)
11. Pre-commit for dangerous operations (if ask verdict)

#### Top-Level Exception Handler
- Catches all unhandled exceptions
- Opens circuit breaker
- Uses `hookBehavior.onError` from config (default: "deny")
- If hookBehavior lookup itself fails, falls back to deny

#### Key Functions

**`split_commands(command)`** -- Layer 2 Command Decomposition
- Splits on: `;`, `&&`, `||`, `|`, `&` (as background separator), newlines
- Respects: single quotes, double quotes, `$()` command substitution, `<()` / `>()` process substitution, backtick substitution, backslash escapes
- Does NOT handle ANSI-C quoting (`$'...'`) -- known limitation
- Properly handles `&>`, `>&`, `<&`, `n>&` as redirections (not separators)

**`glob_to_literals(pattern)`** -- Layer 1 Helper
- Converts glob patterns to literal search strings for raw string scanning
- Exact matches: returns `[pattern]`
- Prefix patterns (`name.*`): returns `["name."]`
- Suffix patterns (`*.ext`): returns `[".ext"]` only if extension >= 4 chars and not in generic words (`env`, `key`, `log`)
- Generic patterns (`*.env`, `*credentials*`): returns `[]` (too noisy)

**`scan_protected_paths(command, config)`** -- Layer 1
- Controlled by `bashPathScan` config section
- Scans path tiers from `bashPathScan.scanTiers` (default: `["zeroAccess"]`)
- Maps tiers: `"zeroAccess"` -> `zeroAccessPaths`, `"readOnly"` -> `readOnlyPaths`, `"noDelete"` -> `noDeletePaths`
- Uses word-boundary regex including `/` (I-4 fix for `./.env`) and `{`, `}`, `,` (for brace expansion)
- Skips directory patterns (`**` or trailing `/`)
- Returns strongest verdict found

**`extract_redirection_targets(command, project_dir)`** -- Layer 3
- Extracts paths from `>`, `>>`, `<`, `2>`, `&>`, `>|` redirections
- Quote-aware (I-5 fix)
- Skips process substitutions `>(cmd)` / `<(cmd)` (F6 fix)
- Skips variable targets (`$FILE`)

**`extract_paths(command, project_dir, allow_nonexistent)`** -- Layer 3
- Uses `shlex.split()` with POSIX mode (non-POSIX on Windows for compatibility)
- Falls back to `str.split()` on shlex failure
- Skips command name (first part)
- Handles: flags (skips `-x`), flag-concatenated paths (`-f.env` -- P1-6 fix), `dd of=` syntax (M-3 fix)
- Validates path candidates (length, no null bytes, no newlines)
- Expands `~`, `$ENV_VARS`, wildcards (`*`, `?`, `[`)
- Resolves relative paths against project_dir
- Checks: exists + within project, allow_nonexistent + would-be within project, allowed external path

**`_is_within_project_or_would_be(path, project_dir)`**
- Uses `Path.resolve(strict=False)` for canonicalization (F7 fix -- prevents `../traversal` attacks)

**`is_delete_command(command)`** -- Layer 4
- Shell delete: `rm`, `del`, `rmdir`, `Remove-Item`, `ri`
- Git: `git rm` (with optional global flags, F8 fix)
- Effective deletion: `mv X /dev/null`
- Truncation: `> file`, `: > file`, `>| file` (P1-2 fix)
- Interpreter: Python (`os.remove`, `os.unlink`, `shutil.rmtree`, `shutil.move`, `os.rmdir`, `pathlib.Path().unlink`), Node (`unlinkSync`, `rmSync`, etc.), Perl/Ruby (`unlink`, `File.delete`, `FileUtils.rm`)

**`is_write_command(command)`** -- Layer 4
- Redirection: `> file`
- Commands: `tee`, `mv`, `ln` (F2 fix: negative lookbehind prevents `ls -ln` false positive), `sed -i`, `cp`, `dd`, `patch`, `rsync`
- Truncation: `: > file`
- Metadata: `chmod`, `touch`, `chown`, `chgrp` (P1-4 fix)
- Does NOT include `install` (I-2 fix: avoids breaking npm/pip/cargo/brew/apt)

**`_is_path_candidate(s)`**
- Rejects: empty strings, strings with newlines/carriage returns/null bytes, strings > 4096 chars, path components > 255 chars

**Archive Functions**
- `archive_files(files, project_dir)`: Archives untracked files before deletion
  - Limits: 100MB per file, 500MB total, 50 files max
  - Creates `_archive/{timestamp}_{title}/` directory
  - Preserves symlinks (F5 fix -- copies symlink, not dereferenced target)
  - Handles collision via random hex suffix
  - Error handling: PermissionError, disk full (errno 28 / winerror 112), generic OSError
- `create_deletion_log(archive_dir, archived, command)`: Writes `_deletion_log.json` metadata
- `generate_archive_title(files)`: Sanitized title from first filename, max 50 chars

**Pre-commit for Dangerous Operations**
- Triggered when final verdict is "ask" and `gitIntegration.preCommitOnDangerous.enabled` is true
- Skips if rebase/merge in progress (would corrupt state)
- Only commits if there are changes and staged changes exist
- Uses `--no-verify` to bypass pre-commit hooks
- Opens circuit breaker on failure

**Logging Behavior**
- Simple commands (`ls`, `cd`, `pwd`, `echo`, `cat`, `type`) shorter than 10 chars are not logged when allowed
- All other decisions (deny/ask/allow) are logged

---

### 2.2 `_guardian_utils.py` (~2427 LOC)

**Purpose**: Shared utilities for all guardian hooks.

#### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `DRY_RUN_ENV` | `"CLAUDE_HOOK_DRY_RUN"` | Env var name for dry-run mode |
| `MAX_COMMAND_LENGTH` | `100,000` | Max command bytes before blocking |
| `MAX_PATH_PREVIEW_LENGTH` | `60` | Max path length for log display |
| `MAX_COMMAND_PREVIEW_LENGTH` | `80` | Max command length for log display |
| `MAX_LOG_SIZE_BYTES` | `1,000,000` (1 MB) | Log file size before rotation |
| `REGEX_TIMEOUT_SECONDS` | `0.5` | Default regex timeout for ReDoS defense |
| `COMMIT_MESSAGE_MAX_LENGTH` | `72` | Git commit message convention limit |
| `COMMIT_PREFIX_MAX_LENGTH` | `30` | Max commit message prefix length |
| `HOOK_DEFAULT_TIMEOUT_SECONDS` | `10` | Default hook execution timeout |
| `CIRCUIT_BREAKER_FILE` | `".circuit_open"` | Circuit breaker flag file name |
| `CIRCUIT_TIMEOUT_SECONDS` | `3600` (1 hour) | Circuit breaker auto-expiry |

#### Configuration Loading

**Config Resolution Chain (3-step)**:
1. `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` (user custom)
2. `$CLAUDE_PLUGIN_ROOT/assets/guardian.default.json` (plugin default)
3. Hardcoded `_FALLBACK_CONFIG` (emergency fallback)

Config is cached per-process (since hooks run as separate processes).

**`_FALLBACK_CONFIG`** provides minimal protection:
- Block patterns: root deletion, .git/.claude/_archive deletion, force push, interpreter deletions
- Ask patterns: force push with lease, hard reset
- zeroAccessPaths: .env, .env.*, *.pem, *.key, ~/.ssh/**, ~/.gnupg/**, ~/.aws/**, secrets.json/yaml
- readOnlyPaths: .claude/guardian/config.json, node_modules, __pycache__, .venv, poetry.lock
- noDeletePaths: .git/**, .claude/**, _archive/**, CLAUDE.md

**Config Validation (`validate_guardian_config()`)**:
- Checks required sections: `bashToolPatterns`, `zeroAccessPaths`
- Validates `hookBehavior` values (onTimeout/onError must be allow/deny/ask; timeoutSeconds must be positive)
- Validates regex pattern syntax (compiles each pattern)
- Checks path patterns are string lists
- Validates gitIntegration.autoCommit.enabled is boolean
- Warns about deprecated `allowedExternalPaths` key

#### ReDoS Defense

**`safe_regex_search(pattern, text, flags, timeout)`**:
- Strategy 1: Uses `regex` module with timeout (if installed via `pip install regex`)
- Strategy 2: Falls back to standard `re` (no timeout, logs warning on first use)
- Returns None on timeout (fail-closed for security)

#### Pattern Matching

**`match_block_patterns(command)`**:
- Fail-closed on oversized commands (> 100,000 bytes) -- padding attack prevention
- Uses `safe_regex_search` with `re.IGNORECASE | re.DOTALL`
- Returns `(matched: bool, reason: str)`

**`match_ask_patterns(command)`**:
- Same oversized command protection
- Same regex approach
- Returns `(matched: bool, reason: str)`

#### Path Matching

**`normalize_path(path)`**:
- Expands `~`, resolves relative paths against project dir, normalizes separators
- Case-insensitive on non-Linux platforms (Windows/macOS)
- Fails open (returns original path on error)

**`expand_path(path)`**:
- Expands `~`, resolves against project dir, returns absolute resolved Path
- Can raise OSError

**`normalize_path_for_matching(path)`**:
- Like normalize_path but always uses forward slashes for pattern matching
- Case-insensitive on non-Linux

**`match_path_pattern(path, pattern, default_on_error)`**:
- Handles `~` expansion in both path and pattern
- `**` recursive matching via `_match_recursive_glob()`
- `*` single-level matching via `fnmatch`
- Tries: direct fnmatch, filename-only match (for simple patterns without `/`), project-relative match
- `default_on_error` parameter: True for deny-list checks (fail-closed), False for allow-list checks

**`_match_recursive_glob(path_parts, pattern_parts)`**:
- Recursive function for `**` glob matching
- `**` matches zero or more path components

**Path tier matchers** (all use `default_on_error=True` for fail-closed):
- `match_zero_access(path)`: Checks against `zeroAccessPaths`
- `match_read_only(path)`: Checks against `readOnlyPaths`
- `match_no_delete(path)`: Checks against `noDeletePaths`

**`match_allowed_external_path(path)`**:
- Checks `allowedExternalWritePaths` first (returns `"readwrite"`)
- Then checks `allowedExternalReadPaths` (returns `"read"`)
- Returns `None` if not matched
- Uses `default_on_error=False` (fail-closed for allow-list: don't grant access on error)

#### Symlink Security

**`is_symlink_escape(path)`**:
- Returns True if path is a symlink resolving outside project directory
- Returns True on any error (fail-closed)
- Returns True if no project dir is set (fail-closed)

#### Project Boundary Check

**`is_path_within_project(path)`**:
- Resolves path and checks if it's within project directory
- Returns False on any error (fail-closed)

#### Self-Guardian Protection

**`SELF_GUARDIAN_PATHS`**: Tuple containing `".claude/guardian/config.json"` -- always protected from Edit/Write regardless of config.

**`is_self_guardian_path(path)`**:
- Checks against static `SELF_GUARDIAN_PATHS`
- Also checks against dynamic `_active_config_path` (the actually-loaded config file)
- Fails closed if normalization fails (assumes guardian path)

#### Logging

**`log_guardian(level, message)`**:
- Writes to `$CLAUDE_PROJECT_DIR/.claude/guardian/guardian.log`
- Format: `TIMESTAMP [LEVEL] [DRY-RUN] MESSAGE`
- Levels: INFO, WARN, ERROR, BLOCK, ASK, ALLOW, DRY-RUN, DEBUG, ARCHIVE, SCAN
- Auto-rotation at 1 MB (keeps one backup `.log.1`)
- Silent fail on any error
- No-op if CLAUDE_PROJECT_DIR is not set

**`sanitize_stderr_for_log(stderr, max_length=500)`**:
- Truncates to max_length
- Masks home directory references (replaces with `~`)

#### Hook Response Helpers
- `deny_response(reason)`: Returns deny JSON with `[BLOCKED]` prefix
- `ask_response(reason)`: Returns ask JSON with `[CONFIRM]` prefix
- `allow_response()`: Returns allow JSON (no reason)

#### Rule Evaluation

**`evaluate_rules(command)`**:
- Orchestration function: block patterns -> ask patterns -> allow
- Fails closed on any exception ("Guardian internal error")

#### Git Integration Functions

All git functions:
- Check `is_git_available()` first (cached per-process via `shutil.which`)
- Use `_get_git_env()` which sets `LC_ALL=C` for consistent English output
- Have subprocess timeouts (5-30s depending on operation)
- Handle lock file errors with retries (where applicable)

| Function | Purpose | Max Retries | Timeout | Fail Mode |
|----------|---------|-------------|---------|-----------|
| `git_is_tracked(path)` | Check if file is git-tracked | 0 | 5s | fail-open (False) |
| `git_has_changes()` | Check uncommitted changes | 0 | 10s | fail-open (False) |
| `git_has_staged_changes()` | Check staged changes | 0 | 10s | fail-open (False) |
| `git_add_all(max_retries=3)` | Stage all changes (`-A`) | 3 | 30s | fail-open (False) |
| `git_add_tracked(max_retries=3)` | Stage tracked changes (`-u`) | 3 | 30s | fail-open (False) |
| `git_commit(message, max_retries=3, no_verify=False)` | Create commit | 3 | 30s | fail-open (False) |
| `git_get_last_commit_hash()` | Get short commit hash | 0 | 5s | fail-open ("") |
| `is_detached_head()` | Check detached HEAD state | 0 | 5s | fail-open (False) |
| `is_rebase_or_merge_in_progress()` | Check active rebase/merge/cherry-pick/bisect | N/A (file check) | N/A | fail-open (False) |
| `ensure_git_config()` | Set user.email/name if missing | 0 | 5s per cmd | fail-open (True) |

**`sanitize_commit_message(message)`**:
- Removes control characters (preserves newline, tab, all printable UTF-8)
- Returns `"[auto-commit]"` if empty after sanitization
- Enforces 72-char limit

**`validate_commit_prefix(prefix, default)`**:
- Truncates to 30 chars max
- Returns default if empty

#### Circuit Breaker Pattern

- File: `$CLAUDE_PROJECT_DIR/.claude/guardian/.circuit_open`
- Format: `ISO_TIMESTAMP|REASON`
- Auto-expires after 1 hour (3600 seconds)
- Race condition handling: FileNotFoundError between exists/stat/open
- Permission errors: fail-closed (circuit treated as open)
- Functions:
  - `set_circuit_open(reason)`: Create/overwrite circuit file
  - `is_circuit_open()`: Returns `(bool, reason)` tuple
  - `clear_circuit()`: Delete circuit file

#### Hook Timeout

**`with_timeout(func, timeout_seconds)`**:
- Unix: `signal.SIGALRM` based
- Windows: `threading.Thread` with `join(timeout=...)`
- Raises `HookTimeoutError`
- **NOT currently used** by bash_guardian.py (risk of corrupting git state, partial archives)

#### Path Guardian Hook Runner

**`run_path_guardian_hook(tool_name)`**:
Shared entry point for Read/Edit/Write guardians. Checks in order:
1. Parse stdin JSON (fail-closed on malformed input)
2. Verify tool_name matches
3. Validate tool_input is dict
4. Extract and validate file_path (reject null bytes)
5. Resolve to absolute path (fail-closed on resolution failure)
6. **Symlink escape** check (deny)
7. **Project boundary** check:
   - If outside project, check `allowedExternalReadPaths` / `allowedExternalWritePaths`
   - Read-only external paths block Write/Edit
8. **Self-guardian** check (deny)
9. **zeroAccess** check (deny) -- with hint about bash alternatives being monitored
10. **readOnly** check (deny for Edit/Write, skip for Read)
11. **noDelete** check (deny for Write tool only, for existing files only) -- with hint to use Edit tool
12. Allow

---

### 2.3 `edit_guardian.py` (~87 LOC)

**Purpose**: Thin wrapper for Edit tool interception.

- Calls `run_path_guardian_hook("Edit")`
- Import failure: fail-closed deny
- Unhandled exception: uses `hookBehavior.onError` (default: deny), opens circuit breaker
- Checks applied: symlink escape, project boundary, external paths, self-guardian, zeroAccess, readOnly

---

### 2.4 `read_guardian.py` (~83 LOC)

**Purpose**: Thin wrapper for Read tool interception.

- Calls `run_path_guardian_hook("Read")`
- Import failure: fail-closed deny
- Unhandled exception: uses `hookBehavior.onError` (default: deny), opens circuit breaker
- Checks applied: symlink escape, project boundary, external paths, self-guardian, zeroAccess
- **Does NOT block readOnly paths** -- reading read-only files is allowed

---

### 2.5 `write_guardian.py` (~87 LOC)

**Purpose**: Thin wrapper for Write tool interception.

- Calls `run_path_guardian_hook("Write")`
- Import failure: fail-closed deny
- Unhandled exception: uses `hookBehavior.onError` (default: deny), opens circuit breaker
- Checks applied: symlink escape, project boundary, external paths, self-guardian, zeroAccess, readOnly, noDelete (existing files only)

---

### 2.6 `auto_commit.py` (~173 LOC)

**Purpose**: Auto-commit checkpoint on session Stop event.

**Design**: Fail-open -- import failure silently exits, unhandled exceptions log and exit 0.

#### Execution Flow
1. Log hook triggered
2. Check circuit breaker (skip if open)
3. Load config
4. Check `gitIntegration` section exists
5. Check `autoCommit.enabled` (default: false)
6. Check `autoCommit.onStop` (default: false)
7. Check for detached HEAD (skip -- commits would be orphaned)
8. Check for rebase/merge in progress (skip)
9. Check for uncommitted changes
10. Handle dry-run mode
11. Stage changes:
    - `includeUntracked=true`: `git add -A` (all files)
    - `includeUntracked=false`: `git add -u` (tracked files only)
    - **Continues even if staging fails** (best-effort -- there may be already-staged changes)
12. Create commit message: `{prefix}: {timestamp}`, max 72 chars
13. Check for staged changes (skip if none -- normal exit)
14. Commit with `--no-verify` (bypasses pre-commit hooks)
15. On success: log hash, clear circuit breaker
16. On failure: open circuit breaker

**Known Security Gap**: `--no-verify` at line 146 unconditionally bypasses pre-commit hooks. Combined with `includeUntracked=true`, this could commit secrets that pre-commit hooks would normally catch.

---

## 3. Configuration Reference

### 3.1 `hookBehavior` (required)

| Option | Type | Default | Values | Description |
|--------|------|---------|--------|-------------|
| `onTimeout` | string | `"deny"` | `"allow"`, `"deny"`, `"ask"` | Action when hook times out |
| `onError` | string | `"deny"` | `"allow"`, `"deny"`, `"ask"` | Action when hook encounters error |
| `timeoutSeconds` | number | `10` | 1-60 | Maximum seconds before timeout |

### 3.2 `bashToolPatterns` (required)

| Option | Type | Description |
|--------|------|-------------|
| `block` | array of `{pattern, reason}` | Regex patterns that are always blocked (deny) |
| `ask` | array of `{pattern, reason}` | Regex patterns requiring user confirmation (ask) |

**Default block patterns** (18 patterns):
- Root/full system deletion (`rm -rf /`)
- Git/Claude/archive directory deletion
- Force push (without `--force-with-lease`)
- History rewriting (`git filter-branch`)
- Reflog destruction (`git reflog expire/delete`)
- Find with delete action
- Secure file destruction (`shred`)
- Remote script execution (curl/wget pipe to interpreter)
- Fork bomb detection
- Command substitution with deletion (`$(rm ...)`, `` `rm ...` ``)
- Eval with deletion
- Interpreter-mediated deletions (Python, Node, Perl, Ruby)

**Default ask patterns** (17 patterns):
- Recursive/force deletion (`rm -rf`)
- Windows delete / PowerShell Remove-Item
- Git destructive ops: reset --hard, clean, checkout --, stash drop
- Force push with lease (safer but still destructive)
- Branch deletion
- File truncation
- Moving protected files (.env, .git, .claude, CLAUDE.md)
- Moving outside project (`../`, `/tmp/`)
- SQL destructive ops: DROP, TRUNCATE, DELETE without WHERE
- find -exec delete, xargs delete

### 3.3 `zeroAccessPaths` (required)

Glob patterns for files with NO access (no read, write, or delete). Default includes:
- Environment files: `.env`, `.env.*`, `.env*.local`, `*.env`
- Cryptographic keys: `*.pem`, `*.key`, `*.pfx`, `*.p12`
- SSH keys: `id_rsa`, `id_rsa.*`, `id_ed25519`, `id_ed25519.*`
- Sensitive directories: `~/.ssh/**`, `~/.gnupg/**`, `~/.aws/**`, `~/.config/gcloud/**`, `~/.azure/**`, `~/.kube/**`
- Credential files: `*credentials*.json`, `*serviceAccount*.json`, `firebase-adminsdk*.json`
- Infrastructure state: `*.tfstate`, `*.tfstate.backup`, `.terraform/**`
- Secret files: `secrets.yaml`, `secrets.yml`, `secrets.json`

### 3.4 `readOnlyPaths`

Glob patterns for read-only files (read allowed, write/delete blocked). Default includes:
- Lock files: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`, `Pipfile.lock`, `Cargo.lock`, `Gemfile.lock`, `composer.lock`, `go.sum`, `*.lock`
- Generated/dependency dirs: `node_modules/**`, `dist/**`, `build/**`, `__pycache__/**`, `.venv/**`, `venv/**`, `target/**`, `vendor/**`

### 3.5 `noDeletePaths`

Glob patterns for files protected from deletion (read/write OK). Default includes:
- Git files: `.gitignore`, `.gitattributes`, `.gitmodules`
- Project docs: `CLAUDE.md`, `LICENSE`, `LICENSE.*`, `README.md`, `README.*`, `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`
- CI/CD: `.github/**`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/**`, `azure-pipelines.yml`
- Docker: `Dockerfile`, `Dockerfile.*`, `docker-compose*.yml`, `docker-compose*.yaml`, `.dockerignore`
- Build config: `Makefile`, `pyproject.toml`, `package.json`, `tsconfig.json`, `Cargo.toml`, `go.mod`

### 3.6 `allowedExternalReadPaths`

Glob patterns for paths outside the project allowed for read-only access.
- Default: `[]` (empty)
- Supports `~` expansion and `**` recursive matching
- Only bypasses the "outside project" check
- zeroAccess, readOnly, and symlink checks still apply
- Write/Edit tools are blocked on these paths

### 3.7 `allowedExternalWritePaths`

Glob patterns for paths outside the project allowed for read+write access.
- Default: `[]` (empty)
- Same expansion and matching support
- Grants both read and write access
- zeroAccess, readOnly, and symlink checks still apply

### 3.8 `gitIntegration`

#### `autoCommit`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable auto-commit on session stop |
| `onStop` | boolean | `true` | Commit when session stops |
| `messagePrefix` | string | `"auto-checkpoint"` | Prefix for auto-commit messages |
| `includeUntracked` | boolean | `false` | Include untracked files in auto-commits |

#### `preCommitOnDangerous`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable pre-danger checkpoint commits |
| `messagePrefix` | string | `"pre-danger-checkpoint"` | Prefix for pre-danger commit messages |

#### `identity`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `email` | string | `"guardian@claude-code.local"` | Git author email |
| `name` | string | `"Guardian Auto-Commit"` | Git author name |

### 3.9 `bashPathScan`

| Option | Type | Default | Values | Description |
|--------|------|---------|--------|-------------|
| `enabled` | boolean | `true` | | Enable/disable Layer 1 raw string scan |
| `scanTiers` | array | `["zeroAccess"]` | `"zeroAccess"`, `"readOnly"`, `"noDelete"` | Which protection tiers to scan for |
| `exactMatchAction` | string | `"ask"` | `"deny"`, `"ask"` | Action for exact filename matches |
| `patternMatchAction` | string | `"ask"` | `"deny"`, `"ask"` | Action for glob-derived pattern matches |

### 3.10 `version`

Semantic version string (required). Current: `"1.0.0"`. Pattern: `^\d+\.\d+\.\d+$`

---

## 4. Security Mechanisms

### 4.1 Multi-Layer Defense (Bash)

| Check | Layer | Fail Mode | Short-Circuits |
|-------|-------|-----------|----------------|
| Oversized command (>100KB) | 0 | Closed (deny) | Yes |
| Block patterns (regex) | 0 | Closed (deny) | Yes |
| Ask patterns (regex) | 0b | N/A (accumulates) | No |
| Protected path scan (raw string) | 1 | N/A (accumulates) | No |
| Symlink escape | 3/4 | Closed (deny) | No |
| Zero access path | 3/4 | Closed (deny) | No |
| Read-only path (writes) | 3/4 | Closed (deny) | No |
| External read-only (writes/deletes) | 3/4 | Closed (deny) | No |
| No-delete path (deletes) | 3/4 | Closed (deny) | No |
| Write/delete with no resolved paths | 3/4 | Closed (ask) | No |

### 4.2 Path Guardian Checks (Edit/Read/Write)

| Check | Order | Edit | Read | Write |
|-------|-------|------|------|-------|
| Malformed JSON input | 1 | Deny | Deny | Deny |
| Null bytes in path | 2 | Deny | Deny | Deny |
| Path resolution failure | 3 | Deny | Deny | Deny |
| Symlink escape | 4 | Deny | Deny | Deny |
| Outside project (no external allow) | 5 | Deny | Deny | Deny |
| External read-only path | 5 | Deny | Allow | Deny |
| Self-guardian path | 6 | Deny | Deny | Deny |
| Zero access path | 7 | Deny | Deny | Deny |
| Read-only path | 8 | Deny | Skip | Deny |
| No-delete path (existing file) | 9 | Skip | Skip | Deny |

### 4.3 ReDoS Prevention
- Uses `regex` module with 0.5s timeout (if installed)
- Falls back to standard `re` without timeout (logs warning)
- Returns None on timeout (fail-closed)

### 4.4 Circuit Breaker
- Prevents repeated failures from cascading
- File-based flag at `.claude/guardian/.circuit_open`
- Auto-expires after 1 hour
- Opened on: git failures, hook crashes, auto-commit failures
- Cleared on: successful auto-commit
- Race-condition safe (handles FileNotFoundError between operations)

### 4.5 Self-Guardian Protection
- Guardian config file (`.claude/guardian/config.json`) is always protected from Edit/Write
- Dynamic: also protects whichever config file was actually loaded (plugin default or user custom)
- Cannot be disabled via configuration

### 4.6 Archive-Before-Delete
- Untracked files are archived to `_archive/` before deletion
- Git-tracked files are not archived (recoverable from git history)
- Archive creates `_deletion_log.json` with metadata
- Size limits prevent DoS: 100MB/file, 500MB total, 50 files max
- Symlinks preserved as symlinks (not dereferenced)
- User prompted after archive (ask) or warned if archive fails

### 4.7 Pre-Commit on Dangerous Operations
- Creates a checkpoint commit before "ask"-level operations
- Protects against data loss from dangerous commands user approves
- Skips during rebase/merge (would corrupt state)
- Uses `--no-verify` to avoid interference from pre-commit hooks

---

## 5. Permission Decision Paths

### 5.1 Bash Tool Decision Tree

```
Input: Bash command via stdin JSON
  |
  +-- Invalid JSON -> DENY
  +-- Not Bash tool -> EXIT (silent)
  +-- No project dir -> DENY
  |
  +-- Layer 0: Block patterns
  |     +-- Oversized command (>100KB) -> DENY (short-circuit)
  |     +-- Matches block pattern -> DENY (short-circuit)
  |
  +-- Layer 0b: Ask patterns -> accumulate verdict
  +-- Layer 1: Protected path scan -> accumulate verdict
  +-- Layer 2+3+4: Per sub-command analysis
  |     +-- For each extracted path:
  |           +-- Symlink escape -> DENY
  |           +-- Zero access -> DENY
  |           +-- Read-only + write operation -> DENY
  |           +-- External read-only + write/delete -> DENY
  |           +-- No-delete + delete operation -> DENY
  |     +-- Write/delete with no resolved paths -> ASK
  |
  +-- Final verdict: deny > ask > allow
  |
  +-- If DENY -> emit deny response
  +-- If delete operation:
  |     +-- Archive untracked files
  |     +-- If archived -> ASK "Proceed with deletion?"
  |     +-- If archive failed -> ASK with warning "Data PERMANENTLY LOST"
  |     +-- If existing paths -> ASK "Delete N file(s)?"
  +-- If ASK:
  |     +-- Pre-commit (if configured)
  |     +-- emit ask response
  +-- If ALLOW -> silent exit (or log if non-trivial command)
```

### 5.2 Path Tool (Edit/Read/Write) Decision Tree

```
Input: file_path via stdin JSON
  |
  +-- Invalid JSON -> DENY
  +-- Wrong tool_name -> EXIT (silent)
  +-- No file_path -> ALLOW (explicit)
  +-- Non-string file_path -> DENY
  +-- Null byte in path -> DENY
  +-- Cannot resolve path -> DENY
  |
  +-- Symlink escape -> DENY
  +-- Outside project:
  |     +-- In allowedExternalWritePaths -> continue checks
  |     +-- In allowedExternalReadPaths:
  |           +-- Read tool -> continue checks
  |           +-- Edit/Write tool -> DENY
  |     +-- Not in any external list -> DENY
  +-- Self-guardian path -> DENY
  +-- Zero access path -> DENY
  +-- Read-only path (Edit/Write only) -> DENY
  +-- No-delete path (Write only, existing file) -> DENY
  +-- ALLOW
```

### 5.3 Auto-Commit Decision Tree

```
Stop event triggered
  |
  +-- Import failure -> EXIT (fail-open)
  +-- Circuit breaker open -> SKIP
  +-- gitIntegration missing -> SKIP
  +-- autoCommit.enabled=false -> SKIP
  +-- autoCommit.onStop=false -> SKIP
  +-- Detached HEAD -> SKIP
  +-- Rebase/merge in progress -> SKIP
  +-- No uncommitted changes -> SKIP
  +-- Dry-run mode -> LOG & SKIP
  |
  +-- Stage changes (includeUntracked determines git add -A vs -u)
  |     +-- Stage failure -> LOG WARNING, continue (best-effort)
  |
  +-- No staged changes -> SKIP (normal)
  +-- Commit (--no-verify)
  |     +-- Success -> LOG, clear circuit breaker
  |     +-- Failure -> LOG, open circuit breaker
  |
  +-- Exception -> LOG, open circuit breaker, EXIT (fail-open)
```

---

## 6. Environment Variables

| Variable | Purpose | Used By |
|----------|---------|---------|
| `CLAUDE_PROJECT_DIR` | Project directory root | All hooks (required for security checks) |
| `CLAUDE_PLUGIN_ROOT` | Plugin installation directory | Config loading (Step 2 resolution) |
| `CLAUDE_HOOK_DRY_RUN` | Enable dry-run mode (`1`, `true`, `yes`) | All hooks |

---

## 7. Inter-File Dependencies

```
bash_guardian.py
  +-- imports from _guardian_utils.py:
  |     COMMIT_MESSAGE_MAX_LENGTH, ask_response, deny_response,
  |     get_hook_behavior, get_project_dir, git_add_tracked,
  |     git_commit, git_has_changes, git_has_staged_changes,
  |     git_is_tracked, is_dry_run, is_rebase_or_merge_in_progress,
  |     is_symlink_escape, load_guardian_config, log_guardian,
  |     make_hook_behavior_response, match_allowed_external_path,
  |     match_ask_patterns, match_block_patterns, match_no_delete,
  |     match_read_only, match_zero_access, set_circuit_open,
  |     truncate_command, validate_commit_prefix
  +-- stdlib: glob, json, os, re, secrets, shlex, shutil, sys,
  |          datetime, pathlib

edit_guardian.py
  +-- imports from _guardian_utils.py:
  |     get_hook_behavior, log_guardian, make_hook_behavior_response,
  |     run_path_guardian_hook, set_circuit_open

read_guardian.py
  +-- imports from _guardian_utils.py:
  |     (same as edit_guardian.py)

write_guardian.py
  +-- imports from _guardian_utils.py:
  |     (same as edit_guardian.py)

auto_commit.py
  +-- imports from _guardian_utils.py:
  |     COMMIT_MESSAGE_MAX_LENGTH, clear_circuit, git_add_all,
  |     git_add_tracked, git_commit, git_get_last_commit_hash,
  |     git_has_changes, git_has_staged_changes, is_circuit_open,
  |     is_detached_head, is_dry_run, is_rebase_or_merge_in_progress,
  |     load_guardian_config, log_guardian, set_circuit_open,
  |     validate_commit_prefix

_guardian_utils.py
  +-- stdlib only: fnmatch, json, os, re, shutil, subprocess,
  |               sys, time, datetime, pathlib, typing
  +-- optional: regex (for ReDoS timeout defense)
```

---

## 8. Edge Cases and Special Behaviors

### 8.1 Command Parsing Edge Cases
- **Backslash-escaped delimiters**: `\;` is NOT treated as a command separator (C-2 fix)
- **Backtick substitution**: Content inside backticks is not split (C-2 fix)
- **Single `&` as separator**: Treated as background operator / separator, but NOT when part of `&>`, `>&`, `<&`, or `n>&` redirections
- **ANSI-C quoting**: `$'...'` is NOT specially handled (known limitation)
- **shlex failure**: Falls back to simple `str.split()` on ValueError

### 8.2 Path Extraction Edge Cases
- **Flag-concatenated paths**: `-f.env` extracts `.env` suffix (P1-6 fix)
- **dd of= syntax**: `of=/path` is extracted (M-3 fix)
- **Environment variable expansion**: `$HOME/path` is expanded via `os.path.expandvars`
- **Tilde expansion**: `~/path` is expanded via `expanduser()`
- **Glob expansion**: `*.txt`, `file[v]` are expanded against filesystem
- **Windows compatibility**: `shlex.split(posix=False)` on Windows, strips quotes from parts

### 8.3 Pattern Matching Edge Cases
- **Filename-only matching**: Simple patterns (no `/` or `**`) match against just the filename portion
- **Case sensitivity**: Linux is case-sensitive; Windows/macOS are case-insensitive
- **Cross-platform paths**: Always normalized to forward slashes for matching

### 8.4 Git Edge Cases
- **Lock file retry**: Git operations retry up to 3 times on lock file errors with exponential backoff
- **Timeout retry**: Git add/commit retry on timeout (system under load)
- **Empty repository**: Detected via "does not have any commits" / "no commits yet" stderr
- **Nothing to commit**: Treated as success, not error (BUG-1/BUG-2 fixes)
- **Detached HEAD**: Auto-commit skipped (orphaned commits prevention)
- **Rebase/merge/cherry-pick/bisect**: Auto-commit and pre-commit skipped (state corruption prevention)
- **Locale safety**: `LC_ALL=C` forced for all git operations

### 8.5 Windows Compatibility
- Path normalization uses platform-appropriate functions
- Case-insensitive matching on Windows and macOS
- `shlex.split(posix=False)` on Windows
- Thread-based timeout instead of SIGALRM
- Explicit file removal before rename (log rotation)
- Recovery guidance uses `del` vs `rm` based on platform

### 8.6 Dry-Run Mode
- All hooks support dry-run via `CLAUDE_HOOK_DRY_RUN=1|true|yes`
- Logs what WOULD happen but does not block or modify
- No responses emitted (all operations pass through)
- Useful for testing configuration changes

### 8.7 Config Error Handling
- JSON parse error: falls through to next config source
- File read error: falls through to next config source
- Validation errors: logged as warnings but don't prevent config use (backwards compatibility)
- Missing config: uses hardcoded fallback with reduced protection
- Deprecated `allowedExternalPaths` key: logged as validation error with migration guidance

### 8.8 Commit Message Handling
- Control characters stripped (except newline/tab)
- All printable UTF-8 preserved (Korean, Japanese, emojis)
- Empty messages become `"[auto-commit]"`
- Max 72 characters (Git convention)
- Prefix max 30 characters
- Pre-commit messages format: `{prefix}: {cmd_short}... @ {timestamp}`
- Auto-commit messages format: `{prefix}: {timestamp}`
