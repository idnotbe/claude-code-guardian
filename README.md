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
- Archives untracked files to `_archive/` before deletion, so nothing is permanently lost without a copy
- Your work is never more than one `git reset` away from recovery

**Hard blocks** (always denied):
- `rm -rf /`, fork bombs, and other catastrophic shell commands
- Reading `.env`, `.pem`, SSH keys, and other secret files
- Writing to protected paths outside your project
- `git push --force` (configure to allow if needed)

**Confirmation prompts** (asks before proceeding):
- `git push --force-with-lease`
- `git reset --hard`, branch deletion
- Other risky-but-sometimes-intentional operations

**Protected files** (access controls):
- Zero-access paths for secrets (cannot be read or written)
- Read-only paths for lock files and generated configs
- No-delete paths for critical project files

Default patterns cover both Unix and Windows commands.

## Installation

### Manual Installation

> **Requires Python 3.10+** and Git. Verify with `python3 --version` and `git --version` before installing.

```bash
git clone https://github.com/idnotbe/claude-code-guardian
claude --plugin-dir /path/to/claude-code-guardian
```

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

## Setup

After installation, run the setup wizard:

```
/guardian:init
```

This generates a `config.json` configuration file in your project with built-in defaults. Customize it for your project's needs.

> If you skip setup, Guardian uses built-in defaults that protect common secret files (.env, *.pem, *.key) and block destructive commands. Run `/guardian:init` anytime to customize.

