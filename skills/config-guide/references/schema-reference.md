# Protection Schema Reference

Complete documentation for `protection.json` -- the Guardian configuration file.

---

## Top-Level Structure

```json
{
  "version": "1.0.0",
  "hookBehavior": { ... },
  "bashToolPatterns": { ... },
  "zeroAccessPaths": [ ... ],
  "readOnlyPaths": [ ... ],
  "noDeletePaths": [ ... ],
  "allowedExternalPaths": [ ... ],
  "gitIntegration": { ... }
}
```

Required fields: `version`, `hookBehavior`, `bashToolPatterns`. All others are optional.

---

## version

**Type:** string (semver format: `MAJOR.MINOR.PATCH`)
**Required:** Yes

```json
"version": "1.0.0"
```

---

## hookBehavior

Controls what happens when a hook times out or encounters an error. **Fail-closed (`deny`) is the safe default.**

| Field | Type | Values | Default | Description |
|-------|------|--------|---------|-------------|
| `onTimeout` | string | `allow`, `deny`, `ask` | `deny` | Action when hook exceeds `timeoutSeconds` |
| `onError` | string | `allow`, `deny`, `ask` | `deny` | Action when hook script throws an error |
| `timeoutSeconds` | number | 1-60 | 10 | Max seconds before timeout triggers |

```json
"hookBehavior": {
  "onTimeout": "deny",
  "onError": "deny",
  "timeoutSeconds": 10
}
```

**Guidance:**
- Keep `onTimeout` and `onError` as `"deny"` unless you have a specific reason to change them
- `"ask"` prompts the user for a decision on each occurrence
- `"allow"` silently permits the operation -- use only if false positives are frequent and acceptable
- Increase `timeoutSeconds` only if your machine is slow (hooks are lightweight, 10s is generous)

---

## bashToolPatterns

Regex patterns that intercept bash commands before execution.

### block

Commands matching these patterns are **silently denied**. The user sees the reason but cannot override.

```json
"block": [
  {
    "pattern": "rm\\s+-[rRf]+\\s+/(?:\\s*$|\\*)",
    "reason": "Root or full system deletion"
  }
]
```

### ask

Commands matching these patterns **require user confirmation**. The reason is displayed as context.

```json
"ask": [
  {
    "pattern": "rm\\s+-[rRf]+",
    "reason": "Recursive/force deletion"
  }
]
```

### Pattern Rule Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pattern` | string | Yes | Regex pattern (Python `re` syntax) |
| `reason` | string | Yes | Human-readable explanation shown to the user |

**Pattern evaluation order:** `block` patterns are checked first. If a command matches both `block` and `ask`, it is blocked.

---

## Path Protection Arrays

Three arrays control file-level access. Each accepts glob patterns.

### Protection Levels

| Array | Read | Write | Delete | Use For |
|-------|------|-------|--------|---------|
| `zeroAccessPaths` | NO | NO | NO | Secrets, credentials, private keys |
| `readOnlyPaths` | YES | NO | NO | Lock files, build output, vendor dirs |
| `noDeletePaths` | YES | YES | NO | Critical configs, CI files, migrations |

### zeroAccessPaths

Files that cannot be read, written, or deleted. The strongest protection level.

```json
"zeroAccessPaths": [
  ".env",
  ".env.*",
  "*.pem",
  "*.key",
  "~/.ssh/**",
  "*credentials*.json"
]
```

### readOnlyPaths

Files that can be read but not written or deleted. Protects generated/managed files from accidental modification.

```json
"readOnlyPaths": [
  "package-lock.json",
  "yarn.lock",
  "node_modules/**",
  "dist/**",
  "__pycache__/**"
]
```

### noDeletePaths

Files that can be read and written but not deleted. Protects critical project files.

```json
"noDeletePaths": [
  ".gitignore",
  "LICENSE",
  "README.md",
  "CLAUDE.md",
  "Dockerfile",
  "package.json",
  ".github/**"
]
```

### allowedExternalPaths

Paths **outside** the project directory that are explicitly allowed for write operations. Only bypasses the "outside project" check -- zeroAccess and readOnly rules still apply.

```json
"allowedExternalPaths": [
  "~/shared-config/**",
  "/tmp/build-output/**"
]
```

---

## Glob Pattern Syntax

All path arrays use glob patterns with these rules:

| Pattern | Matches | Example |
|---------|---------|---------|
| `*` | Any characters in a single path segment | `*.pem` matches `server.pem` |
| `**` | Zero or more directories (recursive) | `migrations/**` matches `migrations/001_init.sql` |
| `?` | Any single character | `?.env` matches `a.env` |
| `[abc]` | Character class | `[._]env` matches `.env` and `_env` |
| `~` | User's home directory | `~/.ssh/**` matches `/home/user/.ssh/id_rsa` |

**Important notes:**
- Patterns are matched against the file path relative to the project root
- Patterns are case-sensitive on Linux/macOS, case-insensitive on Windows
- Use forward slashes (`/`) even on Windows -- the engine normalizes paths
- `**` must be used for recursive directory matching; `dir/*` only matches immediate children

