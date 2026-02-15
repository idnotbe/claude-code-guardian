# Guardian Plugin -- Next Steps for User

## Status: Migration Verified (4 reviewers + 4 MCP validations)

The hook migration from `settings.json` to the Guardian plugin is complete and verified:
- 4 hooks removed from settings.json (3 PreToolUse + 1 Stop)
- 4 hooks added to hooks.json (correct format, empirically proven via probe)
- 0 gaps, 0 overlaps, all non-hook settings preserved
- Verification: 2 rounds x 2 independent reviewers + vibe-check + pal (Gemini) each round

## What You Need to Do

### Step 1: Disable old _protection folder (optional but recommended)

The old `_protection` folder is harmless (settings.json no longer references it), but renaming makes the state clear:

```powershell
Rename-Item "C:\ops\.claude\hooks\_protection" "_protection.disabled"
```

### Step 2: Exit this Claude Code session

Type `/exit` or press Ctrl+C to end this session.

### Step 3: Start a new session with the Guardian plugin

```powershell
claude --dangerously-skip-permissions --plugin-dir C:\claude-code-guardian
```

### Step 4: Smoke test (runtime verification)

Once the new session starts, try these commands to verify hooks are active:

**Should be BLOCKED:**
```
rm -rf /tmp/test
```

**Should be ALLOWED:**
```
git status
```

If the `rm -rf` is blocked with a `[BLOCKED]` message, the plugin hooks are working. You can then proceed with the full test plan at `C:\ops\temp\guardian-plugin-test-plan.md` (Phase 3-5).

### Step 5: If something goes wrong (ROLLBACK)

```powershell
# 1. Exit Claude Code
# 2. Restore settings.json:
copy C:\ops\temp\settings.json.backup C:\ops\.claude\settings.json
# 3. Restore _protection folder (if renamed):
Rename-Item "C:\ops\.claude\hooks\_protection.disabled" "_protection"
# 4. Restart Claude Code normally (no --plugin-dir)
claude --dangerously-skip-permissions
```

## Review Documents

| Document | Result |
|----------|--------|
| `temp/guardian-migrate-review-r1-settings.md` | R1 Settings: **PASS** |
| `temp/guardian-migrate-review-r1-consistency.md` | R1 Consistency: **PASS** |
| `temp/guardian-migrate-review-r2-security.md` | R2 Security: **CONDITIONAL PASS** (condition = runtime smoke test in Step 4) |
| `temp/guardian-migrate-review-r2-completeness.md` | R2 Completeness: **PASS** |
| `temp/guardian-plugin-test-plan.md` | Full test plan (Phase 3-5 remaining) |
