# Config Draft Notes: guardian.recommended.json

## Inputs Analyzed
1. User's production config (`/home/idnotbe/projects/ops/.claude/guardian/config.json`) - v1.2.0
2. Current default config (`assets/guardian.default.json`) - v1.0.0
3. Schema (`assets/guardian.schema.json`)
4. Context document (`temp/team1-context.md`)
5. External LLM consultation: Gemini 3.1 Pro (Codex was unavailable - quota exceeded)

## Key Design Decisions

### 1. `.env` Pattern Strategy: Glob vs Explicit

**Decision: Use glob patterns (matching the default config)**

The user's production config has 24 explicit `.env` variants (`.env.local`, `.env.production`, `.env.staging`, etc.). The default config uses 3 glob patterns: `.env`, `.env.*`, `.env*.local`.

For a recommended config aimed at beginners:
- Glob patterns are simpler to understand and maintain
- `.env.*` catches all dot-separated variants (`.env.production`, `.env.staging`, etc.)
- `.env*.local` catches patterns like `.env.development.local`
- Explicit entries risk missing newly-invented naming conventions
- The glob approach is already proven in the default config

Added `*.env` to also catch reverse-named files like `production.env`.

### 2. `.mcp.json` Protection (Claude Code Specific)

**Decision: Add `.mcp.json` and `.mcp.json.bak` to zeroAccessPaths**

This is a Claude Code-specific addition. The `.mcp.json` file contains MCP server configurations which often include API keys, tokens, and connection strings. The `.mcp.json.bak` is a backup that may also contain secrets. These were in the user's production config but NOT in the current default -- a clear oversight for a Claude Code plugin.

### 3. Plan Mode Write Access (Claude Code Specific)

**Decision: Add `~/.claude/plans` and `~/.claude/plans/**` to allowedExternalWritePaths**

Claude Code's plan mode saves plan files to `~/.claude/plans/`. Without this allowance, Guardian would block plan creation/updates since the path is outside the project directory. This is essential for Claude Code's workflow.

### 4. `allowedExternalReadPaths` Left Empty

**Decision: Empty array (user must configure)**

The user's production config has 6 project-specific paths. These are inherently user-specific and cannot be generalized. Leaving this empty with the root `$comment` explaining customization is the right approach.

### 5. New Bash Patterns Added

**From Gemini's suggestions (incorporated):**
- **Block: `netcat/nc` reverse shell** - `(?i)(?:nc|netcat|ncat)\s.*(?:-e\s|\s/bin/(?:ba)?sh|\s/bin/bash)` - AI agents should never create reverse shells
- **Block: base64 obfuscation** - `(?i)base64\s+-d.*\|\s*(?:bash|sh|zsh)` - Common prompt injection vector
- **Block: `mkfs`** - `(?i)mkfs\.` - Filesystem formatting
- **Block: `dd` to device** - `dd\s+.*of=/dev/[a-z]` - Raw disk overwrite
- **Ask: `npm publish`** - Package publishing (supply chain risk)
- **Ask: `twine upload`** - PyPI publishing
- **Ask: `cargo publish`** - Crates.io publishing
- **Ask: `gem push`** - RubyGems publishing
- **Ask: `docker system prune`** - Docker cleanup
- **Ask: `terraform apply/destroy`** - Infrastructure changes
- **Ask: `kubectl delete`** - Kubernetes resource deletion
- **Ask: `chmod 777`** - Overly permissive permissions
- **Ask: `sudo`** - Privilege escalation

**From Gemini's suggestions (NOT incorporated):**
- **Cryptocurrency mining patterns** (`xmrig`, `cgminer`) - Too niche, low probability in a coding assistant context. Would add pattern complexity for minimal value.
- **History clearing** (`history -c`) - Not a realistic attack vector in Claude Code's hook context (bash commands are single-shot, not persistent sessions).
- **Credential exfiltration via curl POST** (`curl -X POST -d @secrets.json`) - This is already mitigated by zeroAccessPaths blocking read access to secret files. Adding a bash pattern would be defense-in-depth but the pattern is fragile (many ways to bypass with encoding/aliases).
- **`terraform destroy -auto-approve`** as block - Too aggressive for a recommended config. The ask pattern for `terraform apply/destroy` already covers this. Users who run Terraform interactively would be frustrated by a hard block.
- **Publishing with `--token` as block** - Too fragile. The ask pattern for generic publish commands is sufficient.

