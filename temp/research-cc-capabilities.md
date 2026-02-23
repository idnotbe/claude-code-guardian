# Research: Claude Code Capabilities for Plugin Onboarding

## User Journey: Plugin Install to First Use

### Step 1: Discovery
- User finds plugin (GitHub, marketplace, recommendation)
- Reads description: "Security guardrails for Claude Code's --dangerously-skip-permissions mode"

### Step 2: Installation
```
claude plugins install <source>
```
- Claude Code downloads plugin
- Reads `.claude-plugin/plugin.json`
- Registers all components (commands, agents, skills, hooks)
- Plugin is now active

### Step 3: First Session After Install
- Claude Code starts
- **If SessionStart hook exists**: hook runs, can print context
- PreToolUse hooks are active (Bash, Read, Edit, Write guardians)
- Stop hook active (auto-commit)
- `/guardian:init` command available
- `config-guide` skill ready to auto-activate
- `config-assistant` agent ready to trigger

### Step 4: First Interaction
- User says something
- If related to guardian/security, `config-assistant` agent may trigger
- If user runs a blocked command, guardian hooks intercept
- User may discover `/guardian:init` through help or documentation

### Key Gap: Between Step 3 and Step 4
The user has NO proactive indication that:
1. Guardian needs configuration
2. `/guardian:init` exists
3. There are defaults in effect
4. They should customize anything

## What Claude Code Commands Can Do

Commands (`.md` files in `commands/`) are:
- User-invocable via slash (e.g., `/guardian:init`)
- Markdown-based with YAML frontmatter
- Full access to Claude's capabilities (tools, reasoning)
- Can read/write files, run scripts, interact with user

**Limitations:**
- Must be explicitly invoked by user (no auto-run)
- No "post-install" hook to auto-run a command
- Namespace prefixed with plugin name

## What Claude Code Skills Can Do

Skills (`SKILL.md` files in skill directories) are:
- Auto-activated by Claude based on task context
- Provide guidance and capabilities for specific domains
- Can include reference materials, scripts, examples

**Strengths for onboarding:**
- Activate when user discusses related topics
- Can provide step-by-step guidance
- Work naturally in conversation

**Limitations:**
- Only activate when context matches description
- Cannot self-activate on first session
- User must be discussing a relevant topic

## What Claude Code Agents Can Do

Agents (`.md` files in `agents/`) are:
- Specialized subagent definitions
- Have defined triggers and tool access
- Can be manually or automatically invoked

**Strengths for onboarding:**
- Can guide complex configuration interactively
- Have specialized knowledge
- Tool access (Read, Write, Edit, Glob, Grep)

**Limitations:**
- Triggered by conversation context, not session state
- Cannot auto-invoke on first run

## What SessionStart Hooks Can Do

**This is the key capability for onboarding:**

1. **File existence check**: Check if config exists
2. **Context injection**: Print message to stdout -> becomes Claude's context
3. **Environment setup**: Write to `$CLAUDE_ENV_FILE`
4. **Silent operation**: Can exit 0 with no output when config exists

### SessionStart + Context Injection Pattern

When a SessionStart hook prints to stdout, that text becomes context for Claude. This means:
- Claude "knows" the config status before the user says anything
- Claude can proactively suggest setup
- Claude can reference the config status in its responses

**This is exactly how other plugins use it:**
- `explanatory-output-style`: Injects teaching context
- `learning-output-style`: Injects learning mode context

## Can We Detect First Run?

### Method 1: Config File Existence (Recommended)
```bash
if [ ! -f "$CLAUDE_PROJECT_DIR/.claude/guardian/config.json" ]; then
  echo "[Guardian] No project config found. Using minimal built-in defaults."
  echo "Run /guardian:init to set up project-specific security rules."
fi
```
**Pro**: Simple, reliable, fast
**Con**: Runs every session until config exists (but this is desirable)

### Method 2: Marker File
```bash
MARKER="$CLAUDE_PROJECT_DIR/.claude/guardian/.initialized"
if [ ! -f "$MARKER" ]; then
  echo "First time using Guardian in this project..."
  # Could touch marker after first notification
fi
```
**Pro**: Only shows message once
**Con**: Extra file to manage, user might want ongoing reminder

### Method 3: Environment Variable
```bash
if [ ! -f "$CONFIG" ]; then
  echo 'export GUARDIAN_NEEDS_SETUP=true' >> "$CLAUDE_ENV_FILE"
fi
```
**Pro**: Available to all subsequent commands
**Con**: More complex, less direct

**Recommendation**: Method 1 is simplest and most appropriate. The message should appear every session until the user either creates a config or explicitly dismisses it.

## Can We Auto-Copy Files?

### Direct File Copy in SessionStart
```bash
if [ ! -f "$CONFIG" ]; then
  mkdir -p "$(dirname "$CONFIG")"
  cp "$CLAUDE_PLUGIN_ROOT/assets/guardian.default.json" "$CONFIG"
  echo "[Guardian] Created default config at $CONFIG"
fi
```

**Possible but NOT recommended because:**
1. User has no awareness of what was configured
2. Default config may not fit project (e.g., wrong language patterns)
3. Silent file creation in user's project is surprising
4. Better to let the init wizard detect and customize

### Recommended Alternative: Copy-Ready Templates
Instead of auto-copying, make it easy to copy manually:
```bash
echo "To use the recommended config:"
echo "  cp $CLAUDE_PLUGIN_ROOT/assets/guardian.recommended.json .claude/guardian/config.json"
```

## Complete Onboarding Capability Map

| Capability | Available | Mechanism |
|-----------|-----------|-----------|
| Detect first run | YES | SessionStart hook + file check |
| Inject context for Claude | YES | SessionStart stdout |
| Auto-run wizard | NO | Commands must be user-invoked |
| Auto-create config | YES (but not recommended) | SessionStart hook script |
| Guide user interactively | YES | /guardian:init command |
| Auto-activate on config discussion | YES | config-guide skill |
| Help with config modifications | YES | config-assistant agent |
| Provide copy-ready templates | YES | Ship template files in assets/ |
| Show config status | YES | SessionStart hook |
| Persist state between sessions | YES | $CLAUDE_ENV_FILE or marker files |

## Recommended Architecture for Onboarding

```
SessionStart hook (first-run detection)
    ├── Config exists -> silent (exit 0, no output)
    └── Config missing -> inject context message
        ├── User says "set it up" -> /guardian:init wizard runs
        ├── User says "use defaults" -> quick copy of recommended config
        ├── User says "show options" -> config-guide skill activates
        └── User ignores -> minimal defaults protect them anyway
```

This creates a natural, non-intrusive onboarding flow that:
1. Works without any config (fail-safe defaults)
2. Proactively informs users about setup
3. Offers multiple paths based on user preference
4. Leverages existing components (init, skill, agent)