> **Tip**: To test your configuration without blocking operations, use dry-run mode: `CLAUDE_HOOK_DRY_RUN=1`. See [Disabling Guardian](#disabling-guardian) for details.

## Configuration

Guardian uses a `config.json` file for all settings, resolved in this order:

1. `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` (project-specific)
2. Plugin default (`assets/guardian.default.json`) as fallback

If neither is found, a hardcoded minimal guardian ruleset activates as an emergency fallback.

### Example

> **Note**: The example below is a partial configuration showing only custom patterns. A valid config file **must** also include `version` and `hookBehavior`. Copy `assets/guardian.default.json` as your starting point and modify from there.

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
| `version` | Config version (semver, required) |
| `hookBehavior` | Timeout and error handling: what to do on hook timeout or error (`allow`/`deny`/`ask`), and `timeoutSeconds` for hook execution limit |
| `bashToolPatterns.block` | Regex patterns always blocked |
| `bashToolPatterns.ask` | Regex patterns requiring confirmation |
| `zeroAccessPaths` | Glob patterns for files that cannot be read or written |
| `readOnlyPaths` | Glob patterns for read-only files |
| `noDeletePaths` | Glob patterns for files that cannot be deleted |
| `allowedExternalPaths` | Paths outside the project allowed for writes |
| `gitIntegration` | Auto-commit and git identity settings |
| `bashPathScan` | Scans bash commands for references to protected path names (e.g., catches `python3 script.py --file .env`). Supports `scanTiers` to control which path types to scan for |

See `assets/guardian.schema.json` for the full schema.

## How It Works

Guardian registers five hooks with Claude Code:

| Hook | Event | Script |
|------|-------|--------|
| Bash Guardian | PreToolUse: Bash | Checks commands against block/ask patterns |
| Read Guardian | PreToolUse: Read | Blocks reading secret files and paths outside project |
| Edit Guardian | PreToolUse: Edit | Validates file paths against access rules |
| Write Guardian | PreToolUse: Write | Validates file paths against access rules |
| Auto-Commit | Stop | Commits pending changes as a checkpoint |

All security hooks (Bash, Read, Edit, Write) are **fail-closed**: if a hook times out or errors, the operation is **denied** rather than allowed through. A false denial is annoying; a false allow could be catastrophic. The Auto-Commit hook is fail-open by design -- a commit failure must never block session termination.

Guardian also protects its own configuration file (`.claude/guardian/config.json`) from being modified by the AI agent.

> **Important**: If Guardian fails to load while `--dangerously-skip-permissions` is active, you have zero protection. Verify hooks are loaded at the start of your session by running a blocked command -- for example, ask Claude to `cat .env` (even if the file doesn't exist, Guardian should block the attempt). If it doesn't, hooks are not active. See [Failure Modes](#failure-modes) for details.

### How "ask" works in permissionless mode

Claude Code's hook system can still prompt for user confirmation even when `--dangerously-skip-permissions` is active. Hooks operate at a layer above the permission bypass -- this is the architectural foundation Guardian relies on.

## Failure Modes

**If Guardian fails to load** while you're running `--dangerously-skip-permissions`, you have **zero protection**. No hooks means no interception -- every operation executes silently, exactly as if Guardian wasn't installed.

This is the inherent trade-off of hook-based interception: it only works when it's loaded. Before starting a permissionless session, verify Guardian is active and hooks are registered.

**Does not protect against:**
- Determined human adversaries crafting bypass commands
- Arbitrary code within interpreter scripts (Guardian blocks known deletion APIs like `os.remove` and `shutil.rmtree` at the Bash command level, but cannot catch all possible code patterns)
- Operations run in a separate terminal or process outside Claude Code
- Its own failure to load or initialize

**Does protect against:**
- Accidental file deletion and destructive shell commands
- Secret file exposure (.env, credentials, private keys)
- Force pushes and other irreversible git operations
- Loss of work (via auto-commit checkpoints)

Use Guardian alongside git backups, CI/CD checks, and standard access controls -- not instead of them.

**Circuit breaker**: If auto-commit fails repeatedly, Guardian stops attempting auto-commits to prevent cascading failures. The circuit breaker auto-resets after one hour. To manually reset, delete `.claude/guardian/.circuit_open`.

### Troubleshooting

**Log file location**: Guardian logs to `.claude/guardian/guardian.log` (inside your project directory). Check this file for detailed information about hook decisions, blocked operations, and errors.

**Checking if hooks are loaded**: At the start of your session, run a known-blocked command like `cat .env` (the file does not need to exist -- Guardian intercepts the command before it executes). If Guardian is active, the operation will be blocked. If it succeeds silently, hooks are not loaded.

**Common issues**:

| Problem | Cause | Solution |
|---------|-------|----------|
| Hooks not firing | `--plugin-dir` not set or wrong path | Verify path: `claude --plugin-dir /path/to/claude-code-guardian` |
| `python3: command not found` | Python 3.10+ not installed or not on PATH | Install Python 3.10+ and ensure `python3` is available |
| Config not loading | Syntax error in `config.json` | Validate against schema: compare with `assets/guardian.default.json` |
| Auto-commits stopped | Circuit breaker tripped after failures | Delete `.claude/guardian/.circuit_open` or wait 1 hour for auto-reset |
| Unexpected blocks | Custom config too restrictive | Use dry-run mode to debug: `CLAUDE_HOOK_DRY_RUN=1` (see below) |

### Disabling Guardian

To test Guardian without blocking, set `CLAUDE_HOOK_DRY_RUN=1` in your environment. Hooks will log what they would do without actually blocking operations. This is useful for testing configuration changes or debugging unexpected blocks.

```bash
CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/claude-code-guardian
```

To temporarily disable Guardian, remove the `--plugin-dir` flag from your launch command. To uninstall, delete the cloned repository and remove any references from your Claude Code settings. If you ran `/guardian:init`, also remove the `.claude/guardian/` directory from your project.

## Testing

The test suite covers bash_guardian.py and _guardian_utils.py extensively, with ~1,009 test methods across 6 category directories.

```bash
# Run core and security tests (unittest-based, pytest-compatible)
python -m pytest tests/core/ tests/security/ -v

# Run a single test file directly
python3 tests/core/test_p0p1_comprehensive.py
```

See `tests/README.md` for detailed test documentation including directory structure, category boundaries, and how to add new tests.

**Known coverage gaps**: `edit_guardian.py`, `read_guardian.py`, `write_guardian.py`, and `auto_commit.py` currently have no automated tests. See `TEST-PLAN.md` for the prioritized action plan.

## Requirements

- Python 3.10 or later
- Git (for auto-commit features)

## License

MIT
