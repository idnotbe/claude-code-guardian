---
name: Guardian Config Guide
description: Helps users understand and modify their Guardian security configuration through natural language
---

# Guardian Configuration Guide

This skill manages the Guardian `config.json` security configuration. It translates natural language requests into precise JSON modifications, validates changes against the schema, and warns about security implications.

## When This Skill Applies

This skill activates when the user wants to:
- Add, remove, or modify blocked or ask-confirmed bash command patterns
- Protect or unprotect files and directories (zero-access, read-only, no-delete)
- Change git auto-commit behavior, identity, or pre-danger checkpoints
- Understand why a command was blocked or a file access was denied
- Review their current Guardian configuration
- Troubleshoot Guardian behavior

## Config Location

Find the user's config by checking these paths in order:
1. `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` (project-specific config)
2. `${CLAUDE_PLUGIN_ROOT}/assets/guardian.default.json` (plugin default fallback)

If neither exists, a hardcoded minimal guardian fallback is active.

The JSON schema is at `${CLAUDE_PLUGIN_ROOT}/assets/guardian.schema.json`.

## Core Operations

### 1. Block a Command

When the user says things like "block npm publish" or "prevent force push":

1. Read the current config
2. Determine the appropriate regex pattern for the command
3. Ask the user whether it should be **block** (silent deny) or **ask** (confirm before running)
4. Add the pattern to the correct array in `bashToolPatterns`
5. Always include a clear `reason` field

**Example interaction:**
- User: "block npm publish"
- Action: Add `{"pattern": "npm\\s+publish", "reason": "Publishing to npm registry"}` to `bashToolPatterns.block`
- Confirm: "Added. `npm publish` will now be silently blocked. Want it as an ask-confirm instead?"

### 2. Protect a Path

When the user says things like "protect .env.production" or "make migrations read-only":

1. Determine the guarding level from context:
   - **Zero access** -- secrets, credentials, keys (cannot read or write)
   - **Read only** -- lock files, build output, vendor dirs (can read, cannot write)
   - **No delete** -- critical configs, CI files, migrations (can read and write, cannot delete)
2. Add the glob pattern to the correct array
3. Warn if removing guarding from a sensitive path

**Common path patterns:**
- Single file: `config/secrets.yaml`
- File type: `*.pem`
- Dot-prefixed variants: `.env.*`
- Recursive directory: `migrations/**`
- Home directory: `~/.aws/**`

### 3. Unblock or Unprotect

When the user says "allow rm -rf" or "unprotect build/":

1. Find the matching entry in the config
2. **Warn about security implications** before removing
3. Suggest alternatives when possible (e.g., move from `block` to `ask` instead of removing entirely)
4. Apply only after explicit confirmation

### 4. Configure Git Integration

When the user says "disable auto-commit" or "change commit message prefix":

| User says | Field to modify |
|-----------|----------------|
| "disable auto-commit" | `gitIntegration.autoCommit.enabled` -> `false` |
| "enable auto-commit" | `gitIntegration.autoCommit.enabled` -> `true` |
| "include untracked files" | `gitIntegration.autoCommit.includeUntracked` -> `true` |
| "change commit prefix to X" | `gitIntegration.autoCommit.messagePrefix` -> `"X"` |
| "disable pre-danger commits" | `gitIntegration.preCommitOnDangerous.enabled` -> `false` |
| "change git identity" | `gitIntegration.identity.email` and/or `identity.name` |

### 5. Review Config

When the user says "show guardian config" or "what's protected":

Read the config and present a human-readable summary organized by section. Do not dump raw JSON unless the user asks for it. Use the format from the init command's summary.

### 6. Troubleshoot

When the user says "why was X blocked" or "guardian blocked my command":

1. Read the config
2. Check `bashToolPatterns.block` and `bashToolPatterns.ask` for matching patterns
3. Check path guarding arrays if it was a file operation
4. Explain which rule matched and why it exists
5. Offer to modify the rule if the user needs it changed

## Safety Rules

- **Never remove all entries** from `zeroAccessPaths` -- there must always be secret guarding
- **Warn before weakening rules** -- explain what becomes possible when a rule is removed
- **Suggest `ask` before `remove`** -- if a user wants to unblock something dangerous, suggest moving from `block` to `ask` first
- **Validate all regex patterns** -- ensure they compile and do not have obvious false-positive issues
- **Validate against schema** after every modification using the schema at `${CLAUDE_PLUGIN_ROOT}/assets/guardian.schema.json`
- **Preserve existing rules** -- when adding new patterns, append to arrays, do not replace them

## Writing Regex Patterns

When creating bash patterns for users:
- Use `(?i)` prefix for case-insensitive matching
- Use `\\s+` for whitespace between command parts
- Use `(?:...|...)` for alternatives
- Anchor to command name, not start of line (commands may have prefixes)
- Keep patterns specific to avoid false positives
- Always test mentally: does this pattern match the intended command AND avoid matching safe commands?

## Reference

See `references/schema-reference.md` for complete field documentation, glob syntax, and a regex pattern cookbook.
