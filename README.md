# claude-code-guardian

Security guardrails for Claude Code. Protects against destructive commands, unauthorized file access, and provides auto-commit safety nets.

## Features

- **Bash Command Protection**: Block dangerous shell commands (rm -rf /, force push, fork bombs) and prompt for confirmation on risky operations (git reset --hard, branch deletion)
- **File Access Control**: Zero-access paths for secrets (.env, .pem, SSH keys), read-only paths for lock files, no-delete protection for critical project files
- **Auto-Commit Safety Net**: Automatically commits changes when Claude Code sessions end, creating checkpoints you can always roll back to
- **Pre-Danger Checkpoints**: Creates a commit before any destructive operation so you can recover if something goes wrong
- **Configurable Rules**: JSON-based configuration with full JSON Schema validation

## Installation

### From Marketplace

```bash
# Add the agntpod-security marketplace
/plugin marketplace add agntpod/claude-code-guardian

# Install the plugin
/plugin install claude-code-guardian@agntpod-security
```

### Manual Installation

```bash
# Clone the repo
git clone https://github.com/agntpod/claude-code-guardian

# Point Claude Code to the plugin directory
claude --plugin-dir /path/to/claude-code-guardian
```

## Setup

After installation, run the setup wizard:

```
/guardian:init
```

This generates a `protection.json` configuration file in your project with sensible defaults. You can customize it for your project's needs.

> If you skip setup, Guardian uses built-in defaults that protect common secret files (.env, *.pem, *.key) and block destructive commands. Run `/guardian:init` anytime to customize for your project.

## Configuration

The plugin uses a `protection.json` file for all settings. The configuration is looked up in this order:

1. `$CLAUDE_PROJECT_DIR/.claude/guardian/protection.json` (project-specific)
2. Plugin default (`assets/protection.default.json`) as fallback

If neither is found, a hardcoded minimal protection set activates as an emergency fallback.

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

See `assets/protection.schema.json` for the full schema.

## How It Works

Guardian registers four hooks with Claude Code:

| Hook | Event | Script |
|------|-------|--------|
| Bash Protection | PreToolUse: Bash | Checks commands against block/ask patterns |
| Edit Protection | PreToolUse: Edit | Validates file paths against access rules |
| Write Protection | PreToolUse: Write | Validates file paths against access rules |
| Auto-Commit | Stop | Commits pending changes as a checkpoint |

All hooks are **fail-closed**: if something goes wrong (timeout, error), the default behavior is to **deny** the operation rather than allow it through.

## Requirements

- Python 3.10 or later
- Git (for auto-commit features)

## License

MIT
