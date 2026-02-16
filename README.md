# claude-code-guardian

Selective security guardrails for Claude Code's `--dangerously-skip-permissions` mode. Speed by default, intervention by exception.

## Why Guardian?

`--dangerously-skip-permissions` is all-or-nothing. You either approve every single operation manually, or you approve none of them. Most power users choose none -- because stopping to confirm every file write kills the workflow.

The problem: permissionless mode doesn't distinguish between writing a component file and running `rm -rf /`. Everything gets the same silent green light.

Guardian gives you back the guardrails that actually matter. It hooks into Claude Code's plugin system to intercept operations before they execute. The 99% of safe operations run silently. The 1% that could ruin your day -- destructive shell commands, secret file access, force pushes -- get caught and require your explicit approval.

You keep the speed. You lose the existential dread.

## Table of Contents

- [What It Catches](#what-it-catches)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
  - [Configuration File Location](#configuration-file-location)
  - [Configuration Reference](#configuration-reference)
  - [Glob Pattern Syntax](#glob-pattern-syntax)
  - [Writing Regex Patterns](#writing-regex-patterns)
- [How It Works](#how-it-works)
  - [Architecture](#architecture)
  - [Bash Guardian (Multi-Layer Defense)](#bash-guardian-multi-layer-defense)
  - [Path Guardian (Read/Edit/Write)](#path-guardian-readeditwrite)
  - [Auto-Commit (Stop Hook)](#auto-commit-stop-hook)
  - [Archive-Before-Delete](#archive-before-delete)
  - [Self-Guarding](#self-guarding)
  - [Circuit Breaker](#circuit-breaker)
- [Security Model](#security-model)
- [User Guide](#user-guide)
  - [Understanding Default Protection](#understanding-default-protection)
  - [Customizing Command Patterns](#customizing-command-patterns)
  - [Customizing Path Restrictions](#customizing-path-restrictions)
  - [Configuring Auto-Commit](#configuring-auto-commit)
  - [Working with Multiple Projects](#working-with-multiple-projects)
  - [Understanding Block Messages](#understanding-block-messages)
- [Troubleshooting](#troubleshooting)
- [Disabling Guardian](#disabling-guardian)
- [Upgrading](#upgrading)
- [FAQ](#faq)
- [Testing](#testing)
- [Requirements](#requirements)
- [License](#license)

## What It Catches

**Safety checkpoints** (automatic):
- Auto-commits pending changes when a Claude Code session ends
- Creates a commit before any destructive operation, so you can always roll back
- Archives untracked files to `_archive/` before deletion (100MB/file limit, 500MB total, 50 files max)
- Your work is never more than one `git reset` away from recovery

**Hard blocks** (always denied, no override):
- `rm -rf /`, fork bombs, and other catastrophic shell commands
- Reading `.env`, `.pem`, SSH keys, and other secret files
- Writing to protected paths outside your project
- `git push --force` (without `--force-with-lease`)
- Remote script execution (`curl ... | bash`)
- Interpreter-mediated file deletion (Python `os.remove`, Node `unlinkSync`, etc.)
- Commands exceeding ~100KB / 100,000 bytes (padding attack prevention)

**Confirmation prompts** (asks before proceeding):
- `rm -rf <directory>` (non-root recursive deletion)
- `git reset --hard`, `git clean`, `git stash drop`, branch deletion
- `git push --force-with-lease`
- SQL destructive operations (`DROP TABLE`, `TRUNCATE`, `DELETE` without `WHERE`)
- Moving protected files (`.env`, `.git`, `.claude`, `CLAUDE.md`)
- `find -exec rm`, `xargs rm`

**Protected files** (three-tier access control):

| Protection Level | Effect | Example Files |
|-----------------|--------|---------------|
| **Zero Access** | Cannot be read, written, or deleted | `.env`, `*.pem`, `*.key`, `~/.ssh/**`, `~/.aws/**`, `*credentials*.json`, `*.tfstate` |
| **Read Only** | Can be read, cannot be written or edited | `package-lock.json`, `yarn.lock`, `node_modules/**`, `dist/**`, `__pycache__/**` |
| **No Delete** | Can be read and edited, cannot be deleted | `.gitignore`, `CLAUDE.md`, `LICENSE`, `README.md`, `Dockerfile`, `package.json`, `.github/**` |

Default patterns cover both Unix and Windows commands.

## Installation

### Manual Installation (recommended)

> **Requires Python 3.10+** and Git. Verify with `python3 --version` and `git --version` before installing.

```bash
git clone https://github.com/idnotbe/claude-code-guardian
claude --plugin-dir /path/to/claude-code-guardian --dangerously-skip-permissions
```

> **Note**: Point `--plugin-dir` to the repository root (the directory containing `hooks/`), not to any subdirectory.

> **Persistence**: The `--plugin-dir` flag applies to a single session. To load Guardian automatically, add to your shell profile:
> ```bash
> # ~/.bashrc or ~/.zshrc
> alias claude='claude --plugin-dir /path/to/claude-code-guardian'
> ```

To update, run `git pull` in the cloned directory.

### From Marketplace

> **Unverified**: Marketplace integration is currently experimental and these commands have not been tested against a live Claude Code plugin CLI. Manual installation (above) is the reliable path.

The following are two alternative syntaxes that may work depending on your Claude Code version:

```bash
# Alternative A: marketplace add
/plugin marketplace add idnotbe/claude-code-guardian

# Alternative B: direct install
/plugin install claude-code-guardian@idnotbe-security
```

See [UX-07 in KNOWN-ISSUES.md](KNOWN-ISSUES.md) for details.

### Optional: Install `regex` for ReDoS Protection

Guardian uses regex pattern matching for command interception. For added protection against regular expression denial-of-service attacks, install the `regex` package:

```bash
pip install regex
```

Without it, Guardian falls back to Python's standard `re` module (no timeout on regex execution). This is acceptable for default patterns but recommended if you add complex custom patterns.

## Quick Start

1. **Install Guardian** (see [Installation](#installation) above)

2. **Launch Claude Code with Guardian loaded**:
   ```bash
   claude --plugin-dir /path/to/claude-code-guardian --dangerously-skip-permissions
   ```

3. **Run the setup wizard** to create a project-tailored config:
   ```
   /guardian:init
   ```
   The wizard auto-detects your project type (Node.js, Python, Rust, Go, etc.) and generates appropriate security rules.

4. **Verify Guardian is active** by asking Claude to run a known-blocked command:
   ```
   Ask Claude to: "cat .env"
   ```
   Guardian should block this even if `.env` does not exist. If it succeeds silently, hooks are not active -- check your `--plugin-dir` path.

> **Skipping setup**: If you don't run `/guardian:init`, Guardian uses built-in defaults from `assets/guardian.default.json`. These are secure but not project-tailored. Run `/guardian:init` anytime to customize.

> **Testing config changes**: Use dry-run mode to test without blocking operations:
> ```bash
> CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/claude-code-guardian --dangerously-skip-permissions
> ```

## Configuration

### Configuration File Location

Guardian resolves configuration in this order (first found wins):

1. **Project config**: `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` -- created by `/guardian:init`, specific to your project
2. **Plugin default**: `$CLAUDE_PLUGIN_ROOT/assets/guardian.default.json` -- bundled with the plugin
3. **Emergency fallback**: Hardcoded minimal config protecting `.git`, `.claude`, `_archive`, `.env`, `*.pem`, `*.key`, `~/.ssh/**`, `~/.gnupg/**`, `~/.aws/**`, `secrets.json`, and `secrets.yaml`

If your project config has a JSON syntax error, Guardian logs the error and falls back to the plugin default. Check `.claude/guardian/guardian.log` for `[FALLBACK]` messages.

The config file is safe to commit to version control -- it contains only security rules, never secrets.

**Runtime files** created by Guardian:
- `.claude/guardian/guardian.log` -- decision log (auto-rotates at 1MB, keeps one backup as `.log.1`)
- `.claude/guardian/.circuit_open` -- circuit breaker state file (auto-expires after 1 hour)
- `_archive/` -- archived files before deletion (add to `.gitignore`)

### Configuration Reference

Use `assets/guardian.default.json` as your starting point. Copy it to `.claude/guardian/config.json` and modify, or use `/guardian:init` to generate a tailored config.

> **IDE validation**: Add `"$schema": "../../assets/guardian.schema.json"` (adjust path relative to your config file) to your `config.json` for autocompletion and validation in VS Code and other JSON Schema-aware editors.

#### `version` (required)

Semantic version string. Current: `"1.0.0"`.

```json
"version": "1.0.0"
```

#### `hookBehavior` (required)

Controls what happens when a hook times out or encounters an error. Fail-closed (`deny`) is the safe default.

| Field | Type | Default | Values | Description |
|-------|------|---------|--------|-------------|
| `onTimeout` | string | `"deny"` | `"allow"`, `"deny"`, `"ask"` | Action when hook exceeds time limit |
| `onError` | string | `"deny"` | `"allow"`, `"deny"`, `"ask"` | Action when hook encounters an error |
| `timeoutSeconds` | number | `10` | 1-60 | Configured timeout value (see notes below) |

> **Security warning**: Setting `onError` or `onTimeout` to `"allow"` disables fail-closed behavior. If a hook crashes or times out, operations will be silently permitted instead of denied. Only use `"allow"` for temporary debugging, never in production.

```json
"hookBehavior": {
  "onTimeout": "deny",
  "onError": "deny",
  "timeoutSeconds": 10
}
```

> **Note**: `timeoutSeconds` is not enforced as a blanket hook-level timeout. Individual subprocess calls (git operations) have their own timeouts (5-30s). See [SCOPE-02 in KNOWN-ISSUES.md](KNOWN-ISSUES.md) for details.

#### `bashToolPatterns` (required)

Regex patterns that intercept bash commands before execution. Patterns use Python `re` syntax and are searched (not anchored) against the full command string.

| Field | Type | Description |
|-------|------|-------------|
| `block` | array of `{pattern, reason}` | Patterns always denied (no override) |
| `ask` | array of `{pattern, reason}` | Patterns requiring user confirmation |

Block patterns are checked first and short-circuit on match. If a command matches both block and ask, it is blocked.

```json
"bashToolPatterns": {
  "block": [
    {"pattern": "rm\\s+-[rRf]+\\s+/(?:\\s*$|\\*)", "reason": "Root or full system deletion"}
  ],
  "ask": [
    {"pattern": "rm\\s+-[rRf]+", "reason": "Recursive/force deletion"}
  ]
}
```

The default config includes 18 block patterns and 18 ask patterns. See `assets/guardian.default.json` for the full list.

#### `zeroAccessPaths`

Glob patterns for files with NO access -- cannot be read, written, or deleted by any tool. The strongest protection level.

```json
"zeroAccessPaths": [
  ".env", ".env.*", ".env*.local", "*.env",
  "*.pem", "*.key", "*.pfx", "*.p12",
  "id_rsa", "id_rsa.*", "id_ed25519", "id_ed25519.*",
  "~/.ssh/**", "~/.gnupg/**", "~/.aws/**",
  "~/.config/gcloud/**", "~/.azure/**", "~/.kube/**",
  "*credentials*.json", "*serviceAccount*.json", "firebase-adminsdk*.json",
  "*.tfstate", "*.tfstate.backup", ".terraform/**",
  "secrets.yaml", "secrets.yml", "secrets.json"
]
```

#### `readOnlyPaths`

Glob patterns for files that can be read but not written or edited. Protects generated and managed files from accidental modification.

```json
"readOnlyPaths": [
  "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
  "poetry.lock", "Pipfile.lock", "Cargo.lock",
  "Gemfile.lock", "composer.lock", "go.sum", "*.lock",
  "node_modules/**", "dist/**", "build/**",
  "__pycache__/**", ".venv/**", "venv/**",
  "target/**", "vendor/**"
]
```

#### `noDeletePaths`

Glob patterns for files that can be read and edited but cannot be deleted via `rm` or overwritten via the Write tool.

> **Limitation**: `noDeletePaths` is only enforced for Bash delete commands (`rm`, `git rm`, etc.) and Write tool overwrites of existing files. The Edit tool can still modify file contents. If you need full write protection, use `readOnlyPaths` instead. See [SCOPE-01 in KNOWN-ISSUES.md](KNOWN-ISSUES.md).

```json
"noDeletePaths": [
  ".gitignore", ".gitattributes", ".gitmodules",
  "CLAUDE.md", "LICENSE", "LICENSE.*",
  "README.md", "README.*", "CONTRIBUTING.md",
  "CHANGELOG.md", "SECURITY.md",
  ".github/**", ".gitlab-ci.yml", "Jenkinsfile",
  ".circleci/**", "azure-pipelines.yml",
  "Dockerfile", "Dockerfile.*",
  "docker-compose*.yml", "docker-compose*.yaml", ".dockerignore",
  "Makefile", "pyproject.toml", "package.json",
  "tsconfig.json", "Cargo.toml", "go.mod"
]
```

#### `allowedExternalReadPaths`

Glob patterns for paths **outside** the project directory allowed for **read-only** access. Write and Edit operations on these paths are denied. Only bypasses the "outside project" check -- zeroAccess, readOnly, and symlink checks still apply.

Default: `[]` (empty -- no external read access).

```json
"allowedExternalReadPaths": [
  "~/.config/myapp/**",
  "/usr/share/dict/**"
]
```

#### `allowedExternalWritePaths`

Glob patterns for paths **outside** the project directory allowed for **read and write** access. Same security caveats as external read paths.

Default: `[]` (empty -- no external write access).

```json
"allowedExternalWritePaths": [
  "/opt/deploy/**"
]
```

#### `gitIntegration`

Controls automatic git commit behavior and identity.

**`autoCommit`** -- checkpoint commits on session stop:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Master switch for auto-commit |
| `onStop` | boolean | `true` | Commit tracked changes when session ends |
| `messagePrefix` | string | `"auto-checkpoint"` | Prefix for commit messages (max 30 chars) |
| `includeUntracked` | boolean | `false` | Include untracked files in auto-commits |

> **Security warning**: `includeUntracked: true` combined with auto-commit's unconditional `--no-verify` flag can commit secrets that pre-commit hooks would normally catch. Keep this `false` unless you understand the risk. See [Known Security Gaps in CLAUDE.md](CLAUDE.md).

**`preCommitOnDangerous`** -- checkpoint commits before destructive operations:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Create checkpoint before dangerous ops |
| `messagePrefix` | string | `"pre-danger-checkpoint"` | Prefix for checkpoint commit messages |

**`identity`** -- git author for Guardian-created commits:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `email` | string | `"guardian@claude-code.local"` | Git author email |
| `name` | string | `"Guardian Auto-Commit"` | Git author name |

```json
"gitIntegration": {
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

#### `bashPathScan`

Layer 1 defense: scans bash command strings for references to protected file names using word-boundary matching. This catches indirect references like `python3 script.py --file .env` that pattern-based regex might miss.

| Field | Type | Default | Values | Description |
|-------|------|---------|--------|-------------|
| `enabled` | boolean | `true` | | Enable/disable the path scan layer |
| `scanTiers` | array | `["zeroAccess"]` | `"zeroAccess"`, `"readOnly"`, `"noDelete"` | Which protection tiers to scan for |
| `exactMatchAction` | string | `"ask"` | `"deny"`, `"ask"` | Action for exact filename matches |
| `patternMatchAction` | string | `"ask"` | `"deny"`, `"ask"` | Action for glob-derived pattern matches |

```json
"bashPathScan": {
  "enabled": true,
  "scanTiers": ["zeroAccess"],
  "exactMatchAction": "ask",
  "patternMatchAction": "ask"
}
```

For stricter enforcement, set `exactMatchAction` to `"deny"` or expand `scanTiers` to include `"readOnly"` and `"noDelete"`.

### Glob Pattern Syntax

All path arrays use glob patterns:

| Pattern | Matches | Example |
|---------|---------|---------|
| `*` | Any characters in a single path segment | `*.pem` matches `server.pem` |
| `**` | Zero or more directories (recursive) | `migrations/**` matches `migrations/001_init.sql` |
| `?` | Any single character | `?.env` matches `a.env` |
| `[abc]` | Character class | `[._]env` matches `.env` and `_env` |
| `~` | User's home directory | `~/.ssh/**` matches `/home/user/.ssh/id_rsa` |

Important notes:
- Patterns match against the file path relative to the project root
- Case-sensitive on Linux, case-insensitive on Windows and macOS
- Use `**` for recursive directory matching; `dir/*` only matches immediate children
- Use forward slashes (`/`) even on Windows

### Writing Regex Patterns

Patterns for `bashToolPatterns` use Python regex syntax. Key considerations:

**JSON double-escaping**: In JSON, backslashes must be doubled. `\s` becomes `\\s`, `\b` becomes `\\b`.

```json
{"pattern": "rm\\s+-[rRf]+", "reason": "Recursive/force deletion"}
```

**Use word boundaries and whitespace anchors** to avoid false positives. `rm` alone matches "format". Use `\\brm\\s+` instead.

**Use `(?i)` for case-insensitive matching**:
```json
{"pattern": "(?i)drop\\s+table", "reason": "SQL DROP TABLE"}
```

**Use negative lookahead to create exceptions**:
```json
{"pattern": "git\\s+push\\s[^;|&\\n]*(?:--force(?!-with-lease)|-f\\b)", "reason": "Force push (not force-with-lease)"}
```

**Test patterns with dry-run mode**:
```bash
CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/guardian --dangerously-skip-permissions
```
Check `.claude/guardian/guardian.log` for `[DRY-RUN]` entries.

**Avoid catastrophic backtracking**: Patterns like `(a+)+b` can take exponential time. Guardian has ReDoS protection with a 0.5s timeout if the `regex` package is installed.

See `skills/config-guide/references/schema-reference.md` for a complete regex cookbook with patterns for package management, infrastructure, database, git, and system commands.

## How It Works

> This section explains Guardian internals. Skip to [User Guide](#user-guide) if you just want to customize protection.

### Architecture

Guardian registers five hooks with Claude Code via `hooks/hooks.json`:

| Hook | Event | Script | Fail Mode |
|------|-------|--------|-----------|
| Bash Guardian | PreToolUse: Bash | `bash_guardian.py` | Fail-closed (deny on error) |
| Read Guardian | PreToolUse: Read | `read_guardian.py` | Fail-closed (deny on error) |
| Edit Guardian | PreToolUse: Edit | `edit_guardian.py` | Fail-closed (deny on error) |
| Write Guardian | PreToolUse: Write | `write_guardian.py` | Fail-closed (deny on error) |
| Auto-Commit | Stop | `auto_commit.py` | Fail-open (never blocks exit) |

Hooks receive JSON on stdin and communicate decisions via JSON on stdout:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "[BLOCKED] Root or full system deletion"
  }
}
```

Three possible decisions:
- **deny**: Block the operation unconditionally. Reason prefixed with `[BLOCKED]`.
- **ask**: Prompt user for confirmation. Reason prefixed with `[CONFIRM]`.
- **allow**: Permit the operation silently (or: produce no stdout output).

All four security hooks are **fail-closed**: if a hook errors or times out, the operation is **denied** rather than allowed through. A false denial is annoying; a false allow could be catastrophic.

> **Important**: If Guardian fails to load while `--dangerously-skip-permissions` is active, you have zero protection. Verify hooks are loaded at the start of your session by running a blocked command (e.g., `cat .env`). If it succeeds silently, hooks are not active.

### How "ask" works in permissionless mode

Claude Code's hook system can still prompt for user confirmation even when `--dangerously-skip-permissions` is active. Hooks operate at a layer above the permission bypass -- this is the architectural foundation Guardian relies on.

### Bash Guardian (Multi-Layer Defense)

The bash guardian uses a layered defense-in-depth approach. All layers complete before any decision is emitted, and verdicts aggregate with precedence: **deny > ask > allow**.

| Layer | Name | Purpose | Behavior |
|-------|------|---------|----------|
| 0 | Block Patterns | Catastrophic command regex matching | Short-circuits to deny |
| 0b | Ask Patterns | Dangerous-but-legitimate command regex matching | Accumulates verdict |
| 1 | Protected Path Scan | Raw string scan for protected filenames in command text | Accumulates verdict |
| 2 | Command Decomposition | Split compound commands (`;`, `&&`, `\|\|`, `\|`, `&`, newlines) | -- |
| 3 | Path Extraction | Extract file paths from parsed arguments and redirections | -- |
| 4 | Command Type Detection | Classify sub-commands as write/delete operations | Per-path checks |

**Layer 0** also blocks commands exceeding 100KB as a padding attack prevention measure.

**Layer 1** uses the `bashPathScan` config to detect protected filenames inside arbitrary bash commands using word-boundary matching. This catches cases like `python3 script.py --file .env` that pattern regex might miss.

**Layers 2-4** decompose compound commands, extract file paths from arguments and redirections (including `>`, `>>`, `2>`, `&>`), and check each path against:
- Symlink escape (resolves outside project)
- Zero-access paths
- Read-only paths (for write operations)
- External read-only paths (for write/delete operations)
- No-delete paths (for delete operations)

**Fail-closed safety net**: If a write or delete command is detected but no target paths could be resolved, the verdict escalates to "ask" rather than silently allowing.

### Path Guardian (Read/Edit/Write)

The Read, Edit, and Write guardians are thin wrappers that check file paths in order:

| Check | Order | Read | Edit | Write |
|-------|-------|------|------|-------|
| Malformed JSON input | 1 | Deny | Deny | Deny |
| Null bytes in path | 2 | Deny | Deny | Deny |
| Path resolution failure | 3 | Deny | Deny | Deny |
| Symlink escape | 4 | Deny | Deny | Deny |
| Outside project (no external allow) | 5 | Deny | Deny | Deny |
| External read-only path (write attempt) | 5 | Allow | Deny | Deny |
| Self-guardian path | 6 | Deny | Deny | Deny |
| Zero-access path | 7 | Deny | Deny | Deny |
| Read-only path | 8 | Skip | Deny | Deny |
| No-delete path (existing file) | 9 | Skip | Skip | Deny |

### Auto-Commit (Stop Hook)

When a Claude Code session ends, the auto-commit hook creates a checkpoint commit of your changes. This is fail-open by design -- a commit failure must never block session termination.

Auto-commit is **skipped** when:
- `autoCommit.enabled` or `autoCommit.onStop` is false
- Circuit breaker is open
- Detached HEAD state (commits would be orphaned)
- Rebase, merge, cherry-pick, or bisect in progress
- No uncommitted changes
- Dry-run mode is active

Commit messages follow the format `{prefix}: {timestamp}` (max 72 characters per Git convention).

**Pre-danger checkpoints**: When a command triggers an "ask" verdict (e.g., `git reset --hard`), Guardian commits tracked changes first using the `preCommitOnDangerous` settings, creating a rollback point. Like auto-commit, pre-danger checkpoints use `--no-verify` to bypass pre-commit hooks.

### Archive-Before-Delete

When Claude runs a delete command (e.g., `rm temp-file.txt`), Guardian archives untracked files before deletion:

1. Detects the delete command and extracts target file paths
2. For **untracked** files: copies to `_archive/` before deletion
3. For **tracked** files: no archive needed (recoverable via `git checkout`)
4. Prompts user for confirmation with archive details

**Archive location**: `_archive/{YYYYMMDD_HHMMSS}_{title}/`
- Each archive directory contains the file copies and a `_deletion_log.json` with metadata (timestamp, command, original paths)

**Archive limits** (prevent DoS):
- Maximum 100MB per file (larger files skipped with a warning)
- Maximum 500MB total per archive operation
- Maximum 50 files per operation
- Symlinks preserved as symlinks (not dereferenced)

**If archiving fails** (permission error, disk full, etc.), Guardian warns the user that data will be **permanently lost** and asks for confirmation before proceeding.

Add `_archive/` to your `.gitignore` to prevent committing archived files.

### Self-Guarding

Guardian protects its own configuration file (`.claude/guardian/config.json`) from being modified by the AI agent through the Edit, Write, or Read tools. This prevents the AI from weakening security rules.

Self-guarding is always active and cannot be disabled via configuration. It protects:
- The static path `.claude/guardian/config.json`
- Whichever config file was actually loaded (plugin default or project-specific)

To modify the config, edit it directly in your editor (VS Code, vim, etc.) or use the `/guardian:init` wizard. The protection only applies to Claude's Read, Edit, and Write tool calls, not to direct human editing or Bash commands. Bash-based config modification (e.g., `sed -i`) is separately covered by the Layer 1 path scan and `.claude` directory deletion patterns.

### Circuit Breaker

If auto-commit or pre-danger checkpoint fails, Guardian opens a circuit breaker to prevent cascading failures. While the circuit is open:
- Auto-commits are skipped
- Pre-danger checkpoints are skipped
- All other security hooks (Bash, Read, Edit, Write) continue to function normally

The circuit breaker:
- Auto-resets after **1 hour**
- Is stored at `.claude/guardian/.circuit_open`
- Can be manually reset by deleting the file: `rm .claude/guardian/.circuit_open`
- Is cleared automatically on a successful auto-commit

## Security Model

### What Guardian protects against

- Accidental file deletion and destructive shell commands
- Secret file exposure (`.env`, credentials, private keys, cloud configs)
- Force pushes and other irreversible git operations
- Loss of work (via auto-commit checkpoints and archive-before-delete)
- Symlink escape attacks (symlinks resolving outside the project)
- Path traversal attacks (`../` normalized via `Path.resolve(strict=False)`)
- Null byte injection in file paths
- Padding attacks (commands >100KB denied)
- AI-initiated weakening of security config (self-guarding)

### What Guardian does NOT protect against

- Determined human adversaries crafting bypass commands
- Arbitrary code within interpreter scripts (Guardian blocks known deletion APIs like `os.remove` and `shutil.rmtree` at the Bash command level, but cannot catch all possible code patterns)
- Operations run in a separate terminal or process outside Claude Code
- Its own failure to load or initialize
- ANSI-C quoting (`$'...'`) in bash commands (known parser limitation)
- TOCTOU (time-of-check-time-of-use) race conditions for symlink checks

### Design principles

- **Fail-closed**: All security hooks deny on error or timeout. Helper functions for boundary checks use fail-closed defaults.
- **Defense in depth**: Multiple independent checks catch overlapping threat vectors. Block patterns, path scans, path extraction, and symlink checks each provide independent protection.
- **Fail-open for non-security paths**: Auto-commit and logging never block operations. Commit failures never prevent session termination.
- **Minimal false positives**: Allowed commands under 10 characters, or commands starting with `ls`, `cd`, `pwd`, `echo`, `cat`, or `type`, are not logged.

Use Guardian alongside git backups, CI/CD checks, and standard access controls -- not instead of them.

## User Guide

### Understanding Default Protection

The default configuration (`assets/guardian.default.json`) provides three layers of protection:

**1. Command interception** (18 block + 18 ask patterns):
- **Blocked**: root deletion, `.git`/`.claude`/`_archive` deletion, force push, history rewriting, reflog destruction, find-with-delete, shred, remote script execution, fork bombs, command substitution with deletion, eval with deletion, interpreter-mediated file deletion
- **Ask-confirm**: recursive/force deletion, Windows delete/Remove-Item, git reset/clean/checkout/stash-drop, force-with-lease, branch deletion, truncate, moving protected files, moving outside project, SQL DROP/TRUNCATE/DELETE-without-WHERE, find-exec-rm, xargs-rm

**2. File path protection** (27 zero-access + 18 read-only + 27 no-delete patterns):
- **Zero access**: env files, crypto keys, SSH keys, cloud credential directories, service account JSON, Terraform state, secrets files
- **Read only**: lock files, dependency directories, build output directories
- **No delete**: git config files, project docs, CI/CD configs, Docker configs, build configs

**3. Bash path scan** (Layer 1):
- Scans command strings for protected filenames using word-boundary matching
- Default: scans `zeroAccess` tier, action is `ask` for both exact and pattern matches

### Customizing Command Patterns

**Move a command from block to ask** (e.g., allow force push with confirmation):
1. Find the pattern in `bashToolPatterns.block` in your config
2. Remove it from `block` and add it to `ask`
3. Save. Changes take effect on the next tool call.

**Add a new blocked command** (e.g., block `npm publish`):
```json
{"pattern": "npm\\s+publish", "reason": "Publishing to npm registry"}
```
Add to `bashToolPatterns.block` in your config, or use the config assistant: `"Block npm publish in this project"`.

**Add an ask-confirm command** (e.g., require confirmation for `docker push`):
```json
{"pattern": "docker\\s+(?:push|tag)", "reason": "Pushing/tagging Docker images"}
```

**Use the config assistant** for natural language config changes. Simply ask Claude about your Guardian configuration while the plugin is loaded:
- `"block terraform destroy"`
- `"make npm publish require confirmation"`
- `"remove the block on git filter-branch"` (the assistant will warn about security implications)

### Customizing Path Restrictions

**Protect a secret file** -- add to `zeroAccessPaths`:
```json
"zeroAccessPaths": ["config/secrets.yaml", "*.p8"]
```

**Protect files from deletion** -- add to `noDeletePaths`:
```json
"noDeletePaths": ["migrations/**", "db/migrate/**"]
```

**Allow reading external files** -- add to `allowedExternalReadPaths`:
```json
"allowedExternalReadPaths": ["~/.config/myapp/**"]
```
This allows Read tool access but blocks Write/Edit. Zero-access and symlink checks still apply. For example, `~/.config/myapp/service.key` would still be blocked by `zeroAccessPaths` (`*.key`) even if `~/.config/myapp/**` is in `allowedExternalReadPaths`.

**Allow writing external files** -- add to `allowedExternalWritePaths`:
```json
"allowedExternalWritePaths": ["/opt/deploy/**"]
```

Common pitfalls:
- Use `migrations/**` not `migrations/` for recursive matching
- `allowedExternalReadPaths` does NOT bypass zero-access -- these are independent checks
- `noDeletePaths` blocks deletion and Write-tool overwrite, but Edit tool can still modify content
- Path matching is case-sensitive on Linux, case-insensitive on macOS/Windows

### Configuring Auto-Commit

**Disable auto-commit entirely**:
```json
"gitIntegration": {
  "autoCommit": { "enabled": false }
}
```

**Include untracked files** (use with caution):
```json
"autoCommit": { "includeUntracked": true }
```

**Customize the commit identity** (to distinguish auto-commits in git log):
```json
"identity": {
  "email": "bot@mycompany.com",
  "name": "Guardian Bot"
}
```

**Disable pre-danger checkpoints**:
```json
"preCommitOnDangerous": { "enabled": false }
```

### Working with Multiple Projects

Guardian is installed once as a plugin directory. Each project gets its own config:

```
~/projects/frontend/.claude/guardian/config.json   (Node.js-specific)
~/projects/backend/.claude/guardian/config.json     (Python-specific)
~/projects/infra/.claude/guardian/config.json       (Terraform-specific)
```

Set up each project by running `/guardian:init` within it. Use the shell alias for convenience:

```bash
alias claude='claude --plugin-dir ~/tools/claude-code-guardian'
```

Plugin updates (`git pull`) apply to all projects. Project configs are independent and should be committed to each project's git repository.

### Understanding Block Messages

When Guardian blocks an operation, it provides a reason. Common messages:

| Message | Meaning | Resolution |
|---------|---------|------------|
| `Protected path: .env` | File is in `zeroAccessPaths` | Remove from `zeroAccessPaths` if access is needed |
| `Read-only file: package-lock.json` | File is in `readOnlyPaths` | Remove from `readOnlyPaths` if writes are needed |
| `Protected from deletion: README.md` | File is in `noDeletePaths` (Bash `rm`) | Remove from `noDeletePaths` if deletion is needed |
| `Protected from overwrite: LICENSE` | File is in `noDeletePaths` (Write tool) | Remove from `noDeletePaths` or use Edit tool instead |
| `Path is outside project directory` | File is not in the project tree | Add to `allowedExternalReadPaths` or `allowedExternalWritePaths` |
| `Symlink points outside project` | Symlink resolves outside project | Verify the symlink target is safe |
| `Protected system file: config.json` | Guardian self-guarding its own config | Edit the config directly in your editor, not through Claude |
| `Root or full system deletion` | Catastrophic rm pattern matched | Rephrase the command to target specific files |
| `Force push to remote (destructive)` | `git push --force` matched | Use `--force-with-lease` instead (prompted, not blocked) |
| `Detected write but could not resolve target paths` | Fail-closed safety net | Provide explicit file paths in the command |
| `Protected path reference detected: .env` | Layer 1 bash path scan found a reference | Verify the command does not expose protected files |

For detailed context, check `.claude/guardian/guardian.log`.

## Troubleshooting

**Log file location**: `.claude/guardian/guardian.log` (inside your project directory). The log shows the full decision chain for every hook invocation.

Log entry levels:
- `[ALLOW]` -- operation permitted
- `[BLOCK]` -- operation denied
- `[ASK]` -- operation requires user confirmation
- `[SCAN]` -- Layer 1 path scan result
- `[ARCHIVE]` -- file archived before deletion
- `[DRY-RUN]` -- dry-run mode (what would have happened)
- `[ERROR]` -- errors during hook execution
- `[WARN]` -- warnings (config validation, staging failures)
- `[FALLBACK]` -- config loading failed, using fallback

**Sample log output**:
```
2026-02-16 14:30:22 [BLOCK] bash_guardian: Zero access path: .env | cmd: cat .env
2026-02-16 14:30:23 [ALLOW] bash_guardian: ls -la src/
2026-02-16 14:30:45 [ASK] bash_guardian: Recursive/force deletion | cmd: rm -rf temp/
2026-02-16 14:31:02 [BLOCK] write_guardian: Protected path: .env
2026-02-16 14:31:10 [FALLBACK] Config parse error in .claude/guardian/config.json, using plugin default
```

**Common issues**:

| Problem | Cause | Solution |
|---------|-------|----------|
| Hooks not firing | `--plugin-dir` not set or wrong path | Verify path: `claude --plugin-dir /path/to/claude-code-guardian` |
| `python3: command not found` | Python 3.10+ not installed or not on PATH | Install Python 3.10+ and ensure `python3` is available |
| Config not loading | JSON syntax error in `config.json` | Validate JSON syntax; compare with `assets/guardian.default.json` |
| Config validation warnings | Invalid field values in config | Check `guardian.log` for `[WARN] Config validation:` messages |
| Auto-commits stopped | Circuit breaker tripped | Delete `.claude/guardian/.circuit_open` or wait 1 hour |
| Auto-commits stopped | Detached HEAD state | Check out a branch |
| Auto-commits stopped | Rebase/merge in progress | Complete or abort the rebase/merge |
| Unexpected blocks | Config pattern too broad | Check `guardian.log` for which pattern matched; narrow the regex |
| External file access blocked | Path outside project | Add to `allowedExternalReadPaths` or `allowedExternalWritePaths` |
| Guardian config edit blocked | Self-guarding protection | Edit config directly in your editor, not through Claude |
| `Guardian system error` | Hook script crashed | Check `guardian.log` for the stack trace |

> **Note**: Guardian forces `LC_ALL=C` for all git operations to ensure consistent parsing. Git output in Guardian logs will be in English regardless of your system locale.

**Checking if hooks are loaded**: At the start of your session, ask Claude to `cat .env` (the file does not need to exist). If Guardian is active, the operation is blocked. If it succeeds silently, hooks are not loaded.

## Disabling Guardian

**Dry-run mode** -- test config changes without blocking:
```bash
CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/claude-code-guardian --dangerously-skip-permissions
```
Valid values: `1`, `true`, `yes` (case-insensitive). Hooks log what they would do as `[DRY-RUN]` entries but do not block operations or create commits.

**Temporary disable** -- remove `--plugin-dir` from your launch command.

**Uninstall** -- delete the cloned repository and remove any shell aliases. If you ran `/guardian:init`, also remove `.claude/guardian/` from your project.

## Upgrading

1. Pull the latest changes:
   ```bash
   cd /path/to/claude-code-guardian && git pull
   ```

2. Check `CHANGELOG.md` for new features, bug fixes, and breaking changes.

3. Optionally re-run `/guardian:init` to pick up new project-specific patterns.

4. Verify hooks still work after the update by testing with a blocked command.

**Note**: Plugin updates only affect `assets/guardian.default.json` (the plugin default). Your project config at `.claude/guardian/config.json` is not affected. New default patterns are only available to projects without a custom config, or by re-running `/guardian:init`.

> **Deprecated config key**: If your config has `allowedExternalPaths`, rename it to `allowedExternalReadPaths` (for read-only access) or `allowedExternalWritePaths` (for read+write access). The old key is no longer supported.

## FAQ

**Q: Does Guardian work without running `/guardian:init`?**
A: Yes. Guardian uses built-in defaults from `assets/guardian.default.json` if no project config exists. The defaults protect common secret files and block destructive commands. `/guardian:init` creates a project-tailored config.

**Q: Can Claude modify Guardian's config to weaken security?**
A: No. Guardian self-guards its config file. The Edit, Write, and Read tools are all blocked from accessing `.claude/guardian/config.json`. Config changes must be made by a human directly.

**Q: What happens if my config has a JSON syntax error?**
A: Guardian falls through to the plugin default config and logs a `[FALLBACK]` warning. Your project is still protected, but custom rules are not applied.

**Q: Why was my legitimate command blocked?**
A: Check `.claude/guardian/guardian.log` to see which pattern matched. Then either narrow the pattern or move it from `block` to `ask` so you get a confirmation prompt instead. Use dry-run mode to test changes.

**Q: Does Guardian protect against all file deletion?**
A: Guardian catches `rm`, `del`, `rmdir`, `Remove-Item`, `git rm`, `mv X /dev/null`, file truncation (`> file`), and interpreter-based deletion (Python, Node, Perl, Ruby) in bash commands. It also enforces `noDeletePaths` via the Write tool for existing files. However, it cannot catch arbitrary code patterns inside interpreter scripts.

**Q: Does `noDeletePaths` prevent editing a file?**
A: No. `noDeletePaths` prevents deletion via `rm` and overwrite via the Write tool, but the Edit tool can still modify file contents. For full write protection, use `readOnlyPaths`.

**Q: Why doesn't `hookBehavior.timeoutSeconds` seem to work?**
A: `timeoutSeconds` is not enforced as a blanket hook timeout. Individual subprocess calls (git operations) have their own timeouts. This is by design to avoid corrupting git state or partial file archives. See [SCOPE-02 in KNOWN-ISSUES.md](KNOWN-ISSUES.md).

**Q: Can I use Guardian with multiple projects?**
A: Yes. Install the plugin once and use the same `--plugin-dir` path for all projects. Each project gets its own config at `.claude/guardian/config.json` via `/guardian:init`.

**Q: What is the `_archive/` directory?**
A: Guardian archives untracked files to `_archive/` before allowing deletion commands. This provides a safety net for files not tracked by git. Add `_archive/` to your `.gitignore`.

**Q: How do I reset the circuit breaker?**
A: Delete `.claude/guardian/.circuit_open`, or wait 1 hour for automatic reset. The circuit breaker only affects auto-commit -- security hooks continue to function normally.

## Testing

The test suite covers `bash_guardian.py` and `_guardian_utils.py` extensively, with ~631 test methods across 7 category directories.

```bash
# Run core and security tests (unittest-based, pytest-compatible)
python -m pytest tests/core/ tests/security/ -v

# Run all unittest-compatible tests
python -m pytest tests/core/ tests/security/ tests/regression/ -v

# Run a single test file directly
python3 tests/core/test_p0p1_comprehensive.py
```

See `tests/README.md` for detailed test documentation including directory structure, category boundaries, and how to add new tests.

See `TEST-PLAN.md` for the prioritized test action plan covering known coverage gaps.

## Requirements

- Python 3.10 or later
- Git (for auto-commit features)
- Optional: `regex` package for ReDoS timeout protection (`pip install regex`)

## Environment Variables

| Variable | Purpose | Used By |
|----------|---------|---------|
| `CLAUDE_PROJECT_DIR` | Project directory root (set by Claude Code) | All hooks |
| `CLAUDE_PLUGIN_ROOT` | Plugin installation directory (set by Claude Code) | Config loading |
| `CLAUDE_HOOK_DRY_RUN` | Enable dry-run mode (`1`, `true`, `yes`) | All hooks |

## License

MIT
