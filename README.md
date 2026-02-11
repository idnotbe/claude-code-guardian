# claude-code-guardian

Selective security guardrails for Claude Code's `--dangerously-skip-permissions` mode. Speed by default, intervention by exception.

## Why Guardian?

`--dangerously-skip-permissions` is all-or-nothing. You either approve every single operation manually, or you approve none of them. Most power users choose none -- because stopping to confirm every file write kills the workflow.

The problem: permissionless mode doesn't distinguish between writing a component file and running `rm -rf /`. Everything gets the same silent green light.

Guardian gives you back the guardrails that actually matter. It hooks into Claude Code's plugin system to intercept operations before they execute. The 99% of safe operations run silently. The 1% that could ruin your day -- destructive shell commands, secret file access, force pushes -- get caught and require your explicit approval.

You keep the speed. You lose the existential dread.

## What It Catches

**Safety checkpoints** (automatic):
- Auto-commits pending changes when a Claude Code session ends
- Creates a commit before any destructive operation, so you can always roll back
- Your work is never more than one `git reset` away from recovery

**Hard blocks** (always denied):
- `rm -rf /`, fork bombs, and other catastrophic shell commands
- Reading `.env`, `.pem`, SSH keys, and other secret files
- Writing to protected paths outside your project
- `git push --force` and `--force-with-lease` (configure to allow if needed)

**Confirmation prompts** (asks before proceeding):
- `git reset --hard`, branch deletion
- Other risky-but-sometimes-intentional operations

**Protected files** (access controls):
- Zero-access paths for secrets (cannot be read or written)
- Read-only paths for lock files and generated configs
- No-delete paths for critical project files

Default patterns cover both Unix and Windows commands.

## Installation

### Manual Installation

```bash
git clone https://github.com/idnotbe/claude-code-guardian
claude --plugin-dir /path/to/claude-code-guardian
```

> **Persistence**: The `--plugin-dir` flag applies to a single session. To load Guardian automatically, add it to your shell profile or Claude Code settings.

To update, run `git pull` in the cloned directory.

### From Marketplace

> Marketplace integration is currently experimental. Manual installation is the reliable path.

```bash
/plugin marketplace add idnotbe/claude-code-guardian
/plugin install claude-code-guardian@idnotbe-security
```

## Setup

After installation, run the setup wizard:

```
/guardian:init
```

This generates a `config.json` configuration file in your project with sensible defaults. Customize it for your project's needs.

> If you skip setup, Guardian uses built-in defaults that protect common secret files (.env, *.pem, *.key) and block destructive commands. Run `/guardian:init` anytime to customize.

## Configuration

Guardian uses a `config.json` file for all settings, resolved in this order:

1. `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` (project-specific)
2. Plugin default (`assets/guardian.default.json`) as fallback

If neither is found, a hardcoded minimal guardian ruleset activates as an emergency fallback.

### Example

The following shows a partial custom configuration. See `assets/guardian.default.json` for the complete config with all required fields.

```json
{
  "bashToolPatterns": {
    "block": [
      {"pattern": "rm\\s+-rf\\s+/", "reason": "Root deletion"},
      {"pattern": "mkfs\\.", "reason": "Filesystem format"}
    ],
    "ask": [
      {"pattern": "git\\s+reset\\s+--hard", "reason": "Hard reset"}
    ]
  },
  "zeroAccessPaths": [".env", "*.pem"],
  "readOnlyPaths": ["**/package-lock.json"],
  "noDeletePaths": ["README.md", "LICENSE"]
}
```

### Configuration Sections

| Section | Purpose |
|---------|---------|
| `hookBehavior` | What to do on timeout or error (allow/deny/ask) |
| `bashToolPatterns.block` | Regex patterns always blocked |
| `bashToolPatterns.ask` | Regex patterns requiring confirmation |
| `zeroAccessPaths` | Glob patterns for files that cannot be read or written |
| `readOnlyPaths` | Glob patterns for read-only files |
| `noDeletePaths` | Glob patterns for files that cannot be deleted |
| `allowedExternalPaths` | Paths outside the project allowed for writes |
| `gitIntegration` | Auto-commit and git identity settings |

See `assets/guardian.schema.json` for the full schema.

## How It Works

Guardian registers four hooks with Claude Code:

| Hook | Event | Script |
|------|-------|--------|
| Bash Guardian | PreToolUse: Bash | Checks commands against block/ask patterns |
| Edit Guardian | PreToolUse: Edit | Validates file paths against access rules |
| Write Guardian | PreToolUse: Write | Validates file paths against access rules |
| Auto-Commit | Stop | Commits pending changes as a checkpoint |

All security hooks (Bash, Edit, Write) are **fail-closed**: if a hook times out or errors, the operation is **denied** rather than allowed through. A false denial is annoying; a false allow could be catastrophic. The Auto-Commit hook is fail-open by design -- a commit failure must never block session termination.

> **Important**: If Guardian fails to load while `--dangerously-skip-permissions` is active, you have zero protection. Verify hooks are loaded at the start of your session by attempting to read a `.env` file -- Guardian should block the operation. If it doesn't, hooks are not active. See [Failure Modes](#failure-modes) for details.

### How "ask" works in permissionless mode

Claude Code's hook system can still prompt for user confirmation even when `--dangerously-skip-permissions` is active. Hooks operate at a layer above the permission bypass -- this is the architectural foundation Guardian relies on.

## Failure Modes

**If Guardian fails to load** while you're running `--dangerously-skip-permissions`, you have **zero protection**. No hooks means no interception -- every operation executes silently, exactly as if Guardian wasn't installed.

This is the inherent trade-off of hook-based interception: it only works when it's loaded. Before starting a permissionless session, verify Guardian is active and hooks are registered.

**Does not protect against:**
- Determined human adversaries crafting bypass commands
- Shell commands inside Python scripts (e.g., `subprocess.run()`) -- only direct Bash tool calls are intercepted
- Operations run in a separate terminal or process outside Claude Code
- Its own failure to load or initialize

**Does protect against:**
- Accidental file deletion and destructive shell commands
- Secret file exposure (.env, credentials, private keys)
- Force pushes and other irreversible git operations
- Loss of work (via auto-commit checkpoints)

Use Guardian alongside git backups, CI/CD checks, and standard access controls -- not instead of them.

### Disabling Guardian

To temporarily disable Guardian, remove the `--plugin-dir` flag from your launch command. To uninstall, delete the cloned repository and remove any references from your Claude Code settings. If you ran `/guardian:init`, also remove the `.claude/guardian/` directory from your project.

## Requirements

- Python 3.10 or later
- Git (for auto-commit features)

## License

MIT