### 6. `~/.npmrc` and `~/.pypirc` Added to zeroAccessPaths

**Decision: Add both**

These files contain authentication tokens for npm and PyPI respectively. Gemini correctly flagged these as credential files that should be protected. They are outside the project but can be accessed if a path traversal or absolute path is used in commands.

### 7. `bashPathScan` Configuration

**Decision: Keep default settings (scanTiers: ["zeroAccess"] only)**

Scanning all three tiers (zeroAccess + readOnly + noDelete) in bash commands would be too noisy for a recommended config. Many legitimate bash commands reference read-only or no-delete files (e.g., `cat package-lock.json`, `head README.md`). Scanning only zeroAccess tier keeps the signal-to-noise ratio high.

### 8. `includeUntracked: false` (Safety Default)

**Decision: Keep false**

This is a critical safety default. When `true`, auto-commit would stage and commit untracked files, which could include newly-created secret files, temporary credentials, or other sensitive content. The user's production config already uses `false`.

### 9. Version: 1.0.0

As instructed. This is the first release of the recommended config.

## What Changed vs User's Production Config

| Aspect | User Config | Recommended Config | Reason |
|--------|------------|-------------------|--------|
| Version | 1.2.0 | 1.0.0 | First release |
| `.env` patterns | 24 explicit entries | 4 glob patterns | Simpler, more comprehensive |
| `.mcp.json` | Present | Present | Kept (Claude Code specific) |
| `~/.npmrc`, `~/.pypirc` | Not present | Added | Credential protection |
| `allowedExternalReadPaths` | 6 project-specific paths | Empty | User-specific, cannot generalize |
| `allowedExternalWritePaths` | `~/.claude/plans/**` | `~/.claude/plans/**` | Kept (Claude Code specific) |
| Block patterns | 17 | 22 | Added reverse shell, obfuscation, mkfs, dd |
| Ask patterns | 16 | 27 | Added publish, docker, terraform, kubectl, chmod, sudo |
| `find -exec` in ask | Not present | Present | From default config |
| `xargs rm` in ask | Not present | Present | From default config |

## What Changed vs Default Config

| Aspect | Default Config | Recommended Config | Reason |
|--------|---------------|-------------------|--------|
| `$comment` | Minimal | Comprehensive | Beginner-friendly |
| `.mcp.json` in zeroAccess | Not present | Added | Claude Code specific |
| `~/.npmrc`, `~/.pypirc` | Not present | Added | Credential protection |
| `allowedExternalWritePaths` | Empty | `~/.claude/plans/**` | Claude Code plan mode |
| Block patterns | 18 | 22 | Added 4 new patterns |
| Ask patterns | 18 | 27 | Added 9 new patterns |

## External Model Consultation Summary

### Gemini 3.1 Pro
Strong suggestions that were incorporated:
- Reverse shell detection (netcat, /dev/tcp)
- Base64 obfuscation detection
- Package publishing as ask patterns
- Docker/Terraform/Kubernetes as ask patterns
- `~/.npmrc` and `~/.pypirc` as zero-access paths
- `chmod 777` and `sudo` as ask patterns
- `mkfs` and `dd` as block patterns

Suggestions not incorporated (with reasoning above):
- Cryptocurrency mining patterns (too niche)
- History clearing (not applicable)
- Curl POST exfiltration (already mitigated by path protection)
- `terraform destroy -auto-approve` as hard block (too aggressive)

### Codex (unavailable - quota exceeded)
Could not consult due to API rate limits.
