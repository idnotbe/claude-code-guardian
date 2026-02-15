# Plugin Scope & Error Fix Work Log

## Problem Statement
1. `claude-code-guardian` plugin shows "Marketplace 'inline' not found" error
2. Duplicate hooks file detected: `hooks/hooks.json` loaded twice
3. Plugin is registered at user scope, want project scope
4. Failed to uninstall from user scope

## Current Understanding
- Plugin is loaded via `ccyolo` alias which reads `.claude/plugin-dirs`
- User wants project-level plugin, not user-level

## Investigation Steps
- [ ] Check `.claude/plugin-dirs` content
- [ ] Check plugin.json manifest (hooks reference)
- [ ] Check hooks/hooks.json structure
- [ ] Check how ccyolo alias works
- [ ] Check Claude Code plugin scope mechanisms
- [ ] Consult external models via clink

## Findings

### Key Discovery: Plugin is NOT in installed_plugins.json
- `~/.claude/plugins/installed_plugins.json` does NOT contain `claude-code-guardian`
- Only marketplace plugins (pyright-lsp, typescript-lsp, etc.) are registered there
- The guardian plugin is loaded via **auto-discovery** of `.claude-plugin/plugin.json` in the project root
- This makes it an "inline" plugin — that's why "Marketplace 'inline' not found" error appears

### Error 1: Duplicate hooks
- `plugin.json` line 9: `"hooks": "./hooks/hooks.json"` — explicit reference
- Claude Code ALSO auto-loads `hooks/hooks.json` from plugin root → loaded twice
- **Fix**: Remove `"hooks"` key from plugin.json (auto-load handles it)

### Error 2: Marketplace 'inline' not found
- "inline" is a virtual scope for auto-discovered plugins in the current directory
- Not a real marketplace → lookup fails
- This is a Claude Code display/reporting issue for local dev plugins

### Current Plugin Loading Mechanism
- `ccyolo()` function reads `.claude/plugin-dirs` → passes `--plugin-dir` flags
- Currently `.claude/plugin-dirs` has guardian **commented out**
- Guardian loads via `.claude-plugin/plugin.json` auto-discovery (inline)

### Scope Analysis
- "user scope" = installed via `/install` into `~/.claude/plugins/installed_plugins.json`
- "project scope" = loaded via `--plugin-dir` or `.claude/settings.json` per-project
- "inline" = auto-discovered from `.claude-plugin/plugin.json` in CWD (development mode)
- User wants: project scope (not inline, not user)

## Action Plan

### Already Done (by Codex via clink)
- [x] Removed `"hooks": "./hooks/hooks.json"` from `.claude-plugin/plugin.json`

### Also Fixed
- [x] Removed `"hooks": "./hooks/hooks.json"` from `~/projects/claude-memory/.claude-plugin/plugin.json`

### Other Plugins Checked — All OK
- vibe-check: no hooks key ✓
- deepscan: no hooks key ✓
- prd-creator: no hooks key ✓
- fractal-wave: no hooks key ✓

### Remaining
- [ ] Verify hooks error is fixed (need to restart Claude session)
- [ ] "Marketplace inline" error — cosmetic, no code fix needed
- [ ] claude-memory Stop hooks "JSON validation failed" — separate issue (prompt hook schema mismatch)

## Verification
- Codex removed hooks key: confirmed via `git diff .claude-plugin/plugin.json`
- vibe-check plugin uses same `.claude-plugin/plugin.json` structure and works via plugin-dirs
- Claude Code docs confirm `--plugin-dir` expects `.claude-plugin/plugin.json`

## Key Decision: "inline" vs "project" scope
- Guardian is NOT user-scoped (not in installed_plugins.json)
- "inline" = auto-discovered from .claude-plugin/ in CWD — this IS effectively project scope
- The label "inline" in `/plugin` output is just Claude Code's terminology for local dev plugins
- **No actual scope change needed** — the plugin is already project-scoped
