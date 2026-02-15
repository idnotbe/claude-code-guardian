# Implementation Analysis Report
## Date: 2026-02-14
## Analyzer: Teammate A (Implementation Analyzer)

---

### 1. Project Structure

```
claude-code-guardian/
  .claude-plugin/
    plugin.json              # Plugin manifest (name, version, hooks, commands, skills, agents)
    marketplace.json         # Marketplace metadata for distribution
  assets/
    guardian.default.json    # Default configuration template (v1.0.0)
    guardian.schema.json     # JSON Schema for config validation (draft-07)
  hooks/
    hooks.json               # Hook registrations (PreToolUse: Bash/Read/Edit/Write, Stop)
    scripts/
      bash_guardian.py       # Bash command interception (the core engine)
      read_guardian.py       # Read tool path guarding (thin wrapper)
      edit_guardian.py       # Edit tool path guarding (thin wrapper)
      write_guardian.py      # Write tool path guarding (thin wrapper)
      auto_commit.py         # Auto-commit on session stop
      _guardian_utils.py     # Shared utilities (config, matching, git, logging)
  commands/
    init.md                  # /guardian:init setup wizard prompt
  skills/
    config-guide/
      SKILL.md               # Config guide skill definition
      references/
        schema-reference.md  # Complete schema documentation
  agents/
    config-assistant.md      # Guardian config assistant agent definition
  README.md
  CHANGELOG.md
  KNOWN-ISSUES.md
  LICENSE                    # MIT (copyright: agntpod)
  .gitignore
```

**Key Observations:**
- There is NO `CLAUDE.md` file in the repository.
- There is NO `package.json` -- this is a pure Python plugin, not a Node.js project.
- The `.claude/guardian/guardian.log` file exists at runtime but is gitignored.
- Test files exist in `tests/` but are not part of the plugin distribution.
- The `__pycache__` directories are present (not gitignored from plugin root).

---

### 2. Core Components

The plugin registers **5 hooks** via `hooks/hooks.json`:

| Hook Script | Event | Matcher | Purpose |
|---|---|---|---|
| `bash_guardian.py` | PreToolUse | Bash | Block/ask dangerous bash commands |
| `read_guardian.py` | PreToolUse | Read | Block reading protected files |
| `edit_guardian.py` | PreToolUse | Edit | Block editing protected files |
| `write_guardian.py` | PreToolUse | Write | Block writing to protected files |
| `auto_commit.py` | Stop | (none) | Auto-commit on session end |

All hooks are invoked via `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/<script>.py"`.

