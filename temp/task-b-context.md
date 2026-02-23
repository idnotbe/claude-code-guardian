# Task B Context: Write Action Plan for SessionStart Auto-Activate

## Objective
Write an action plan in `action-plans/session-start-auto-activate.md` for implementing the SessionStart Auto-Activate ("Instant-On") feature.

## Background
The research report at `/home/idnotbe/projects/claude-code-guardian/research/config-onboarding-research.md` recommends Option D: SessionStart Auto-Activate. This was NOT implemented - only researched.

## What the Action Plan Must Cover

### Feature Summary
When a user starts a Claude Code session and no project config exists at `.claude/guardian/config.json`, Guardian should:
1. Auto-copy `assets/guardian.recommended.json` → `.claude/guardian/config.json`
2. Print a context message so Claude knows to inform the user
3. Stay silent if config already exists

### Implementation Details Needed

1. **New file**: `hooks/scripts/session_start.sh` (bash script)
   - Check if `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` exists
   - If not, create dir and copy recommended config
   - Print activation message to stdout (SessionStart stdout goes into Claude context)
   - If exists, exit 0 silently

2. **Modify file**: `hooks/hooks.json`
   - Add SessionStart event with matcher "startup"
   - Point to the new script
   - Current hooks.json at `/home/idnotbe/projects/claude-code-guardian/hooks/hooks.json`
   - Current events: PreToolUse (Bash, Read, Edit, Write), Stop

3. **Testing**: What tests are needed?
   - Script works when no config exists (copies file, prints message)
   - Script is silent when config exists
   - Created config validates against schema
   - Script handles missing CLAUDE_PROJECT_DIR gracefully
   - Script handles read-only filesystem gracefully (fail-open - don't block session)

4. **Edge cases**:
   - What if `.claude/guardian/` dir exists but config.json doesn't?
   - What if recommended.json is missing from the plugin?
   - What if the filesystem is read-only?
   - What if the user is in a git worktree?

5. **Documentation updates**:
   - README.md update needed?
   - CLAUDE.md update needed?
   - init command behavior change? (it now becomes "customize" not "first setup")

### Action Plan Format
Must follow the frontmatter convention in `/home/idnotbe/projects/claude-code-guardian/action-plans/README.md`:

```yaml
---
status: not-started
progress: "미시작"
---
```

### Reference Files
- Research report: `/home/idnotbe/projects/claude-code-guardian/research/config-onboarding-research.md`
- Current hooks.json: `/home/idnotbe/projects/claude-code-guardian/hooks/hooks.json`
- Plugin manifest: `/home/idnotbe/projects/claude-code-guardian/.claude-plugin/plugin.json`
- Init command: `/home/idnotbe/projects/claude-code-guardian/commands/init.md`
- Recommended config: `/home/idnotbe/projects/claude-code-guardian/assets/guardian.recommended.json`
- Action plans README: `/home/idnotbe/projects/claude-code-guardian/action-plans/README.md`
