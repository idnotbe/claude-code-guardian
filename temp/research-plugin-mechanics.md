# Research: Plugin Mechanics for Config Onboarding

## Plugin Installation and Lifecycle

### Installation Flow
When a user runs `claude plugins install`, Claude Code:
1. Downloads/clones the plugin repository
2. Reads `.claude-plugin/plugin.json` manifest
3. Auto-discovers components: commands, agents, skills, hooks
4. Registers hooks from `hooks/hooks.json`
5. Plugin becomes active on next session start

### Component Discovery (Auto)
- **Commands**: All `.md` files in `commands/` load automatically -> Guardian has `/guardian:init`
- **Agents**: All `.md` files in `agents/` load automatically -> Guardian has `config-assistant`
- **Skills**: All `SKILL.md` files in skill subdirectories -> Guardian has `config-guide`
- **Hooks**: Loaded from `hooks/hooks.json` -> Guardian has PreToolUse (Bash/Read/Edit/Write) + Stop hooks

### Current Guardian Plugin Structure
```
claude-code-guardian/
├── .claude-plugin/plugin.json    # Manifest
├── commands/init.md              # /guardian:init wizard
├── agents/config-assistant.md    # Config modification agent
├── skills/config-guide/SKILL.md  # Auto-activating config skill
├── hooks/hooks.json              # Security hooks (PreToolUse + Stop)
└── assets/
    ├── guardian.default.json     # Default config template
    └── guardian.schema.json      # JSON schema
```

## SessionStart Hook Capability

### Key Finding: SessionStart is available and perfect for first-run detection

**What SessionStart can do:**
- Runs when Claude Code starts a NEW session (`matcher: "startup"`)
- Also runs on resume, clear, and compact events
- Can execute shell commands (`type: "command"` only)
- **Stdout is added as context that Claude can see and act on** (unlike most hooks)
- Can persist environment variables via `$CLAUDE_ENV_FILE`
- Has access to `$CLAUDE_PROJECT_DIR` and `$CLAUDE_PLUGIN_ROOT`

**What SessionStart CANNOT do:**
- Cannot block session start (exit code 2 only shows stderr to user)
- Cannot use prompt-based or agent-based hooks (command only)
- Should be kept fast (runs on every session)

### First-Run Detection Strategy

A SessionStart hook can:
1. Check if `.claude/guardian/config.json` exists in the project
2. If missing, print a helpful message to stdout (which Claude sees as context)
3. Claude then naturally suggests running `/guardian:init` or offers guidance

**Example hook script:**
```bash
#!/bin/bash
CONFIG_PATH="$CLAUDE_PROJECT_DIR/.claude/guardian/config.json"

if [ ! -f "$CONFIG_PATH" ]; then
  echo "Guardian is installed but no config.json found for this project."
  echo "Run /guardian:init to set up security guardrails, or say 'help me configure guardian'."
  echo "Without a config, Guardian uses built-in minimal defaults."
fi
exit 0
```

### Environment Variable Persistence
SessionStart hooks can write to `$CLAUDE_ENV_FILE`:
```bash
echo "export GUARDIAN_CONFIG_STATUS=missing" >> "$CLAUDE_ENV_FILE"
```
This would be available in all subsequent Bash commands.

## Hook Events Currently Used by Guardian

| Event | Matcher | Purpose |
|-------|---------|---------|
| PreToolUse | Bash | Command interception (bash_guardian.py) |
| PreToolUse | Read | File read guarding (read_guardian.py) |
| PreToolUse | Edit | File edit guarding (edit_guardian.py) |
| PreToolUse | Write | File write guarding (write_guardian.py) |
| Stop | * | Auto-commit checkpoint (auto_commit.py) |

### Gap: No SessionStart hook is currently configured

This is the key finding -- Guardian currently has NO SessionStart hook. Adding one for first-run detection would be straightforward and non-breaking.

## Plugin Manifest Capabilities

The `plugin.json` manifest supports:
- `commands`: Custom paths for slash commands (supplements default `commands/`)
- `agents`: Custom paths for agents (supplements default `agents/`)
- `hooks`: Custom path for hooks.json
- `mcpServers`: MCP server definitions
- `skills`: Custom paths for skills

**No automatic file copying mechanism exists.** Plugins cannot auto-copy files to the user's project during installation. Any config file creation must happen through:
1. A command that the user explicitly runs
2. A hook script that creates files (with appropriate user awareness)
3. Claude naturally offering to create the file based on SessionStart context

## Other Notable Plugin Capabilities

### Skill Auto-Activation
Skills activate automatically based on task context matching the description. The `config-guide` skill already does this -- when users discuss guardian settings, it activates.

### Agent Triggering
The `config-assistant` agent has a `trigger` field that describes when it should activate. This happens automatically when users discuss relevant topics.

### Command Invocation
Commands are available as slash commands. `/guardian:init` is already available after plugin install.

## Summary of Key Findings

1. **SessionStart hook is the missing piece** -- can detect config absence and inject context for Claude
2. **No auto-copy mechanism** -- plugins cannot silently install config files
3. **The existing trinity (command + skill + agent) is solid** but lacks discoverability
4. **Stdout from SessionStart becomes Claude's context** -- this is the key enabler for proactive onboarding
5. **Hook must be fast** since it runs on every session start
6. **Config checking script is trivial to implement** -- just a file existence check