**Common patterns:**
| Intent | Pattern |
|--------|---------|
| All .env files | `.env`, `.env.*`, `.env*.local`, `*.env` |
| All key/cert files | `*.pem`, `*.key`, `*.pfx`, `*.p12` |
| SSH keys | `id_rsa`, `id_rsa.*`, `id_ed25519`, `id_ed25519.*` |
| Cloud credentials | `~/.aws/**`, `~/.config/gcloud/**`, `~/.azure/**` |
| Terraform state | `*.tfstate`, `*.tfstate.backup`, `.terraform/**` |
| All files in a directory | `migrations/**` |
| All YAML secrets | `secrets.yaml`, `secrets.yml`, `secrets.json` |
| Lock files (generic) | `*.lock` |

---

## gitIntegration

Controls automatic git commit behavior and identity for Guardian-created commits.

### autoCommit

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Master switch for auto-commit |
| `onStop` | boolean | `true` | Commit tracked changes when Claude Code session ends |
| `messagePrefix` | string | `"auto-checkpoint"` | Prefix for commit messages (e.g., `auto-checkpoint: 2026-02-11 14:30:00`) |
| `includeUntracked` | boolean | `false` | Include untracked files in auto-commits (default: tracked only) |

```json
"autoCommit": {
  "enabled": true,
  "onStop": true,
  "messagePrefix": "auto-checkpoint",
  "includeUntracked": false
}
```

### preCommitOnDangerous

Creates a safety checkpoint commit before destructive operations (e.g., commands matching `ask` patterns).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Create checkpoint before dangerous ops |
| `messagePrefix` | string | `"pre-danger-checkpoint"` | Prefix for checkpoint commit messages |

```json
"preCommitOnDangerous": {
  "enabled": true,
  "messagePrefix": "pre-danger-checkpoint"
}
```

### identity

Git author identity used for Guardian auto-commits. Separates automated commits from human commits in git log.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `email` | string | `"guardian@claude-code.local"` | Git author email |
| `name` | string | `"Guardian Auto-Commit"` | Git author name |

```json
"identity": {
  "email": "guardian@claude-code.local",
  "name": "Guardian Auto-Commit"
}
```

---

## Regex Pattern Cookbook

Copy-paste patterns for common protection scenarios.

### Package Management
```json
{"pattern": "npm\\s+publish", "reason": "Publishing to npm registry"}
{"pattern": "pip\\s+install\\s+--break-system-packages", "reason": "System Python modification"}
{"pattern": "cargo\\s+publish", "reason": "Publishing to crates.io"}
{"pattern": "(?:mvn|gradle)\\s+deploy", "reason": "Deploying artifacts to repository"}
{"pattern": "gem\\s+push", "reason": "Publishing to RubyGems"}
```

### Infrastructure
```json
{"pattern": "terraform\\s+destroy", "reason": "Terraform destroy (irreversible)"}
{"pattern": "terraform\\s+apply(?!.*-target)", "reason": "Terraform apply (full infrastructure)"}
{"pattern": "kubectl\\s+delete\\s+(?:namespace|ns)", "reason": "Kubernetes namespace deletion"}
{"pattern": "docker\\s+system\\s+prune", "reason": "Docker system prune (removes all unused data)"}
{"pattern": "docker\\s+push", "reason": "Pushing Docker image to registry"}
```

### Database
```json
{"pattern": "(?i)drop\\s+(?:table|database|index|schema)", "reason": "SQL DROP command"}
{"pattern": "(?i)truncate\\s+table", "reason": "SQL TRUNCATE"}
{"pattern": "(?i)delete\\s+from\\s+\\w+(?:\\s*;|\\s*$|\\s+--)", "reason": "SQL DELETE without WHERE"}
{"pattern": "(?i)(?:psql|mysql|mongo).*--eval.*(?:drop|truncate)", "reason": "CLI database destruction"}
```

### Git Operations
```json
{"pattern": "git\\s+push\\s+(?:--force(?:-with-lease)?|-f)", "reason": "Force push to remote"}
{"pattern": "git\\s+reset\\s+--hard", "reason": "Hard reset (discards uncommitted changes)"}
{"pattern": "git\\s+clean\\s+-[fdxX]+", "reason": "Git clean (removes files from working tree)"}
{"pattern": "git\\s+filter-branch", "reason": "History rewriting"}
{"pattern": "git\\s+push\\s+origin\\s+--delete", "reason": "Deleting remote branch"}
```

### System/Network
```json
{"pattern": "(?:curl|wget)[^|]*\\|\\s*(?:bash|sh|zsh|python|perl|ruby|node)", "reason": "Remote script execution (pipe to interpreter)"}
{"pattern": "chmod\\s+777", "reason": "World-writable permissions"}
{"pattern": "(?:sudo\\s+)?(?:systemctl|service)\\s+(?:stop|disable)", "reason": "Stopping system services"}
{"pattern": "(?:iptables|ufw)\\s+.*(?:flush|reset)", "reason": "Firewall rule flush"}
```

### Pattern Writing Tips

1. **Use `\\s+`** for spaces between words (handles multiple spaces and tabs)
2. **Use `(?i)`** at the start for case-insensitive matching (useful for SQL, Windows commands)
3. **Use `(?:...|...)`** for non-capturing groups with alternatives
4. **Avoid `.*` greedily** -- be specific about what you match to reduce false positives
5. **Escape special chars** -- `\\.`, `\\(`, `\\)`, `\\[`, `\\]`, `\\{`, `\\}`, `\\|`, `\\+`, `\\*`
6. **Test patterns** -- Guardian logs matches to the guardian log file; use dry-run mode (`CLAUDE_HOOK_DRY_RUN=1`) to test without blocking
