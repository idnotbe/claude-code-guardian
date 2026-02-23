# Team 1 Context: Default Config Example Creation

## Objective
Create a practical, opinionated default config example (`assets/guardian.recommended.json`) that new users can use out of the box or as a starting point.

## Key Inputs

### User's Real Config (reference - at /home/idnotbe/projects/ops/.claude/guardian/config.json)
This is the production config used by the plugin author. Key patterns to extract:
- Claude Code-specific paths: `~/.claude/plans` and `~/.claude/plans/**` in allowedExternalWritePaths
- `.mcp.json` and `.mcp.json.bak` in zeroAccessPaths (Claude Code MCP config files contain secrets)
- Comprehensive .env variants (not just `.env.*` glob but explicit entries for common naming patterns)
- includeUntracked: false (safety default - prevents committing untracked secrets)

### Current Default Config (at /home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json)
This is the minimal default. It needs to be enhanced into a "recommended" config.

### Schema (at /home/idnotbe/projects/claude-code-guardian/assets/guardian.schema.json)
All config must validate against this schema.

## What Makes This "Claude Code Specific"
1. **allowedExternalWritePaths: `~/.claude/plans/**`** - Claude Code saves plan files here when using plan mode
2. **zeroAccessPaths: `.mcp.json`** - Claude Code's MCP server config often contains API keys/tokens
3. The guardian itself is a Claude Code plugin, so the config should reflect Claude Code usage patterns
4. Claude Code creates worktrees in `.claude/worktrees/` - consider read-only protection
5. Claude Code auto-memory lives in `~/.claude/projects/*/memory/` - consider allowing read access

## Requirements
1. Must be a complete, valid JSON file that validates against the schema
2. Should be "opinionated but practical" - good defaults for most Claude Code users
3. Should include helpful $comment fields explaining WHY certain choices were made
4. Should demonstrate Claude Code-specific features (plan paths, MCP config protection, etc.)
5. File name: `assets/guardian.recommended.json`
6. Include practical tips as $comment fields in each section

## Claude Code Characteristics to Reflect
- Uses `--dangerously-skip-permissions` mode (that's why Guardian exists)
- Creates plan files in `~/.claude/plans/`
- Has MCP config at `.mcp.json` (contains secrets like API keys)
- Uses worktrees for isolation at `.claude/worktrees/`
- Has auto-memory at `~/.claude/projects/*/memory/`
- Often reads files from other projects (cross-repo reference)
- Git operations are frequent (commits, branches, etc.)