**Communication Protocol:** All PreToolUse hooks communicate via JSON on stdout:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny" | "ask" | "allow",
    "permissionDecisionReason": "..."
  }
}
```

No stdout output = allow (Claude Code treats silence as permission).

**Fail-Close vs Fail-Open Design:**
- All security hooks (Bash, Read, Edit, Write) are **fail-closed**: ImportError or unhandled exception -> deny.
- Auto-commit hook is **fail-open**: ImportError prints warning to stderr and exits 0 (never blocks session termination).

---

### 3. bash_guardian.py - Detailed Analysis

**Location:** `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py`
**Lines:** 1232
**Phase:** 3 (Bash Bypass Protection)

#### Execution Flow (main function, lines 919-1211)

1. Get project directory from `CLAUDE_PROJECT_DIR` environment variable
2. Parse JSON from stdin (fail-close on malformed JSON)
3. Exit silently if tool_name is not "Bash"
4. Extract `command` from `tool_input.command`
5. Load config (cached per-process)

**Layer 0: Block Patterns (lines 958-966)**
- Short-circuits immediately on match -> deny
- Calls `match_block_patterns()` from utils

**Layer 0b: Ask Patterns (lines 972-975)**
- Calls `match_ask_patterns()` from utils
- Does NOT short-circuit; adds to verdict aggregation

**Layer 1: Protected Path Scan (lines 977-981)**
- Calls `scan_protected_paths()` (defined in bash_guardian.py, lines 303-374)
- Scans raw command string for literal occurrences of zeroAccessPaths filenames
- Uses word-boundary regex with special chars: `[\s;|&<>()"\`'=/,{\[:\]]`
- Configurable via `bashPathScan` config section
- Actions configurable: `exactMatchAction` and `patternMatchAction` (default: "ask")
- `glob_to_literals()` (lines 250-300) converts glob patterns to literal strings:
  - Exact patterns -> literal string
  - `name.*` -> `name.` (prefix)
  - `*.ext` -> `.ext` (suffix, only if >= 4 chars and not generic like "env", "key", "log")
  - Generic patterns like `*.env`, `*credentials*` -> `[]` (skipped to avoid false positives)

**Layer 2: Command Decomposition (lines 984-986)**
- `split_commands()` (lines 79-242) splits compound commands on: `;`, `&&`, `||`, `|`, `&`, `\n`
- Respects: single quotes, double quotes, `$()`, `<()`, `>()`, backticks, backslash escapes
- Does NOT handle ANSI-C quoting `$'...'`
- Single `&` is treated as separator UNLESS part of redirection (`&>`, `>&`, `<&`, `n>&`)

**Layer 3: Path Extraction (lines 987-998)**
- `extract_paths()` (lines 457-541):
  - Uses `shlex.split()` with `posix=False` on Windows
  - Strips quotes on Windows after split (COMPAT-03 fix)
  - Skips flags (args starting with `-`), but checks flag-concatenated paths like `-f.env` (P1-6)
  - Handles `dd of=` syntax (M-3)
  - Expands environment variables via `os.path.expandvars()` (P1-5)
  - Expands `~` via `path.expanduser()`
  - Expands wildcards via `glob.glob()`
  - `_is_path_candidate()` rejects: empty, newlines, null bytes, >4096 chars, components >255 chars
  - `allow_nonexistent=True` for write/delete commands (target may not exist yet)
- `extract_redirection_targets()` (lines 410-454):
  - Regex: `(?:(?:\d|&)?(?:>\|?|>{2})|<(?!<))\s*([^\s;|&<>]+)`
  - Quote-aware via `_is_inside_quotes()` (I-5 fix)
  - Skips process substitutions `>(cmd)` and `<(cmd)` (F6)
  - Skips variable targets `$FILE`

**Layer 4: Command Type Detection (lines 572-658)**
- `is_delete_command()` detects: `rm`, `del`, `rmdir`, `Remove-Item`, `ri`, `git rm` (with optional global flags), `mv ... /dev/null`, standalone redirect truncation `> file`, interpreter deletions (Python/Node/Perl/Ruby)
- `is_write_command()` detects: `>` redirection, `tee`, `mv`, `ln` (with negative lookbehind for `ls -ln`), `sed -i`, `cp`, `dd`, `patch`, `rsync`, `: >`, `chmod`, `touch`, `chown`, `chgrp`
- Does NOT include `install` in write patterns (I-2 fix to avoid blocking npm/pip/cargo/brew)

**F1: Fail-Closed Safety Net (lines 1000-1007)**
- If write/delete detected but no paths resolved -> escalate to "ask" instead of silently allowing

**Path Access Checks (lines 1009-1042)**
For each extracted path:
1. Symlink escape check -> deny
2. Zero access check (ALL operations) -> deny
3. Read-only check (write commands only) -> deny
4. No-delete check (delete commands only) -> deny

**CRITICAL BEHAVIORAL NOTE:** The `noDeletePaths` check in bash_guardian is applied per-sub-command. If a sub-command is classified as `is_delete`, its paths are checked against `noDeletePaths`. If a sub-command is classified as `is_write` but NOT `is_delete`, noDeletePaths is NOT checked. This is the only place noDeletePaths enforcement occurs for bash commands.

**Verdict Aggregation (lines 886-911, 1044-1053)**
- Priority: deny (2) > ask (1) > allow (0)
- Unknown verdicts default to deny priority (fail-close)
- ALL layers complete before any decision is emitted (C-1 fix)

**Deletion Handling with Archive (lines 1055-1132)**
- Only triggers if any sub-command is a delete command
- Checks if paths exist and are git-tracked
- Untracked files are archived before deletion is permitted
- Archive goes to `_archive/<timestamp>_<title>/` within project
- Archive constraints: max 100MB/file, 500MB total, 50 files
- Symlinks are preserved (F5 fix)
- On archive success: asks user to confirm deletion
- On archive failure: asks user with WARNING about permanent data loss
- Tracked-only files: asks user to confirm without archive

**Pre-Commit on Dangerous (lines 1134-1204)**
- Only triggers when final verdict is "ask"
- Checks `gitIntegration.preCommitOnDangerous.enabled`
- Skips if rebase/merge in progress
- Skips if no changes to commit
- Uses `git add -u` (tracked only) -> checks staged changes -> commits with `--no-verify`
- Commit message format: `<prefix>: <cmd_short>... @ <timestamp>` (max 72 chars)
- On failure: sets circuit breaker open

**Top-Level Exception Handler (lines 1214-1231)**
- Catches all unhandled exceptions
- Sets circuit breaker open
- Emits deny response (F-01 fix: fail-CLOSE)

#### Archive Functions (lines 686-848)
- `generate_archive_title()`: sanitizes first filename, adds "and_N_more" suffix
- `archive_files()`: copies files to `_archive/` with size limits, deduplication, symlink preservation
- `create_deletion_log()`: writes `_deletion_log.json` metadata in archive directory

---

### 4. _guardian_utils.py - Detailed Analysis

**Location:** `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`
**Lines:** 2308

#### Constants (lines 75-103)
| Constant | Value | Purpose |
|---|---|---|
| `DRY_RUN_ENV` | `"CLAUDE_HOOK_DRY_RUN"` | Env var for dry-run mode |
| `MAX_COMMAND_LENGTH` | 100,000 | Command size limit before block (F-02 padding attack prevention) |
| `MAX_PATH_PREVIEW_LENGTH` | 60 | Path truncation for logs |
| `MAX_COMMAND_PREVIEW_LENGTH` | 80 | Command truncation for logs |
| `MAX_LOG_SIZE_BYTES` | 1,000,000 (1MB) | Log rotation threshold |
| `REGEX_TIMEOUT_SECONDS` | 0.5 | ReDoS defense timeout |
| `COMMIT_MESSAGE_MAX_LENGTH` | 72 | Git convention |
| `COMMIT_PREFIX_MAX_LENGTH` | 30 | Max prefix length |
| `HOOK_DEFAULT_TIMEOUT_SECONDS` | 10 | Default hook timeout |

#### ReDoS Defense (lines 56-69, 722-787)
- Optional `regex` package for timeout support
- `safe_regex_search()` uses `regex` module with timeout if available
- Falls back to standard `re` with warning (no timeout defense)
- On timeout: returns `None` (fail-closed: treat as no match for security)

#### Hook Timeout (lines 106-169)
- `with_timeout()`: platform-specific timeout execution
  - Windows: threading-based (non-killable, accepted limitation)
  - Unix: signal-based (SIGALRM)
- `HookTimeoutError` exception class
- **NOTE:** `with_timeout()` is defined but NOT called anywhere in the codebase. The hook scripts do not wrap their main() in with_timeout(). This appears to be infrastructure for future use or relies on an external caller.

#### Circuit Breaker (lines 222-351)
- File-based: `.claude/guardian/.circuit_open`
- Auto-expires after 1 hour (`CIRCUIT_TIMEOUT_SECONDS = 3600`)
- Format: `<ISO-timestamp>|<reason>`
- Race-condition handling (M2 fix): handles file disappearing between exists()/stat()/open()
- Permission errors: fail-closed (treats as circuit open)
- `set_circuit_open()`: creates file with reason
- `is_circuit_open()`: checks existence, expiry, returns (bool, reason)
- `clear_circuit()`: deletes file

#### Config Loading (lines 415-598)
**Resolution Chain (3-step):**
1. `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` (user custom)
2. `$CLAUDE_PLUGIN_ROOT/assets/guardian.default.json` (plugin default)
3. Hardcoded `_FALLBACK_CONFIG` (emergency fallback)

- Cached per-process (`_config_cache`)
- Tracks which config was loaded (`_active_config_path`)
- `_using_fallback_config` flag for status checking
- Never raises exceptions -- returns safe default on any error

**FALLBACK CONFIG (lines 366-413) vs DEFAULT CONFIG differences:**
| Aspect | Fallback | Default |
|---|---|---|
| Block patterns | 8 | 19 |
| Ask patterns | 2 | 17 |
| zeroAccessPaths | 9 entries | 26 entries |
| readOnlyPaths | 5 entries | 17 entries |
| noDeletePaths | 4 entries (.git, .claude, _archive, CLAUDE.md) | 29 entries |
| allowedExternalPaths | empty | empty |
| gitIntegration | NOT present | Full (autoCommit, preCommitOnDangerous, identity) |
| bashPathScan | NOT present | Full (enabled, scanTiers, actions) |
| Reasons prefixed with | `[FALLBACK]` | (no prefix) |

**IMPORTANT:** The fallback config protects `.claude/guardian/config.json` in readOnlyPaths (not the hook scripts). This is the PLUGIN MIGRATION change -- scripts live in read-only plugin cache dir.

#### Config Validation (lines 616-698)
- `validate_guardian_config()`: validates structure, hookBehavior values, regex syntax, path pattern types, gitIntegration structure
- Returns list of error strings (empty = valid)
- **NOTE:** This function is defined but NOT called anywhere in the main hook scripts. It exists for external use (e.g., by the init wizard or skill).

#### Dry-Run Mode (lines 700-719)
- Env var: `CLAUDE_HOOK_DRY_RUN` set to "1", "true", or "yes"
- In dry-run: hooks log what they WOULD do but don't block or modify

#### Pattern Matching (lines 789-865)
- `match_block_patterns()`: checks command against `bashToolPatterns.block` array
  - F-02 fix: Commands exceeding `MAX_COMMAND_LENGTH` (100K) are unconditionally blocked
  - Uses `safe_regex_search()` with `re.IGNORECASE | re.DOTALL`
- `match_ask_patterns()`: checks command against `bashToolPatterns.ask` array
  - Same F-02 fix for oversized commands
  - Uses `safe_regex_search()` with `re.IGNORECASE | re.DOTALL`

#### Path Matching (lines 867-1192)
- `normalize_path()`: expanduser -> abspath -> normpath -> lowercase on Windows
- `expand_path()`: expanduser -> resolve relative to project dir -> resolve()
- `is_symlink_escape()`: checks if symlink resolves outside project (fail-open on error)
- `is_path_within_project()`: checks if resolved path is under project dir (fail-open: returns True if no project dir or on error)
- `match_path_pattern()`: multi-strategy glob matching:
  1. Direct fnmatch against normalized path
  2. Filename-only match for simple patterns (no `/` or `**`)
  3. Relative-to-project match with recursive glob support (`_match_recursive_glob()`)
- `match_zero_access()`, `match_read_only()`, `match_no_delete()`, `match_allowed_external_path()`: check path against respective config arrays

#### Self-Guardian (lines 354-363, 2094-2139)
- `SELF_GUARDIAN_PATHS`: tuple containing only `".claude/guardian/config.json"`
- **PLUGIN MIGRATION:** Reduced from 6 script paths to config-only (scripts are in read-only plugin cache)
- `is_self_guardian_path()`: checks both static paths AND dynamically-loaded config path

#### Logging (lines 1194-1302)
- Log file: `$CLAUDE_PROJECT_DIR/.claude/guardian/guardian.log`
- Format: `TIMESTAMP [LEVEL] [DRY-RUN] MESSAGE`
- Auto-rotation at 1MB, keeps one backup (.log.1)
- Silent fail on all errors
- Log levels: INFO, WARN, ERROR, BLOCK, ASK, ALLOW, DRY-RUN, SCAN, DENY, ARCHIVE, DEBUG

#### Response Helpers (lines 1305-1359)
- `deny_response()`: prefix `[BLOCKED]` (text prefix, not emoji, for Windows cp949 compatibility)
- `ask_response()`: prefix `[CONFIRM]`
- `allow_response()`: no prefix

#### Rule Evaluation Orchestration (lines 1362-1402)
- `evaluate_rules()`: block -> ask -> allow precedence
- **NOTE:** This function wraps match_block_patterns + match_ask_patterns but does NOT include path checks. It is NOT called by bash_guardian.py (which implements its own more comprehensive multi-layer flow).

#### Git Integration (lines 1405-2051)
- `git_is_tracked()`: uses `git ls-files --error-unmatch`
- `_get_git_env()`: sets `LC_ALL=C` for consistent English output
- `_is_git_lock_error()`: checks for `.git/index.lock` indicators
- `sanitize_commit_message()`: removes control chars (preserves UTF-8), enforces 72-char limit
- `git_has_changes()`: `git status --porcelain`, checks returncode (CRITICAL-1 fix)
- `git_has_staged_changes()`: `git diff --cached --quiet` (exit 1 = has changes)
- `git_add_all()`: `git add -A` with 3 retries on lock/timeout
- `git_add_tracked()`: `git add -u` with 3 retries on lock/timeout
- `ensure_git_config()`: checks/sets user.email and user.name from config identity section with verification
- `git_commit()`: commit with sanitized message, 3 retries, optional `--no-verify`, handles "nothing to commit" as success
- `git_get_last_commit_hash()`: `git rev-parse --short HEAD`, handles empty repos
- `is_detached_head()`: `git symbolic-ref -q HEAD`
- `is_rebase_or_merge_in_progress()`: checks for `.git/rebase-merge`, `.git/rebase-apply`, `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `BISECT_LOG`
- `is_git_available()`: cached `shutil.which("git")` check

#### Path Guardian Hook Runner (lines 2053-2293)
`run_path_guardian_hook(tool_name)` -- shared logic for Read/Edit/Write hooks:
1. Parse JSON from stdin (fail-close on malformed JSON)
2. Match tool_name case-insensitively
3. Validate tool_input is dict
4. Extract and validate file_path (null byte check)
5. Resolve to absolute path
6. Check order:
   a. Symlink escape -> deny
   b. Path within project -> deny (unless in allowedExternalPaths)
   c. Self-guardian path -> deny
   d. Zero access -> deny (with message: "Bash alternatives are also monitored")
   e. Read-only -> deny (SKIPPED for Read tool -- reading read-only files IS allowed)
7. If all checks pass -> allow (exits silently; actually prints allow_response then exits)

**CRITICAL BEHAVIORAL NOTES:**
- `noDeletePaths` is NOT enforced by run_path_guardian_hook(). This means Edit and Write tools can modify files listed in noDeletePaths. Only bash `rm`-style commands are blocked from deleting noDeletePaths files.
- The Read guardian does NOT check readOnlyPaths (by design -- line 2278 condition `tool_name.lower() != "read"`).
- The Read guardian DOES check zeroAccessPaths, self-guardian paths, symlink escapes, and outside-project paths.

---

### 5. Configuration (guardian.default.json)

**Version:** 1.0.0
**Location:** `/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json`

#### hookBehavior
```json
{
  "onTimeout": "deny",
  "onError": "deny",
  "timeoutSeconds": 10
}
```

#### bashToolPatterns.block (19 patterns)
| Category | Patterns |
|---|---|
| Root deletion | `rm -rf /` or `rm -rf /*` |
| Protected dir deletion | `.git`, `.claude`, `_archive` via rm/rmdir/del/remove-item |
| Force push | `git push --force` (NOT `--force-with-lease`) |
| History rewriting | `git filter-branch`, `git reflog expire/delete` |
| Find with delete | `find ... -delete` |
| Secure destruction | `shred` |
| Remote code exec | `curl/wget | bash/sh/python/perl/ruby/node` |
| Fork bomb | `: (){ ... }; :` pattern |
| Substitution with deletion | `$(rm ...)` and backtick equivalents |
| Eval with deletion | `eval "rm ..."` |
| Interpreter file deletion | Python (os.remove, shutil.rmtree, pathlib.Path.unlink), Node (unlinkSync, rmSync, fs.unlink), Perl/Ruby (unlink, File.delete) |

#### bashToolPatterns.ask (17 patterns)
| Category | Patterns |
|---|---|
| Recursive/force deletion | `rm -rf` (non-root) |
| Windows delete | `del /s /q` |
| PowerShell removal | `Remove-Item` |
| Git destructive | `reset --hard`, `clean -f`, `checkout -- .`, `stash drop`, `branch -d/-D` |
| Force push with lease | `git push --force-with-lease` |
| File truncation | `truncate` |
| Moving protected files | `mv .env`, `mv .git`, `mv .claude`, `mv CLAUDE.md` |
| Moving outside project | `mv ... ../` or `mv ... /tmp/` |
| SQL destructive | `DROP TABLE/DATABASE`, `TRUNCATE TABLE`, `DELETE FROM ... ;` (without WHERE) |
| Find/xargs with delete | `find -exec rm`, `xargs rm` |

#### zeroAccessPaths (26 entries)
Covers: `.env` (all variants including `*.env`), `*.pem`, `*.key`, `*.pfx`, `*.p12`, SSH keys (`id_rsa`, `id_ed25519` + variants), `~/.ssh/**`, `~/.gnupg/**`, `~/.aws/**`, `~/.config/gcloud/**`, `~/.azure/**`, `~/.kube/**`, `*credentials*.json`, `*serviceAccount*.json`, `firebase-adminsdk*.json`, Terraform state files, `.terraform/**`, `secrets.yaml/yml/json`

#### readOnlyPaths (17 entries)
Covers: Lock files (package-lock.json, yarn.lock, pnpm-lock.yaml, poetry.lock, Pipfile.lock, Cargo.lock, Gemfile.lock, composer.lock, go.sum, `*.lock`), build output dirs (node_modules, dist, build, __pycache__, .venv, venv, target, vendor)

#### noDeletePaths (29 entries)
Covers: Git files (.gitignore, .gitattributes, .gitmodules), docs (CLAUDE.md, LICENSE, README.md, CONTRIBUTING.md, CHANGELOG.md, SECURITY.md), CI/CD (.github/**, .gitlab-ci.yml, Jenkinsfile, .circleci/**, azure-pipelines.yml), Docker (Dockerfile, docker-compose*.yml/yaml, .dockerignore), build configs (Makefile, pyproject.toml, package.json, tsconfig.json, Cargo.toml, go.mod)

**NOTE:** The default config's `noDeletePaths` does NOT include `.git/**`, `.claude/**`, or `_archive/**`. These are only in the fallback config. The default config guards these via the block patterns (rm .git, rm .claude, rm _archive are blocked).

#### allowedExternalPaths
Empty array `[]` by default.

#### gitIntegration
```json
{
  "autoCommit": {
    "enabled": true,
    "onStop": true,
    "messagePrefix": "auto-checkpoint",
    "includeUntracked": false
  },
  "preCommitOnDangerous": {
    "enabled": true,
    "messagePrefix": "pre-danger-checkpoint"
  },
  "identity": {
    "email": "guardian@claude-code.local",
    "name": "Guardian Auto-Commit"
  }
}
```

#### bashPathScan
```json
{
  "enabled": true,
  "scanTiers": ["zeroAccess"],
  "exactMatchAction": "ask",
  "patternMatchAction": "ask"
}
```
**NOTE:** The `scanTiers` field is declared in config but the actual `scan_protected_paths()` code ONLY scans `zeroAccessPaths` regardless of what `scanTiers` says. The `scanTiers` config value is not read by the code (the code hardcodes `config.get("zeroAccessPaths", [])`). This is a config-implementation gap.

---

### 6. Schema (guardian.schema.json)

**Location:** `/home/idnotbe/projects/claude-code-guardian/assets/guardian.schema.json`
**Standard:** JSON Schema draft-07
**ID:** `guardian.schema.json`

**Required top-level fields:** `version`, `hookBehavior`, `bashToolPatterns`
**Optional top-level fields:** `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths`, `allowedExternalPaths`, `gitIntegration`, `bashPathScan`

**additionalProperties: false** at all levels -- strict schema, no extra fields allowed.

**Schema details:**
- `version`: semver pattern `^\d+\.\d+\.\d+$`
- `hookBehavior`: requires onTimeout, onError (enum: allow/deny/ask), timeoutSeconds (1-60)
- `bashToolPatterns`: block and ask arrays of `patternRule` objects (pattern + reason, both required)
- Path arrays: arrays of strings
- `allowedExternalPaths`: default `[]`
- `gitIntegration`: autoCommit (enabled, onStop, messagePrefix, includeUntracked), preCommitOnDangerous (enabled, messagePrefix), identity (email with format:email, name)
- `bashPathScan`: enabled (bool, default true), scanTiers (enum array: zeroAccess/readOnly/noDelete), exactMatchAction (deny/ask), patternMatchAction (deny/ask)
- `$schema` and `$comment` fields allowed at top level

**Gap Note:** The schema declares `bashPathScan.scanTiers` as an enum array supporting `["zeroAccess", "readOnly", "noDelete"]`, but the code only ever scans zeroAccessPaths regardless of this setting.

---

### 7. Hooks Configuration

**File:** `/home/idnotbe/projects/claude-code-guardian/hooks/hooks.json`

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/bash_guardian.py\""}] },
      { "matcher": "Read", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/read_guardian.py\""}] },
      { "matcher": "Edit", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/edit_guardian.py\""}] },
      { "matcher": "Write", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/write_guardian.py\""}] }
    ],
    "Stop": [
      { "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/auto_commit.py\""}] }
    ]
  }
}
```

**Observations:**
- Uses `python3` (not `python`) -- COMPAT-02 fix for Linux/WSL.
- Relies on `CLAUDE_PLUGIN_ROOT` environment variable expansion by Claude Code (PV-01 assumption).
- Stop hook has no matcher (fires on all stop events).
- All hooks use `type: "command"` (shell command execution).

#### Plugin Manifest (plugin.json)
```json
{
  "name": "claude-code-guardian",
  "version": "1.0.0",
  "hooks": "./hooks/hooks.json",
  "commands": ["./commands/init.md"],
  "skills": ["./skills/config-guide"],
  "agents": ["./agents/config-assistant.md"]
}
```

---

### 8. Key Features & Behaviors

#### 8.1 Multi-Layer Defense Architecture
The bash guardian implements 5 defense layers:
- **Layer 0**: Regex block patterns (catastrophic commands) -- short-circuits
- **Layer 0b**: Regex ask patterns (dangerous-but-legitimate)
- **Layer 1**: Raw string scan for protected path names
- **Layer 2**: Command decomposition (splits compound commands)
- **Layer 3**: Path extraction from arguments and redirections
- **Layer 4**: Command type detection (write vs delete)
- Layers 2-4 operate together on sub-commands

#### 8.2 Verdict Aggregation
All layers must complete before any verdict is emitted. Verdicts aggregate with deny > ask > allow precedence. Unknown verdict strings default to deny priority (fail-close).

#### 8.3 Archive-Before-Delete
For delete commands targeting untracked files, Guardian archives them to `_archive/` before allowing deletion. Archives include metadata logs. Users must confirm after archive.

#### 8.4 Pre-Danger Checkpoints
Before "ask" operations, Guardian creates a git commit of tracked changes (if configured). Uses `--no-verify` to skip pre-commit hooks. Skips if rebase/merge in progress.

#### 8.5 Auto-Commit on Session Stop
On session end, commits tracked changes (or all changes if `includeUntracked=true`). Checks: circuit breaker, config enabled, detached HEAD, rebase/merge state. Opens circuit breaker on failure.

#### 8.6 Circuit Breaker Pattern
File-based circuit breaker prevents auto-commit storms on repeated failures. Auto-expires after 1 hour. Cleared on successful commit. Opened on: auto-commit failure, pre-commit failure, unhandled exceptions in any hook.

#### 8.7 Self-Guardian Protection
The guardian config file (`.claude/guardian/config.json`) is protected from Edit/Write by self-guarding logic, even if not explicitly listed in zeroAccessPaths or readOnlyPaths.

#### 8.8 Dry-Run Mode
Setting `CLAUDE_HOOK_DRY_RUN=1` makes hooks log what they would do without actually blocking or modifying anything. Useful for testing configurations.

#### 8.9 Allowed External Paths
Paths outside the project can be whitelisted for write access via `allowedExternalPaths`. Only bypasses the "outside project" check -- zeroAccess, readOnly, symlink, and self-guardian checks still apply.

#### 8.10 Platform Compatibility
- Windows: `shlex.split(posix=False)` with quote stripping, case-insensitive path matching, threading-based timeout, `winerror=112` for disk full
- Unix: signal-based timeout, case-sensitive path matching
- All platforms: `LC_ALL=C` for git commands, `python3` in hook commands

---

### 9. Patterns & Rules Currently Implemented

#### 9.1 Block Patterns in Default Config
19 patterns covering: root deletion, .git/.claude/_archive deletion, force push (not --force-with-lease), history rewriting (filter-branch, reflog expire/delete), find -delete, shred, remote code execution (curl/wget pipe to interpreter), fork bombs, command/backtick substitution with deletion, eval with deletion, interpreter file deletions (Python/Node/Perl/Ruby).

#### 9.2 Ask Patterns in Default Config
17 patterns covering: recursive/force deletion, Windows del, PowerShell Remove-Item, git reset --hard, git clean, git checkout --, git stash drop, force-with-lease push, branch deletion, truncate, moving protected files, moving outside project, SQL DROP/TRUNCATE/DELETE-without-WHERE, find -exec rm, xargs rm.

#### 9.3 Path Protection Tiers

**Zero Access (26 patterns):** All .env variants, all key/cert formats, SSH keys and dirs, cloud credential dirs (~/.aws, ~/.gcloud, ~/.azure, ~/.kube), credential JSON files, Terraform state, secrets files.

**Read Only (17 patterns):** Lock files (all major package managers + generic *.lock), build/dependency dirs (node_modules, dist, build, __pycache__, .venv, venv, target, vendor).

**No Delete (29 patterns):** Git config files, documentation files, CI/CD configs, Docker files, build system configs (Makefile, pyproject.toml, package.json, tsconfig.json, Cargo.toml, go.mod).

#### 9.4 Fallback Protection (always active, even without config)
8 block patterns, 2 ask patterns. Critical paths always protected: .git, .claude, _archive deletions blocked. Force push blocked. Interpreter deletions blocked. Minimal zeroAccess (9 entries). Config file in readOnlyPaths.

---

### 10. Confidence Notes

#### High Confidence (verified from code)
- Hook registration structure and communication protocol
- Fail-close/fail-open behavior per hook type
- Layer execution order in bash_guardian.py
- Verdict aggregation logic
- Config resolution chain (3-step)
- Archive constraints and behavior
- Circuit breaker mechanics
- Self-guardian path protection scope (config.json only)
- All pattern lists (exact contents from code/config)
- Read guardian skips readOnly check (line 2278 conditional)
- noDeletePaths NOT enforced by Edit/Write hooks
- `with_timeout()` defined but not called in hook scripts
- `validate_guardian_config()` defined but not called by hooks
- `evaluate_rules()` defined but not called by bash_guardian.py
- `scanTiers` config field not read by code

#### Medium Confidence (inferred from code patterns)
- The `hookBehavior.onTimeout` and `hookBehavior.onError` values are read by `get_hook_behavior()` but this function is not called anywhere in the codebase. The actual timeout/error behavior is hardcoded (deny) in the exception handlers and not configurable at runtime via config. The config values appear to be declarative/documentation-only.
- The `bashPathScan.scanTiers` config appears to be forward-looking (config supports it, schema validates it, but code ignores it).

#### Gaps & Discrepancies Identified
1. **scanTiers not implemented:** Schema and config support `scanTiers: ["zeroAccess", "readOnly", "noDelete"]` but code only scans zeroAccessPaths.
2. **hookBehavior not runtime-configurable:** `onTimeout` and `onError` are in config/schema but not used by hook scripts (behavior is hardcoded as deny).
3. **with_timeout() unused:** Defined in utils but no hook script calls it.
4. **validate_guardian_config() unused by hooks:** Available for external use but hooks don't validate config on load.
5. **evaluate_rules() unused by bash_guardian:** bash_guardian has its own comprehensive flow; evaluate_rules() is a simpler wrapper available for external use.
6. **noDeletePaths not enforced by Edit/Write:** Only bash delete commands are checked against noDeletePaths. The Write tool could theoretically write an empty file (effectively deleting content) without triggering noDeletePaths.
7. **Fallback config missing noDeletePaths for default entries:** Fallback has .git, .claude, _archive, CLAUDE.md. Default has 29 entries. Large protection gap if fallback activates.
8. **Default config noDeletePaths does NOT include .git/**, .claude/**, _archive/**:** These are protected by block patterns (rm .git etc.) instead. But a non-rm deletion method (like Python shutil) aimed at .git would not be caught by noDeletePaths in the default config (though it would be caught by the block pattern for interpreter deletions).
9. **LICENSE copyright says "agntpod"** but plugin.json author says "idnotbe" -- minor discrepancy.
10. **$schema in default config uses relative path** (`"./guardian.schema.json"`) which breaks when config is copied to user project directory.
